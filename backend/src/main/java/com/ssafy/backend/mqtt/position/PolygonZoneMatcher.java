package com.ssafy.backend.mqtt.position;

import java.math.BigDecimal;
import java.util.List;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

@Component
public class PolygonZoneMatcher {

	private static final double EPSILON = 1.0e-9;

	private final ObjectMapper objectMapper;

	public PolygonZoneMatcher(ObjectMapper objectMapper) {
		this.objectMapper = objectMapper;
	}

	public boolean contains(String polygonJson, BigDecimal x, BigDecimal y) {
		List<List<Double>> points = parse(polygonJson);
		if (points.size() < 3) {
			return false;
		}

		double targetX = x.doubleValue();
		double targetY = y.doubleValue();
		boolean inside = false;

		for (int current = 0, previous = points.size() - 1;
			current < points.size();
			previous = current++) {
			Point first = Point.from(points.get(previous));
			Point second = Point.from(points.get(current));
			if (isOnSegment(targetX, targetY, first, second)) {
				return true;
			}
			boolean crosses = (first.y() > targetY) != (second.y() > targetY);
			if (crosses) {
				double intersectionX = (second.x() - first.x())
					* (targetY - first.y())
					/ (second.y() - first.y())
					+ first.x();
				if (targetX < intersectionX) {
					inside = !inside;
				}
			}
		}
		return inside;
	}

	private List<List<Double>> parse(String polygonJson) {
		try {
			return objectMapper.readValue(
				polygonJson,
				new TypeReference<List<List<Double>>>() {
				}
			);
		} catch (JacksonException exception) {
			return List.of();
		}
	}

	private boolean isOnSegment(double x, double y, Point first, Point second) {
		double cross = (x - first.x()) * (second.y() - first.y())
			- (y - first.y()) * (second.x() - first.x());
		if (Math.abs(cross) > EPSILON) {
			return false;
		}
		return x >= Math.min(first.x(), second.x()) - EPSILON
			&& x <= Math.max(first.x(), second.x()) + EPSILON
			&& y >= Math.min(first.y(), second.y()) - EPSILON
			&& y <= Math.max(first.y(), second.y()) + EPSILON;
	}

	private record Point(double x, double y) {

		private static Point from(List<Double> coordinates) {
			if (coordinates.size() < 2) {
				throw new IllegalArgumentException("구역 좌표는 x와 y가 필요합니다.");
			}
			return new Point(coordinates.get(0), coordinates.get(1));
		}
	}
}
