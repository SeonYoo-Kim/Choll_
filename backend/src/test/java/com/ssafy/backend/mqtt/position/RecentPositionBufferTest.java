package com.ssafy.backend.mqtt.position;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class RecentPositionBufferTest {

	@Test
	void keepsOnlyTheMostRecentTwentyPositionsPerCart() {
		RecentPositionBuffer buffer = new RecentPositionBuffer(20);

		for (int sequence = 1; sequence <= 25; sequence++) {
			buffer.add(new PositionSample(
				1L,
				BigDecimal.valueOf(sequence),
				BigDecimal.ZERO,
			null,
				Instant.EPOCH.plusSeconds(sequence)
			));
		}

		List<PositionSample> positions = buffer.snapshot(1L);
		assertThat(positions).hasSize(20);
		assertThat(positions.getFirst().x()).isEqualByComparingTo("6");
		assertThat(positions.getLast().x()).isEqualByComparingTo("25");
	}

	@Test
	void separatesPositionsByCart() {
		RecentPositionBuffer buffer = new RecentPositionBuffer(20);

		buffer.add(new PositionSample(
			1L,
			BigDecimal.ONE,
			BigDecimal.ONE,
			null,
			Instant.EPOCH
		));
		buffer.add(new PositionSample(
			2L,
			BigDecimal.TWO,
			BigDecimal.TWO,
			null,
			Instant.EPOCH
		));

		assertThat(buffer.snapshot(1L)).hasSize(1);
		assertThat(buffer.snapshot(2L)).hasSize(1);
		assertThat(buffer.snapshot(3L)).isEmpty();
	}
}
