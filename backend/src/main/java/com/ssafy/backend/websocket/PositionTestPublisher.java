package com.ssafy.backend.websocket;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
	name = "websocket.position-test.enabled",
	havingValue = "true"
)
public class PositionTestPublisher {

	private static final double CENTER_X = 500.0;
	private static final double CENTER_Y = 300.0;
	private static final double RADIUS_X = 350.0;
	private static final double RADIUS_Y = 200.0;
	private static final double ANGLE_STEP_RADIANS = Math.PI / 30.0;

	private final CartWebSocketHandler webSocketHandler;
	private final long testCartId;
	private final long testMapId;
	private final AtomicLong sequence = new AtomicLong();

	public PositionTestPublisher(
		CartWebSocketHandler webSocketHandler,
		@Value("${websocket.position-test.cart-id:1}") long testCartId,
		@Value("${websocket.position-test.map-id:2}") long testMapId
	) {
		this.webSocketHandler = webSocketHandler;
		this.testCartId = testCartId;
		this.testMapId = testMapId;
	}

	@Scheduled(fixedRate = 1_000)
	public void publish() {
		long current = sequence.getAndIncrement();
		double angle = current * ANGLE_STEP_RADIANS;
		PositionPayload payload = new PositionPayload(
			testMapId,
			decimal(CENTER_X + RADIUS_X * Math.cos(angle)),
			decimal(CENTER_Y + RADIUS_Y * Math.sin(angle)),
			decimal(Math.atan2(
				RADIUS_Y * Math.cos(angle),
				-RADIUS_X * Math.sin(angle)
			)),
			true
		);
		String event = """
			{"type":"CART_POSITION_UPDATE","payload":{"mapId":%d,"x":%s,"y":%s,"yaw":%s,"valid":%s}}
			""".formatted(
			payload.mapId(),
			payload.x().toPlainString(),
			payload.y().toPlainString(),
			payload.yaw().toPlainString(),
			payload.valid()
		);
		webSocketHandler.send(testCartId, event);
	}

	private BigDecimal decimal(double value) {
		return BigDecimal.valueOf(value).setScale(2, RoundingMode.HALF_UP);
	}

	private record PositionPayload(
		Long mapId,
		BigDecimal x,
		BigDecimal y,
		BigDecimal yaw,
		boolean valid
	) {
	}
}
