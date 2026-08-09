package com.ssafy.backend.mqtt.position;

import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.repository.CartRepository;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import com.ssafy.backend.led.service.SlotLedService;
import com.ssafy.backend.map.domain.LibraryMap;
import com.ssafy.backend.map.repository.LibraryMapRepository;
import com.ssafy.backend.mqtt.heartbeat.CartConnectionService;
import com.ssafy.backend.websocket.CartEventPublisher;
import com.ssafy.backend.zone.domain.Zone;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CartPositionTelemetryService {

	private static final Logger log =
		LoggerFactory.getLogger(CartPositionTelemetryService.class);
	private static final ZoneId DATABASE_ZONE = ZoneId.of("Asia/Seoul");
	private static final String POSITION_EVENT_TYPE = "CART_POSITION_UPDATE";
	private static final String UNIT_METERS = "meters";

	private final CartRepository cartRepository;
	private final RecentPositionBuffer positionBuffer;
	private final ZoneLocator zoneLocator;
	private final StableZoneTracker zoneTracker;
	private final CartEventPublisher eventPublisher;
	private final CartConnectionService connectionService;
	private final LibraryMapRepository mapRepository;
	private final SlamCoordinateConverter coordinateConverter;
	private final SlotLedService slotLedService;
	// EM 계약(2026-07-31 확정): 위치는 SLAM 미터 좌표 — meters면 BE가 이미지 픽셀로 변환.
	// EM 발행 시작 전까지는 pixels(무변환)로 두고 수동 테스트 호환 유지.
	private final String positionUnit;
	private final long mapId;

	public CartPositionTelemetryService(
		CartRepository cartRepository,
		RecentPositionBuffer positionBuffer,
		ZoneLocator zoneLocator,
		StableZoneTracker zoneTracker,
		CartEventPublisher eventPublisher,
		CartConnectionService connectionService,
		LibraryMapRepository mapRepository,
		SlamCoordinateConverter coordinateConverter,
		SlotLedService slotLedService,
		@Value("${mqtt.position-unit:pixels}") String positionUnit,
		@Value("${mqtt.map-id:2}") long mapId
	) {
		this.cartRepository = cartRepository;
		this.positionBuffer = positionBuffer;
		this.zoneLocator = zoneLocator;
		this.zoneTracker = zoneTracker;
		this.eventPublisher = eventPublisher;
		this.connectionService = connectionService;
		this.mapRepository = mapRepository;
		this.coordinateConverter = coordinateConverter;
		this.slotLedService = slotLedService;
		this.positionUnit = positionUnit;
		this.mapId = mapId;
	}

	@Transactional
	public void accept(PositionSample position) {
		Cart cart = cartRepository.findById(position.cartId())
			.orElseThrow(() -> new ResourceNotFoundException("카트", position.cartId()));
		positionBuffer.add(position);

		BigDecimal x = position.x();
		BigDecimal y = position.y();
		// EM이 yaw(라디안, SLAM 기준 CCW+)를 실기 발행 중 (2026-08-09 확정) — 없으면 0
		BigDecimal yaw = position.yaw() == null ? BigDecimal.ZERO : position.yaw();
		Long knownMapId = null;
		if (UNIT_METERS.equalsIgnoreCase(positionUnit)) {
			LibraryMap map = mapRepository.findById(mapId)
				.orElseThrow(() -> new ResourceNotFoundException("지도", mapId));
			SlamCoordinateConverter.ImagePosition converted =
				coordinateConverter.toImagePixels(x, y, map);
			x = converted.x();
			y = converted.y();
			// 방향도 위치와 같은 변환을 거쳐야 화면 마커가 실제 진행 방향을 가리킨다
			yaw = coordinateConverter.toImageYaw(yaw, map);
			knownMapId = map.getId();
		}

		Optional<Zone> detectedZone = zoneLocator.locate(x, y);
		StableZoneTracker.Decision decision = zoneTracker.observe(
			position.cartId(),
			detectedZone.map(Zone::getId).orElse(null)
		);
		Zone previousZone = cart.getCurrentZone();
		Zone currentZone = decision.stable()
			? detectedZone.orElse(null)
			: previousZone;
		LocalDateTime measuredAt = LocalDateTime.ofInstant(
			position.measuredAt(),
			DATABASE_ZONE
		);

		// 위치 수신도 생존 신호 — OFFLINE→ONLINE 전환 시 연결 이벤트 발행 포함
		connectionService.markAlive(cart, measuredAt);
		cart.updatePosition(x, y, currentZone, measuredAt);

		Long eventMapId = knownMapId != null
			? knownMapId
			: (currentZone == null ? null : currentZone.getMap().getId());
		eventPublisher.publish(position.cartId(), POSITION_EVENT_TYPE, new PositionEventPayload(
			eventMapId,
			x,
			y,
			yaw,
			true
		));

		// 구역이 바뀐 순간에만 LED 발행 — 이탈이면 빈 목록으로 소등, 같은 구역 유지면 발행 없음
		if (zoneChanged(previousZone, currentZone)) {
			slotLedService.syncZoneLighting(position.cartId(), previousZone != null);
		}

		log.info(
			"카트 위치 수신 cartId={}, raw=({}, {}), image=({}, {}), unit={}, detectedZoneId={}, stable={}",
			position.cartId(),
			position.x(),
			position.y(),
			x,
			y,
			positionUnit,
			detectedZone.map(Zone::getId).orElse(null),
			decision.stable()
		);
	}

	/** 구역이 막 바뀌었는지 — 진입·이탈·구역 간 이동은 true, 같은 구역 유지는 false. */
	private static boolean zoneChanged(Zone previous, Zone current) {
		if (previous == null && current == null) {
			return false;
		}
		if (previous == null || current == null) {
			return true;
		}
		return !previous.getId().equals(current.getId());
	}

	// WS-FE-01 CART_POSITION_UPDATE 페이로드 (x·y는 지도 이미지 픽셀, yaw는 이미지 기준 라디안,
	// mapId는 구역 미확정 시 null)
	private record PositionEventPayload(
		Long mapId,
		BigDecimal x,
		BigDecimal y,
		BigDecimal yaw,
		boolean valid
	) {
	}
}
