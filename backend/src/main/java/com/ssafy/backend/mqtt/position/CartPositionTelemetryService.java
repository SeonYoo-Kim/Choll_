package com.ssafy.backend.mqtt.position;

import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.domain.CartConnectionStatus;
import com.ssafy.backend.cart.repository.CartRepository;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import com.ssafy.backend.zone.domain.Zone;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CartPositionTelemetryService {

	private static final Logger log =
		LoggerFactory.getLogger(CartPositionTelemetryService.class);
	private static final ZoneId DATABASE_ZONE = ZoneId.of("Asia/Seoul");

	private final CartRepository cartRepository;
	private final RecentPositionBuffer positionBuffer;
	private final ZoneLocator zoneLocator;
	private final StableZoneTracker zoneTracker;

	public CartPositionTelemetryService(
		CartRepository cartRepository,
		RecentPositionBuffer positionBuffer,
		ZoneLocator zoneLocator,
		StableZoneTracker zoneTracker
	) {
		this.cartRepository = cartRepository;
		this.positionBuffer = positionBuffer;
		this.zoneLocator = zoneLocator;
		this.zoneTracker = zoneTracker;
	}

	@Transactional
	public void accept(PositionSample position) {
		Cart cart = cartRepository.findById(position.cartId())
			.orElseThrow(() -> new ResourceNotFoundException("카트", position.cartId()));
		positionBuffer.add(position);

		Optional<Zone> detectedZone = zoneLocator.locate(position.x(), position.y());
		StableZoneTracker.Decision decision = zoneTracker.observe(
			position.cartId(),
			detectedZone.map(Zone::getId).orElse(null)
		);
		Zone currentZone = decision.stable()
			? detectedZone.orElse(null)
			: cart.getCurrentZone();
		LocalDateTime measuredAt = LocalDateTime.ofInstant(
			position.measuredAt(),
			DATABASE_ZONE
		);

		cart.updateStatus(
			CartConnectionStatus.ONLINE,
			cart.getOperationStatus(),
			measuredAt
		);
		cart.updatePosition(position.x(), position.y(), currentZone, measuredAt);

		log.info(
			"카트 위치 수신 cartId={}, x={}, y={}, detectedZoneId={}, stable={}, bufferSize={}",
			position.cartId(),
			position.x(),
			position.y(),
			detectedZone.map(Zone::getId).orElse(null),
			decision.stable(),
			positionBuffer.snapshot(position.cartId()).size()
		);
	}
}
