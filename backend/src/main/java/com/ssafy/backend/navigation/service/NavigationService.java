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
import com.ssafy.backend.mqtt.position.PolygonZoneMatcher;
import com.ssafy.backend.mqtt.position.SlamCoordinateConverter;
import com.ssafy.backend.websocket.CartEventPublisher;
import com.ssafy.backend.zone.domain.Zone;
import com.ssafy.backend.zone.repository.ZoneRepository;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
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
 * 목적지 좌표: FE가 픽셀(x,y)을 주면 그 지점, 없으면 구역 bbox 중심.
 * 클릭 지점이 구역 밖(서가·테이블 위)이면 그 구역 안에서 가장 가까운 지점으로 스냅한다 —
 * FE는 지도 어디든 누를 수 있고(2026-08-07), 장애물 안을 nav goal로 내려보내면 EM이 도달할 수 없다.
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
	private final PolygonZoneMatcher polygonMatcher;
	private final CartEventPublisher eventPublisher;
	private final ObjectProvider<MqttCommandPublisher> commandPublisher;
	private final ObjectMapper objectMapper;
	private final String positionUnit;
	private final long mapId;
	/** 구역 밖 클릭을 스냅할 때 경계에서 안쪽으로 확보할 여유 (미터) */
	private final double snapMarginMeters;

	private final ConcurrentHashMap<Long, ActiveNavigation> activeByCartId =
		new ConcurrentHashMap<>();
	private final AtomicLong navigationSequence = new AtomicLong();

	public NavigationService(
		CartRepository cartRepository,
		ZoneRepository zoneRepository,
		LibraryMapRepository mapRepository,
		SlamCoordinateConverter coordinateConverter,
		PolygonZoneMatcher polygonMatcher,
		CartEventPublisher eventPublisher,
		ObjectProvider<MqttCommandPublisher> commandPublisher,
		ObjectMapper objectMapper,
		@Value("${mqtt.position-unit:pixels}") String positionUnit,
		@Value("${mqtt.map-id:2}") long mapId,
		@Value("${navigation.snap-margin-meters:0.5}") double snapMarginMeters
	) {
		this.cartRepository = cartRepository;
		this.zoneRepository = zoneRepository;
		this.mapRepository = mapRepository;
		this.coordinateConverter = coordinateConverter;
		this.polygonMatcher = polygonMatcher;
		this.eventPublisher = eventPublisher;
		this.commandPublisher = commandPublisher;
		this.objectMapper = objectMapper;
		this.positionUnit = positionUnit;
		this.mapId = mapId;
		this.snapMarginMeters = snapMarginMeters;
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
			? snapIntoZone(zone, pixelX, pixelY)
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
	 * 클릭 지점을 목적지로 삼되, 요청한 구역 밖이면 그 구역 안에서 가장 가까운 지점으로 당긴다.
	 *
	 * FE는 지도의 아무 지점이나 목적지로 보낼 수 있다 — 서가나 테이블 위를 눌렀을 때 그 좌표를
	 * 그대로 하행하면 장애물 안이 nav goal이 되어 EM SLAM Nav가 도달하지 못한다. 스냅 대상은
	 * 다른 구역이 아니라 **요청에 실린 구역**이다: FE가 이미 가장 가까운 구역을 골라 zoneId로
	 * 보내고 그 구역 이름으로 사서에게 안내하므로, 목적지가 다른 구역으로 튀면 안내와 어긋난다.
	 *
	 * 폴리곤을 읽을 수 없으면 클릭 지점을 그대로 쓴다 — 좌표를 버려 구역 중심으로 보내면
	 * 사서가 찍은 자리와 동떨어진 곳으로 가고, 그 편이 더 놀랍다.
	 */
	private Destination snapIntoZone(Zone zone, double pixelX, double pixelY) {
		Optional<PolygonZoneMatcher.Point> inside = polygonMatcher.closestPointInside(
			zone.getPolygonJson(),
			pixelX,
			pixelY,
			snapMarginPixels(zone)
		);
		if (inside.isEmpty()) {
			log.warn(
				"구역 {}의 좌표를 읽을 수 없어 클릭 지점을 그대로 씁니다. pixel=({}, {})",
				zone.getId(),
				pixelX,
				pixelY
			);
			return new Destination(pixelX, pixelY);
		}
		// 스냅 계산은 나눗셈을 거쳐 5.999999999999999 같은 값을 만든다 — 하행 전에 픽셀 2자리로 정리
		PolygonZoneMatcher.Point point = new PolygonZoneMatcher.Point(
			roundPixel(inside.get().x()),
			roundPixel(inside.get().y())
		);
		if (point.x() != pixelX || point.y() != pixelY) {
			log.info(
				"구역 밖 클릭을 구역 안으로 스냅 zoneId={}, 클릭=({}, {}) → 목적지=({}, {})",
				zone.getId(),
				pixelX,
				pixelY,
				point.x(),
				point.y()
			);
		}
		return new Destination(point.x(), point.y());
	}

	/** 지도 이미지 픽셀 소수 2자리 — 0.05 m/px 기준 1mm 이하라 목적지 정밀도에 영향이 없다 */
	private static double roundPixel(double pixel) {
		return Math.round(pixel * 100.0) / 100.0;
	}

	/**
	 * 스냅 여유(미터)를 이 구역이 속한 지도의 픽셀로 환산한다.
	 * 해상도를 모르면 0 — 경계 위에 세우게 되지만, 임의의 픽셀 값을 쓰는 것보다 낫다.
	 */
	private double snapMarginPixels(Zone zone) {
		LibraryMap map = zone.getMap();
		BigDecimal resolution = map == null ? null : map.getResolution();
		if (resolution == null || resolution.signum() <= 0) {
			return 0.0;
		}
		return snapMarginMeters / resolution.doubleValue();
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
