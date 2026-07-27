package com.ssafy.backend.mqtt.position;

import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Component;

@Component
public class StableZoneTracker {

	static final int REQUIRED_CONSECUTIVE_SAMPLES = 3;

	private final Map<Long, Candidate> candidates = new ConcurrentHashMap<>();

	public Decision observe(Long cartId, Long zoneId) {
		AtomicReference<Decision> decision = new AtomicReference<>();
		candidates.compute(cartId, (ignored, previous) -> {
			int count = previous != null && Objects.equals(previous.zoneId(), zoneId)
				? previous.count() + 1
				: 1;
			Candidate current = new Candidate(zoneId, count);
			decision.set(new Decision(count >= REQUIRED_CONSECUTIVE_SAMPLES));
			return current;
		});
		return decision.get();
	}

	private record Candidate(Long zoneId, int count) {
	}

	public record Decision(boolean stable) {
	}
}
