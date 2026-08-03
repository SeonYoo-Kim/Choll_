package com.ssafy.backend.mqtt.position;

import com.ssafy.backend.map.domain.LibraryMap;
import java.math.BigDecimal;
import java.math.RoundingMode;
import org.springframework.stereotype.Component;

/**
 * SLAM 세계 좌표(미터) ↔ 지도 이미지 픽셀 좌표(좌상단 원점) 상호 변환.
 * ROS 지도 규약: origin은 이미지 좌하단 픽셀의 세계 좌표, y축은 위쪽이 양수 —
 * 이미지 픽셀은 y축이 아래쪽이므로 세로축을 뒤집는다.
 *
 *   픽셀x = (slam_x - originX) / resolution
 *   픽셀y = imageHeight - (slam_y - originY) / resolution
 */
@Component
public class SlamCoordinateConverter {

	private static final int PIXEL_SCALE = 2;
	private static final int METER_SCALE = 3;

	public ImagePosition toImagePixels(BigDecimal x, BigDecimal y, LibraryMap map) {
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

	public record ImagePosition(BigDecimal x, BigDecimal y) {
	}

	public record SlamPosition(BigDecimal x, BigDecimal y) {
	}
}
