package com.ssafy.backend.mqtt.position;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * 구역 폴리곤(zones.polygon_json) 포함 판정.
 * 좌표계는 지도 이미지 픽셀(좌상단 원점) — 카트 좌표가 SLAM 미터에서 변환된 그 공간이다.
 */
@Component
public class PolygonZoneMatcher {

	private static final double EPSILON = 1.0e-9;

	private final ObjectMapper objectMapper;

	public PolygonZoneMatcher(ObjectMapper objectMapper) {
		this.objectMapper = objectMapper;
	}

	/** (x, y)가 폴리곤 안(경계 포함)인가. 폴리곤을 읽을 수 없으면 false. */
	public boolean contains(String polygonJson, BigDecimal x, BigDecimal y) {
		List<Point> vertices = vertices(polygonJson);
		if (vertices.size() < 3) {
			return false;
		}
		return containsPoint(vertices, x.doubleValue(), y.doubleValue());
	}

	/**
	 * 폴리곤 JSON을 꼭짓점 목록으로 읽는다.
	 * 값이 비었거나 형식이 깨졌으면 빈 목록 — 판정을 예외로 끊지 않고 "구역 아님"으로 다룬다.
	 */
	private List<Point> vertices(String polygonJson) {
		if (polygonJson == null || polygonJson.isBlank()) {
			return List.of();
		}
		List<List<Double>> parsed;
		try {
			parsed = objectMapper.readValue(
				polygonJson,
				new TypeReference<List<List<Double>>>() {
				}
			);
		} catch (JacksonException exception) {
			return List.of();
		}
		List<Point> vertices = new ArrayList<>(parsed.size());
		for (List<Double> coordinates : parsed) {
			if (coordinates == null
				|| coordinates.size() < 2
				|| coordinates.get(0) == null
				|| coordinates.get(1) == null) {
				return List.of();
			}
			vertices.add(new Point(coordinates.get(0), coordinates.get(1)));
		}
		return vertices;
	}

	/** ray casting — 경계선 위는 안으로 본다 (구역 경계에서 판정이 비는 것을 막는다) */
	private static boolean containsPoint(List<Point> vertices, double x, double y) {
		boolean inside = false;
		for (int current = 0, previous = vertices.size() - 1;
			current < vertices.size();
			previous = current++) {
			Point first = vertices.get(previous);
			Point second = vertices.get(current);
			if (isOnSegment(x, y, first, second)) {
				return true;
			}
			boolean crosses = (first.y() > y) != (second.y() > y);
			if (crosses) {
				double intersectionX = (second.x() - first.x())
					* (y - first.y())
					/ (second.y() - first.y())
					+ first.x();
				if (x < intersectionX) {
					inside = !inside;
				}
			}
		}
		return inside;
	}

	private static boolean isOnSegment(double x, double y, Point first, Point second) {
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
	}
}
