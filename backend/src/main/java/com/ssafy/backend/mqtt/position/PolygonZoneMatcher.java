package com.ssafy.backend.mqtt.position;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * 구역 폴리곤(zones.polygon_json) 기하 연산.
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
		return containsPoint(vertices(polygonJson), x.doubleValue(), y.doubleValue());
	}

	/**
	 * 폴리곤 안에서 (x, y)에 가장 가까운 지점.
	 *
	 * 이미 폴리곤 안이면 (x, y)를 그대로 돌려준다. 밖이면 경계에서 가장 가까운 점을 찾아
	 * 폴리곤 중심 쪽으로 {@code margin}만큼 당긴다 — 경계는 곧 서가·벽면이라, 그 위를 목적지로
	 * 삼으면 카트가 장애물에 붙어 서려다 실패한다.
	 *
	 * 폴리곤이 깨졌거나 꼭짓점이 3개 미만이면 도형이 되지 않으므로 빈 값. 호출자가 대체 동작을 정한다.
	 */
	public Optional<Point> closestPointInside(
		String polygonJson,
		double x,
		double y,
		double margin
	) {
		List<Point> vertices = vertices(polygonJson);
		if (vertices.size() < 3) {
			return Optional.empty();
		}
		if (containsPoint(vertices, x, y)) {
			return Optional.of(new Point(x, y));
		}
		Point centroid = centroid(vertices);
		Point pulled = movedToward(closestBoundaryPoint(vertices, x, y), centroid, margin);
		// 오목한 폴리곤이면 중심 방향으로 당긴 점이 다시 밖으로 나갈 수 있다 — 그때는 중심으로
		return Optional.of(
			containsPoint(vertices, pulled.x(), pulled.y()) ? pulled : centroid
		);
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
		if (vertices.size() < 3) {
			return false;
		}
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

	/** 모든 변에 대해 수선의 발을 구해 가장 가까운 것을 고른다 */
	private static Point closestBoundaryPoint(List<Point> vertices, double x, double y) {
		Point nearest = vertices.get(0);
		double shortest = Double.MAX_VALUE;
		for (int current = 0, previous = vertices.size() - 1;
			current < vertices.size();
			previous = current++) {
			Point candidate = closestPointOnSegment(
				vertices.get(previous),
				vertices.get(current),
				x,
				y
			);
			double distance = Math.hypot(candidate.x() - x, candidate.y() - y);
			if (distance < shortest) {
				shortest = distance;
				nearest = candidate;
			}
		}
		return nearest;
	}

	private static Point closestPointOnSegment(Point first, Point second, double x, double y) {
		double deltaX = second.x() - first.x();
		double deltaY = second.y() - first.y();
		double lengthSquared = deltaX * deltaX + deltaY * deltaY;
		if (lengthSquared < EPSILON) {
			return first;
		}
		double projection =
			((x - first.x()) * deltaX + (y - first.y()) * deltaY) / lengthSquared;
		double clamped = Math.max(0.0, Math.min(1.0, projection));
		return new Point(first.x() + clamped * deltaX, first.y() + clamped * deltaY);
	}

	private static Point centroid(List<Point> vertices) {
		double sumX = 0.0;
		double sumY = 0.0;
		for (Point vertex : vertices) {
			sumX += vertex.x();
			sumY += vertex.y();
		}
		return new Point(sumX / vertices.size(), sumY / vertices.size());
	}

	/** from에서 to 방향으로 distance만큼 이동한 점. to를 지나치면 to에서 멈춘다. */
	private static Point movedToward(Point from, Point to, double distance) {
		double deltaX = to.x() - from.x();
		double deltaY = to.y() - from.y();
		double length = Math.hypot(deltaX, deltaY);
		if (distance <= 0.0 || length < EPSILON) {
			return from;
		}
		if (distance >= length) {
			return to;
		}
		return new Point(
			from.x() + deltaX / length * distance,
			from.y() + deltaY / length * distance
		);
	}

	/** 지도 이미지 픽셀 좌표의 한 점 */
	public record Point(double x, double y) {
	}
}
