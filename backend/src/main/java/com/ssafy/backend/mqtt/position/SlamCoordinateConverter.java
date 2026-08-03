package com.ssafy.backend.mqtt.position;

import com.ssafy.backend.map.domain.LibraryMap;
import java.math.BigDecimal;
import java.math.RoundingMode;
import org.springframework.stereotype.Component;

/**
 * SLAM 세계 좌표(미터)를 지도 이미지 픽셀 좌표(좌상단 원점)로 변환한다.
 * ROS 지도 규약: origin은 이미지 좌하단 픽셀의 세계 좌표, y축은 위쪽이 양수 —
 * 이미지 픽셀은 y축이 아래쪽이므로 세로축을 뒤집는다.
 *
 *   픽셀x = (slam_x - originX) / resolution
 *   픽셀y = imageHeight - (slam_y - originY) / resolution
 */
@Component
public class SlamCoordinateConverter {

	private static final int PIXEL_SCALE = 2;

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

	public record ImagePosition(BigDecimal x, BigDecimal y) {
	}
}
