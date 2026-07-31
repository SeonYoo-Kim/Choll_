package com.ssafy.backend.mqtt.position;

import java.math.BigDecimal;
import java.time.Instant;

public record PositionSample(
	Long cartId,
	BigDecimal x,
	BigDecimal y,
	Instant measuredAt
) {
}
