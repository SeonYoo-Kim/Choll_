package com.ssafy.backend.mqtt.position;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class StableZoneTrackerTest {

	@Test
	void becomesStableAfterThreeConsecutiveSamplesInTheSameZone() {
		StableZoneTracker tracker = new StableZoneTracker();

		assertThat(tracker.observe(1L, 10L).stable()).isFalse();
		assertThat(tracker.observe(1L, 10L).stable()).isFalse();
		assertThat(tracker.observe(1L, 10L).stable()).isTrue();
	}

	@Test
	void resetsTheCountWhenDetectedZoneChanges() {
		StableZoneTracker tracker = new StableZoneTracker();

		tracker.observe(1L, 10L);
		tracker.observe(1L, 10L);
		assertThat(tracker.observe(1L, 20L).stable()).isFalse();
		assertThat(tracker.observe(1L, 20L).stable()).isFalse();
		assertThat(tracker.observe(1L, 20L).stable()).isTrue();
	}

	@Test
	void tracksEachCartIndependently() {
		StableZoneTracker tracker = new StableZoneTracker();

		tracker.observe(1L, 10L);
		tracker.observe(1L, 10L);
		tracker.observe(2L, 10L);

		assertThat(tracker.observe(1L, 10L).stable()).isTrue();
		assertThat(tracker.observe(2L, 10L).stable()).isFalse();
	}
}
