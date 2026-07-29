package com.ssafy.backend.websocket;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
	name = "websocket.position-test.enabled",
	havingValue = "true"
)
public class PositionTestPublisher {

	private static final Long TEST_CART_ID = 1L;

	private final CartWebSocketHandler webSocketHandler;
	private final AtomicLong sequence = new AtomicLong();

	public PositionTestPublisher(CartWebSocketHandler webSocketHandler) {
		this.webSocketHandler = webSocketHandler;
	}

	@Scheduled(fixedRate = 1_000)
	public void publish() {
		long current = sequence.getAndIncrement();
		PositionPayload payload = new PositionPayload(
			decimal(current * 0.1),
			decimal(current * 0.2),
			decimal((current * 0.05) % (Math.PI * 2))
		);
		String event = """
			{"type":"CART_POSITION_UPDATE","payload":{"x":%s,"y":%s,"yaw":%s}}
			""".formatted(
			payload.x().toPlainString(),
			payload.y().toPlainString(),
			payload.yaw().toPlainString()
		);
		webSocketHandler.send(TEST_CART_ID, event);
	}

	private BigDecimal decimal(double value) {
		return BigDecimal.valueOf(value).setScale(2, RoundingMode.HALF_UP);
	}

	private record PositionPayload(
		BigDecimal x,
		BigDecimal y,
		BigDecimal yaw
	) {
	}
}
