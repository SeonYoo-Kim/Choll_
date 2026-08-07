package com.ssafy.backend.mqtt.position;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class PolygonZoneMatcherTest {

	/** 0~100 정사각형 (중심 50,50) — 스냅 결과를 눈으로 검산하기 쉬운 도형 */
	private static final String SQUARE = "[[0,0],[100,0],[100,100],[0,100]]";

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

	@Test
	void closestPointInsideKeepsPointThatIsAlreadyInside() {
		assertThat(matcher.closestPointInside(SQUARE, 30.0, 40.0, 6.0))
			.contains(new PolygonZoneMatcher.Point(30.0, 40.0));
	}

	@Test
	void closestPointInsidePullsOutsidePointToNearestEdgePlusMargin() {
		// 왼쪽 밖 → 가장 가까운 경계 (0,50) → 중심(50,50) 쪽으로 6px
		assertThat(matcher.closestPointInside(SQUARE, -50.0, 50.0, 6.0))
			.contains(new PolygonZoneMatcher.Point(6.0, 50.0));
		// 아래쪽 밖 → 경계 (50,100) → 중심 쪽으로 6px
		assertThat(matcher.closestPointInside(SQUARE, 50.0, 250.0, 6.0))
			.contains(new PolygonZoneMatcher.Point(50.0, 94.0));
	}

	@Test
	void closestPointInsideWithoutMarginLandsOnTheBoundary() {
		assertThat(matcher.closestPointInside(SQUARE, -50.0, 50.0, 0.0))
			.contains(new PolygonZoneMatcher.Point(0.0, 50.0));
	}

	@Test
	void closestPointInsideFallsBackToCentroidWhenMarginExceedsPolygon() {
		// 여유가 도형보다 크면 중심을 넘어가 다시 밖으로 나간다 — 그때는 중심으로
		assertThat(matcher.closestPointInside(SQUARE, -50.0, 50.0, 500.0))
			.contains(new PolygonZoneMatcher.Point(50.0, 50.0));
	}

	@Test
	void closestPointInsideIsEmptyWhenPolygonIsNotAShape() {
		assertThat(matcher.closestPointInside("not-json", 1.0, 1.0, 6.0)).isEmpty();
		assertThat(matcher.closestPointInside("[[0,0],[100,0]]", 1.0, 1.0, 6.0)).isEmpty();
		assertThat(matcher.closestPointInside(null, 1.0, 1.0, 6.0)).isEmpty();
	}
}
