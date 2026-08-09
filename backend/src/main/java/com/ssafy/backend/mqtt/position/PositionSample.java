package com.ssafy.backend.mqtt.position;

import java.math.BigDecimal;
import java.time.Instant;

public record PositionSample(
	Long cartId,
	BigDecimal x,
	BigDecimal y,
	/** 카트 진행 방향 (라디안, CCW+, SLAM 좌표계 기준). EM 미송신 구버전 페이로드면 null */
	BigDecimal yaw,
	Instant measuredAt
) {
}
