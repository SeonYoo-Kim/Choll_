package com.ssafy.backend.mqtt.position;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.ssafy.backend.map.domain.LibraryMap;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class SlamCoordinateConverterTest {

	@Mock
	private LibraryMap map;

	private final SlamCoordinateConverter converter = new SlamCoordinateConverter();

	private void stubMap(String resolution, String originX, String originY, int height) {
		when(map.getResolution()).thenReturn(new BigDecimal(resolution));
		when(map.getOriginX()).thenReturn(new BigDecimal(originX));
		when(map.getOriginY()).thenReturn(new BigDecimal(originY));
		when(map.getHeight()).thenReturn(height);
	}

	@Test
	void convertsSlamMetersToImagePixelsWithVerticalFlip() {
		// resolution 0.05 m/px, origin (-10, -10), 이미지 높이 600px
		stubMap("0.05", "-10", "-10", 600);

		// SLAM (0, 0)m → 픽셀 ((0-(-10))/0.05, 600-(0-(-10))/0.05) = (200, 400)
		SlamCoordinateConverter.ImagePosition result = converter.toImagePixels(
			BigDecimal.ZERO,
			BigDecimal.ZERO,
			map
		);

		assertThat(result.x()).isEqualByComparingTo("200");
		assertThat(result.y()).isEqualByComparingTo("400");
	}

	@Test
	void mapsOriginToBottomLeftPixel() {
		stubMap("0.05", "-10", "-10", 600);

		// SLAM 원점(-10, -10)m = 이미지 좌하단 (0, 600)
		SlamCoordinateConverter.ImagePosition result = converter.toImagePixels(
			new BigDecimal("-10"),
			new BigDecimal("-10"),
			map
		);

		assertThat(result.x()).isEqualByComparingTo("0");
		assertThat(result.y()).isEqualByComparingTo("600");
	}

	@Test
	void increasingSlamYMovesUpInImage() {
		stubMap("0.1", "0", "0", 500);

		SlamCoordinateConverter.ImagePosition low = converter.toImagePixels(
			BigDecimal.ONE, new BigDecimal("1"), map);
		SlamCoordinateConverter.ImagePosition high = converter.toImagePixels(
			BigDecimal.ONE, new BigDecimal("2"), map);

		// SLAM y가 커질수록(위로 갈수록) 이미지 y는 작아져야 한다
		assertThat(high.y()).isLessThan(low.y());
	}

	@Test
	void convertsImagePixelsToSlamMetersWithVerticalFlip() {
		stubMap("0.05", "-10", "-10", 600);

		// 픽셀 (775, 505) → SLAM (-10 + 775*0.05, -10 + (600-505)*0.05) = (28.75, -5.25)
		SlamCoordinateConverter.SlamPosition result = converter.toSlamMeters(
			new BigDecimal("775"),
			new BigDecimal("505"),
			map
		);

		assertThat(result.x()).isEqualByComparingTo("28.75");
		assertThat(result.y()).isEqualByComparingTo("-5.25");
	}

	@Test
	void pixelToMetersRoundTripsBackToSamePixel() {
		stubMap("0.05", "-10", "-10", 600);
		SlamCoordinateConverter.SlamPosition meters = converter.toSlamMeters(
			new BigDecimal("200"),
			new BigDecimal("400"),
			map
		);

		SlamCoordinateConverter.ImagePosition pixels = converter.toImagePixels(
			meters.x(),
			meters.y(),
			map
		);

		assertThat(pixels.x()).isEqualByComparingTo("200");
		assertThat(pixels.y()).isEqualByComparingTo("400");
	}
}
