package com.ssafy.backend.mqtt.position;

import com.ssafy.backend.map.domain.LibraryMap;
import java.math.BigDecimal;
import java.math.RoundingMode;
import org.springframework.stereotype.Component;

/**
 * SLAM 세계 좌표(미터) ↔ 지도 이미지 픽셀 좌표(좌상단 원점) 상호 변환.
 *
 * 기본 방식(ROS 지도 규약): origin은 이미지 좌하단 픽셀의 세계 좌표, y축은 위쪽이 양수 —
 * 이미지 픽셀은 y축이 아래쪽이므로 세로축을 뒤집는다.
 *
 *   픽셀x = (slam_x - originX) / resolution
 *   픽셀y = imageHeight - (slam_y - originY) / resolution
 *
 * 캘리브레이션 방식(2026-08-07): FE 평면도가 SLAM 지도에서 **회전·좌우반전·크롭**을 거쳐
 * 만들어진 경우 위 식으로는 표현할 수 없다. LibraryMap에 아핀 6계수가 채워져 있으면
 * (hasAffineTransform) 그 변환을 우선 사용한다:
 *
 *   픽셀 = A·세계좌표 + t,   세계좌표 = A⁻¹·(픽셀 - t)
 *
 * 계수는 scripts/calibrate_map_transform.py가 대응점들로부터 계산해 SQL로 넣는다.
 */
@Component
public class SlamCoordinateConverter {

	private static final int PIXEL_SCALE = 2;
	private static final int METER_SCALE = 3;
	private static final double DETERMINANT_EPSILON = 1.0e-9;

	public ImagePosition toImagePixels(BigDecimal x, BigDecimal y, LibraryMap map) {
		if (map.hasAffineTransform()) {
			double wx = x.doubleValue();
			double wy = y.doubleValue();
			double px = map.getAffineA11().doubleValue() * wx
				+ map.getAffineA12().doubleValue() * wy
				+ map.getAffineTx().doubleValue();
			double py = map.getAffineA21().doubleValue() * wx
				+ map.getAffineA22().doubleValue() * wy
				+ map.getAffineTy().doubleValue();
			return new ImagePosition(roundPixel(px), roundPixel(py));
		}
		BigDecimal pixelX = x.subtract(map.getOriginX())
			.divide(map.getResolution(), PIXEL_SCALE, RoundingMode.HALF_UP);
		BigDecimal pixelY = BigDecimal.valueOf(map.getHeight())
			.subtract(
				y.subtract(map.getOriginY())
					.divide(map.getResolution(), PIXEL_SCALE, RoundingMode.HALF_UP)
			);
		return new ImagePosition(pixelX, pixelY);
	}

	/** 지도 이미지 픽셀 → SLAM 세계 좌표(미터). 이동 명령 하행(cmd/move/cart)에 사용. */
	public SlamPosition toSlamMeters(BigDecimal pixelX, BigDecimal pixelY, LibraryMap map) {
		if (map.hasAffineTransform()) {
			double a11 = map.getAffineA11().doubleValue();
			double a12 = map.getAffineA12().doubleValue();
			double a21 = map.getAffineA21().doubleValue();
			double a22 = map.getAffineA22().doubleValue();
			double determinant = a11 * a22 - a12 * a21;
			if (Math.abs(determinant) < DETERMINANT_EPSILON) {
				// 역행렬이 없으면 캘리브레이션 값이 잘못 들어간 것 — 조용히 엉뚱한 좌표를
				// 만들지 말고 설정 오류로 끊는다 (대응점을 다시 찍어야 한다)
				throw new IllegalStateException(
					"지도 %d의 아핀 계수가 퇴화(행렬식 0)입니다. 캘리브레이션을 다시 하세요."
						.formatted(map.getId())
				);
			}
			double dx = pixelX.doubleValue() - map.getAffineTx().doubleValue();
			double dy = pixelY.doubleValue() - map.getAffineTy().doubleValue();
			double wx = (a22 * dx - a12 * dy) / determinant;
			double wy = (-a21 * dx + a11 * dy) / determinant;
			return new SlamPosition(roundMeter(wx), roundMeter(wy));
		}
		BigDecimal x = map.getOriginX()
			.add(pixelX.multiply(map.getResolution()))
			.setScale(METER_SCALE, RoundingMode.HALF_UP);
		BigDecimal y = map.getOriginY()
			.add(
				BigDecimal.valueOf(map.getHeight())
					.subtract(pixelY)
					.multiply(map.getResolution())
			)
			.setScale(METER_SCALE, RoundingMode.HALF_UP);
		return new SlamPosition(x, y);
	}

	/**
	 * SLAM 진행 방향(yaw, 라디안 CCW+) → 지도 이미지 기준 방향(라디안, 이미지 y축이 아래라 CW+).
	 *
	 * 위치와 마찬가지로 방향도 좌표 변환을 거쳐야 한다 — 평면도가 회전·반전 파생본이면
	 * 세계 기준 0 rad(동쪽)가 화면에서는 동쪽이 아니다. 방향 벡터 (cos, sin)에 변환의
	 * 선형부만 적용하고(평행이동은 방향에 무의미) 다시 각도로 되돌린다.
	 * FE는 이 값을 CSS rotate(rad)로 그대로 쓴다 (화면 좌표도 y가 아래라 부호 규약이 같다).
	 */
	public BigDecimal toImageYaw(BigDecimal yaw, LibraryMap map) {
		double radians = yaw.doubleValue();
		double vx = Math.cos(radians);
		double vy = Math.sin(radians);
		double px;
		double py;
		if (map.hasAffineTransform()) {
			px = map.getAffineA11().doubleValue() * vx + map.getAffineA12().doubleValue() * vy;
			py = map.getAffineA21().doubleValue() * vx + map.getAffineA22().doubleValue() * vy;
		} else {
			// 기본식은 세로반전뿐 — 이미지에서는 y 부호만 뒤집힌다
			px = vx;
			py = -vy;
		}
		return BigDecimal.valueOf(Math.atan2(py, px)).setScale(4, RoundingMode.HALF_UP);
	}

	private static BigDecimal roundPixel(double value) {
		return BigDecimal.valueOf(value).setScale(PIXEL_SCALE, RoundingMode.HALF_UP);
	}

	private static BigDecimal roundMeter(double value) {
		return BigDecimal.valueOf(value).setScale(METER_SCALE, RoundingMode.HALF_UP);
	}

	public record ImagePosition(BigDecimal x, BigDecimal y) {
	}

	public record SlamPosition(BigDecimal x, BigDecimal y) {
	}
}
