package com.ssafy.backend.mqtt.position;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class RecentPositionBuffer {

	static final int DEFAULT_CAPACITY = 20;

	private final int capacity;
	private final Map<Long, ArrayDeque<PositionSample>> positionsByCart =
		new ConcurrentHashMap<>();

	public RecentPositionBuffer() {
		this(DEFAULT_CAPACITY);
	}

	RecentPositionBuffer(int capacity) {
		if (capacity < 1) {
			throw new IllegalArgumentException("위치 버퍼 크기는 1 이상이어야 합니다.");
		}
		this.capacity = capacity;
	}

	public void add(PositionSample position) {
		ArrayDeque<PositionSample> positions = positionsByCart.computeIfAbsent(
			position.cartId(),
			ignored -> new ArrayDeque<>(capacity)
		);
		synchronized (positions) {
			if (positions.size() == capacity) {
				positions.removeFirst();
			}
			positions.addLast(position);
		}
	}

	public List<PositionSample> snapshot(Long cartId) {
		ArrayDeque<PositionSample> positions = positionsByCart.get(cartId);
		if (positions == null) {
			return List.of();
		}
		synchronized (positions) {
			return List.copyOf(new ArrayList<>(positions));
		}
	}
}
