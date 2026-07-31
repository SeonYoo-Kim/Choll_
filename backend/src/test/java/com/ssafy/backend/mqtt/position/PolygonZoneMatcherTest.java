package com.ssafy.backend.mqtt.position;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class PolygonZoneMatcherTest {

	private final PolygonZoneMatcher matcher =
		new PolygonZoneMatcher(new ObjectMapper());

	@Test
	void matchesInsideAndBoundaryButNotOutside() {
		String polygon = "[[0,0],[1000,0],[1000,600],[0,600]]";

		assertThat(matcher.contains(
			polygon,
			BigDecimal.valueOf(500),
			BigDecimal.valueOf(300)
		)).isTrue();
		assertThat(matcher.contains(
			polygon,
			BigDecimal.ZERO,
			BigDecimal.valueOf(300)
		)).isTrue();
		assertThat(matcher.contains(
			polygon,
			BigDecimal.valueOf(1001),
			BigDecimal.valueOf(300)
		)).isFalse();
	}

	@Test
	void ignoresMalformedPolygonJson() {
		assertThat(matcher.contains(
			"not-json",
			BigDecimal.ONE,
			BigDecimal.ONE
		)).isFalse();
	}
}
