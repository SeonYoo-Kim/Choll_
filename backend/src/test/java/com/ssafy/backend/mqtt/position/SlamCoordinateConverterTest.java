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

	/**
	 * 좌우반전+회전이 섞인 평면도용 아핀 변환 (캘리브레이션 값).
	 * 예시: 90도 회전 + 반전이 섞인 A=[[0,180],[180,0]], t=(100,50) —
	 * 행렬식 -32400(<0, 반전 포함)으로 기존 세로반전식으로는 표현 불가한 변환이다.
	 */
	private void stubAffine() {
		when(map.hasAffineTransform()).thenReturn(true);
		when(map.getAffineA11()).thenReturn(new BigDecimal("0"));
		when(map.getAffineA12()).thenReturn(new BigDecimal("180"));
		when(map.getAffineA21()).thenReturn(new BigDecimal("180"));
		when(map.getAffineA22()).thenReturn(new BigDecimal("0"));
		when(map.getAffineTx()).thenReturn(new BigDecimal("100"));
		when(map.getAffineTy()).thenReturn(new BigDecimal("50"));
	}

	@Test
	void affineTransformTakesPrecedenceOverLegacyFormula() {
		stubAffine();

		// world (2, 1) → 픽셀 (0·2 + 180·1 + 100, 180·2 + 0·1 + 50) = (280, 410)
		SlamCoordinateConverter.ImagePosition result = converter.toImagePixels(
			new BigDecimal("2"),
			new BigDecimal("1"),
			map
		);

		assertThat(result.x()).isEqualByComparingTo("280");
		assertThat(result.y()).isEqualByComparingTo("410");
	}

	@Test
	void affineRoundTripsPixelToMetersAndBack() {
		stubAffine();

		SlamCoordinateConverter.SlamPosition meters = converter.toSlamMeters(
			new BigDecimal("925"),
			new BigDecimal("138"),
			map
		);
		SlamCoordinateConverter.ImagePosition pixels = converter.toImagePixels(
			meters.x(),
			meters.y(),
			map
		);

		assertThat(pixels.x().doubleValue()).isCloseTo(925.0, org.assertj.core.data.Offset.offset(0.5));
		assertThat(pixels.y().doubleValue()).isCloseTo(138.0, org.assertj.core.data.Offset.offset(0.5));
	}

	@Test
	void degenerateAffineFailsLoudlyInsteadOfProducingGarbage() {
		when(map.hasAffineTransform()).thenReturn(true);
		when(map.getAffineA11()).thenReturn(BigDecimal.ONE);
		when(map.getAffineA12()).thenReturn(BigDecimal.ONE);
		when(map.getAffineA21()).thenReturn(BigDecimal.ONE);
		when(map.getAffineA22()).thenReturn(BigDecimal.ONE);

		org.assertj.core.api.Assertions.assertThatThrownBy(() ->
			converter.toSlamMeters(BigDecimal.ONE, BigDecimal.ONE, map)
		).isInstanceOf(IllegalStateException.class);
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
