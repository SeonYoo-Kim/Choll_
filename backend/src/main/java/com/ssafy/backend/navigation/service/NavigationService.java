package com.ssafy.backend.navigation.service;

import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.domain.CartConnectionStatus;
import com.ssafy.backend.cart.domain.CartOperationStatus;
import com.ssafy.backend.cart.repository.CartRepository;
import com.ssafy.backend.common.exception.InvalidDomainException;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import com.ssafy.backend.map.domain.LibraryMap;
import com.ssafy.backend.map.repository.LibraryMapRepository;
import com.ssafy.backend.mqtt.command.MqttCommandPublisher;
import com.ssafy.backend.mqtt.position.SlamCoordinateConverter;
import com.ssafy.backend.websocket.CartEventPublisher;
import com.ssafy.backend.zone.domain.Zone;
import com.ssafy.backend.zone.repository.ZoneRepository;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * 목적지 이동 명령(NAV-01/02): FE REST 요청을 MQTT 명령으로 변환하고
 * NAVIGATION_STATUS_UPDATED WebSocket 이벤트로 진행 상태를 FE에 전달한다.
 * 이동 상태는 인메모리(카트당 1건) — 카트의 상행 결과 토픽이 확정되면
 * STARTED/ARRIVED/FAILED 전환을 붙일 자리다.
 *
 * 목적지 좌표: FE가 픽셀(x,y)을 주면 **그 지점 그대로**, 없으면 구역 bbox 중심.
 * 통로 한가운데 같은 구역 밖 좌표도 목적지가 될 수 있으므로 BE는 스냅하지 않는다(2026-08-07) —
 * 장애물(서가·테이블) 클릭을 고정 정차점으로 바꾸는 책임은 FE 평면도에 있고,
 * 그래도 도달 불가한 goal은 Nav2가 거부해 status/nav-result(ABORTED·REJECTED)로 FAILED가 전달된다.
 * mqtt.position-unit=meters면 지도 메타(resolution·origin)로 SLAM 미터 target을
 * 함께 하행한다 (EM SLAM Nav의 goal 좌표). pixels 모드(메타 미입력)에선 target=null.
 */
@Service
public class NavigationService {

	private static final Logger log = LoggerFactory.getLogger(NavigationService.class);
	private static final String NAVIGATION_EVENT_TYPE = "NAVIGATION_STATUS_UPDATED";
	private static final String UNIT_METERS = "meters";

	private final CartRepository cartRepository;
	private final ZoneRepository zoneRepository;
	private final LibraryMapRepository mapRepository;
	private final SlamCoordinateConverter coordinateConverter;
	private final CartEventPublisher eventPublisher;
	private final ObjectProvider<MqttCommandPublisher> commandPublisher;
	private final ObjectMapper objectMapper;
	private final String positionUnit;
	private final long mapId;

	private final ConcurrentHashMap<Long, ActiveNavigation> activeByCartId =
		new ConcurrentHashMap<>();
	private final AtomicLong navigationSequence = new AtomicLong();

	public NavigationService(
		CartRepository cartRepository,
		ZoneRepository zoneRepository,
		LibraryMapRepository mapRepository,
		SlamCoordinateConverter coordinateConverter,
		CartEventPublisher eventPublisher,
		ObjectProvider<MqttCommandPublisher> commandPublisher,
		ObjectMapper objectMapper,
		@Value("${mqtt.position-unit:pixels}") String positionUnit,
		@Value("${mqtt.map-id:2}") long mapId
	) {
		this.cartRepository = cartRepository;
		this.zoneRepository = zoneRepository;
		this.mapRepository = mapRepository;
		this.coordinateConverter = coordinateConverter;
		this.eventPublisher = eventPublisher;
		this.commandPublisher = commandPublisher;
		this.objectMapper = objectMapper;
		this.positionUnit = positionUnit;
		this.mapId = mapId;
	}

	@Transactional
	public Response start(Long cartId, Long zoneId) {
		return start(cartId, zoneId, null, null);
	}

	@Transactional
	public Response start(Long cartId, Long zoneId, Double pixelX, Double pixelY) {
		Cart cart = cartRepository.findById(cartId)
			.orElseThrow(() -> new ResourceNotFoundException("카트", cartId));
		Zone zone = zoneRepository.findById(zoneId)
			.orElseThrow(() -> new ResourceNotFoundException("구역", zoneId));
		if (cart.getConnectionStatus() != CartConnectionStatus.ONLINE) {
			throw new InvalidDomainException("카트가 오프라인 상태라 이동 명령을 보낼 수 없습니다.");
		}
		if (activeByCartId.containsKey(cartId)) {
			throw new InvalidDomainException("이미 진행 중인 이동이 있습니다. 취소 후 다시 시도하세요.");
		}

		long navigationId = navigationSequence.incrementAndGet();
		Destination destination = pixelX != null && pixelY != null
			? new Destination(pixelX, pixelY)
			: resolveDestination(zone);
		Target target = toSlamTarget(destination);
		cart.updateStatus(
			cart.getConnectionStatus(),
			CartOperationStatus.NAVIGATING,
			cart.getLastCommunicationAt()
		);
		activeByCartId.put(cartId, new ActiveNavigation(navigationId, zoneId));

		publishCommand(new MoveCommand(
			navigationId,
			"MOVE",
			zoneId,
			target,
			new Pixel(destination.x(), destination.y())
		));
		publishNavigationEvent(cartId, navigationId, "ACCEPTED", zoneId, null);
		log.info(
			"이동 명령 접수 cartId={}, navigationId={}, zoneId={}, pixel=({}, {}), target={}",
			cartId,
			navigationId,
			zoneId,
			destination.x(),
			destination.y(),
			target
		);
		return new Response(navigationId, "ACCEPTED", zoneId);
	}

	/**
	 * 픽셀 목적지를 SLAM 미터 좌표로 변환한다.
	 * pixels 모드(지도 메타 미입력 — EM 좌표 연동 전)에서는 null을 반환하고,
	 * EM 연동 시 mqtt.position-unit=meters + library_maps 실값 입력으로 켠다.
	 */
	private Target toSlamTarget(Destination pixelDestination) {
		if (!UNIT_METERS.equalsIgnoreCase(positionUnit)) {
			return null;
		}
		LibraryMap map = mapRepository.findById(mapId)
			.orElseThrow(() -> new ResourceNotFoundException("지도", mapId));
		SlamCoordinateConverter.SlamPosition slam = coordinateConverter.toSlamMeters(
			BigDecimal.valueOf(pixelDestination.x()),
			BigDecimal.valueOf(pixelDestination.y()),
			map
		);
		return new Target(slam.x().doubleValue(), slam.y().doubleValue());
	}

	@Transactional
	public void cancel(Long cartId) {
		Cart cart = cartRepository.findById(cartId)
			.orElseThrow(() -> new ResourceNotFoundException("카트", cartId));
		ActiveNavigation active = activeByCartId.remove(cartId);
		if (active == null) {
			// 세션은 인메모리라 재시작하면 사라지는데 DB 상태만 NAVIGATING으로
			// 남을 수 있다 — 취소 요청이 오면 그 고아 상태도 청소한다
			if (cart.getOperationStatus() == CartOperationStatus.NAVIGATING) {
				cart.updateStatus(
					cart.getConnectionStatus(),
					CartOperationStatus.IDLE,
					cart.getLastCommunicationAt()
				);
				log.info("세션 없는 NAVIGATING 상태 정리 (재시작 잔재) cartId={}", cartId);
				return;
			}
			log.info("취소할 진행 중 이동이 없습니다. cartId={} (무시)", cartId);
			return;
		}
		cart.updateStatus(
			cart.getConnectionStatus(),
			CartOperationStatus.IDLE,
			cart.getLastCommunicationAt()
		);
		publishCommand(new MoveCommand(active.navigationId(), "CANCEL", active.zoneId(), null, null));
		publishNavigationEvent(cartId, active.navigationId(), "CANCELLED", active.zoneId(), null);
		log.info("이동 취소 cartId={}, navigationId={}", cartId, active.navigationId());
	}

	/**
	 * 카트(EM SLAM Nav)의 주행 결과(status/nav-result) 반영 — ROS2 /cart/nav_status 7종.
	 *
	 * NAVIGATING은 진행 중 세션에 STARTED를 중계하고, SUCCEEDED/CANCELED/ABORTED/REJECTED/
	 * NAV2_UNAVAILABLE은 세션을 종료한다. IDLE은 노드 기동 신호라 세션과 무관 — 무시.
	 * 세션이 없어도(BE 재시작·REST 취소 선행) DB의 NAVIGATING 잔재는 정리한다.
	 */
	@Transactional
	public void applyCartNavResult(Long cartId, String navResult) {
		switch (navResult) {
			case "IDLE" -> {
				// 노드 기동 직후의 대기 신호 — 이동 세션과 무관하다
			}
			case "NAVIGATING" -> {
				ActiveNavigation active = activeByCartId.get(cartId);
				if (active == null) {
					log.warn("진행 중 세션이 없는 NAVIGATING 수신 (무시) cartId={}", cartId);
					return;
				}
				publishNavigationEvent(cartId, active.navigationId(), "STARTED", active.zoneId(), null);
				log.info("카트 주행 시작 cartId={}, navigationId={}", cartId, active.navigationId());
			}
			case "SUCCEEDED" -> completeFromCart(cartId, "ARRIVED", null);
			case "CANCELED" -> completeFromCart(cartId, "CANCELLED", null);
			case "ABORTED" -> completeFromCart(cartId, "FAILED", "경로를 찾지 못해 주행을 포기했습니다");
			case "REJECTED" -> completeFromCart(cartId, "FAILED", "카트가 이동 명령을 거부했습니다");
			case "NAV2_UNAVAILABLE" ->
				completeFromCart(cartId, "FAILED", "카트 주행 시스템이 꺼져 있습니다");
			default -> log.warn("알 수 없는 주행 결과 (무시) cartId={}, navResult={}", cartId, navResult);
		}
	}

	/**
	 * 주행 종료 처리 — 카트를 대기 상태로 되돌리고, 세션이 있으면 종료 이벤트를 FE에 알린다.
	 * 세션이 없으면(REST 취소가 먼저 정리했거나 BE 재시작) DB 상태 정리만 하고 조용히 끝낸다 —
	 * REST 취소 직후 카트가 CANCELED를 확인 응답하는 정상 흐름에서 이벤트가 중복되지 않게.
	 */
	private void completeFromCart(Long cartId, String status, String failReason) {
		Cart cart = cartRepository.findById(cartId)
			.orElseThrow(() -> new ResourceNotFoundException("카트", cartId));
		ActiveNavigation active = activeByCartId.remove(cartId);
		if (cart.getOperationStatus() == CartOperationStatus.NAVIGATING) {
			cart.updateStatus(
				cart.getConnectionStatus(),
				CartOperationStatus.IDLE,
				cart.getLastCommunicationAt()
			);
		}
		if (active == null) {
			log.info("세션 없는 주행 종료 수신 — DB 상태만 정리 cartId={}, status={}", cartId, status);
			return;
		}
		publishNavigationEvent(cartId, active.navigationId(), status, active.zoneId(), failReason);
		log.info(
			"카트 주행 종료 cartId={}, navigationId={}, status={}, failReason={}",
			cartId,
			active.navigationId(),
			status,
			failReason
		);
	}

	private void publishCommand(MoveCommand command) {
		MqttCommandPublisher publisher = commandPublisher.getIfAvailable();
		if (publisher == null) {
			log.warn("MQTT 비활성 — 명령을 발행하지 못했습니다. command={}", command);
			return;
		}
		publisher.publish(command);
	}

	private void publishNavigationEvent(
		Long cartId,
		long navigationId,
		String status,
		Long destinationZoneId,
		String failReason
	) {
		eventPublisher.publish(cartId, NAVIGATION_EVENT_TYPE, new NavigationEventPayload(
			navigationId,
			status,
			destinationZoneId,
			failReason
		));
	}

	/** 구역 폴리곤의 bounding box 중심을 목적지 좌표로 사용한다. */
	private Destination resolveDestination(Zone zone) {
		try {
			List<List<Double>> vertices = objectMapper.readValue(
				zone.getPolygonJson(),
				new TypeReference<List<List<Double>>>() {
				}
			);
			if (vertices.isEmpty()) {
				throw new IllegalArgumentException("구역 좌표가 비어 있습니다.");
			}
			double minX = Double.MAX_VALUE;
			double maxX = -Double.MAX_VALUE;
			double minY = Double.MAX_VALUE;
			double maxY = -Double.MAX_VALUE;
			for (List<Double> vertex : vertices) {
				minX = Math.min(minX, vertex.get(0));
				maxX = Math.max(maxX, vertex.get(0));
				minY = Math.min(minY, vertex.get(1));
				maxY = Math.max(maxY, vertex.get(1));
			}
			return new Destination((minX + maxX) / 2, (minY + maxY) / 2);
		} catch (JacksonException | IllegalArgumentException | IndexOutOfBoundsException exception) {
			throw new InvalidDomainException(
				"구역 %d의 좌표를 계산할 수 없습니다.".formatted(zone.getId())
			);
		}
	}

	private record ActiveNavigation(long navigationId, Long zoneId) {
	}

	private record Destination(double x, double y) {
	}

	// BE→EM 이동 명령 페이로드 — ⚠️ EM 미확정 임시 계약.
	// target=SLAM 미터(EM nav goal, pixels 모드에선 null), pixel=지도 이미지 픽셀(참고용)
	private record MoveCommand(
		long requestId,
		String command,
		Long zoneId,
		Target target,
		Pixel pixel
	) {
	}

	private record Target(double x, double y) {
	}

	private record Pixel(double x, double y) {
	}

	// WS-FE-06 NAVIGATION_STATUS_UPDATED 페이로드
	private record NavigationEventPayload(
		long navigationId,
		String status,
		Long destinationZoneId,
		String failReason
	) {
	}

	@Schema(name = "NavigationCommand")
	public record Response(
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		long navigationId,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		String status,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		Long destinationZoneId
	) {
	}
}
