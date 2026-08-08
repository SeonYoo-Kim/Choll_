package com.ssafy.backend.map.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.math.BigDecimal;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@Entity
@Table(
	name = "library_maps",
	uniqueConstraints = @UniqueConstraint(name = "uk_library_map_name", columnNames = "name")
)
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class LibraryMap {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@Column(nullable = false, length = 100)
	private String name;

	@Column(name = "image_url", nullable = false, length = 500)
	private String imageUrl;

	@Column(nullable = false, precision = 12, scale = 6)
	private BigDecimal resolution;

	@Column(name = "origin_x", nullable = false, precision = 12, scale = 6)
	private BigDecimal originX;

	@Column(name = "origin_y", nullable = false, precision = 12, scale = 6)
	private BigDecimal originY;

	@Column(nullable = false)
	private int width;

	@Column(nullable = false)
	private int height;

	/*
	 * SLAM 세계 좌표(미터) → 지도 이미지 픽셀의 일반 아핀 변환 (2026-08-07):
	 *
	 *   픽셀x = a11·wx + a12·wy + tx
	 *   픽셀y = a21·wx + a22·wy + ty
	 *
	 * 평면도가 SLAM 지도에서 회전·좌우반전·크롭을 거쳐 만들어져, 기존
	 * resolution·origin(배율+이동+세로반전)만으로는 표현할 수 없다.
	 * 여섯 값이 모두 채워졌을 때만 사용하고, 하나라도 null이면 기존 방식으로 동작한다.
	 * 값은 REST가 아니라 캘리브레이션(scripts/calibrate_map_transform.py)이 뽑은 SQL로 넣는다.
	 */
	@Column(name = "affine_a11", precision = 18, scale = 9)
	private BigDecimal affineA11;

	@Column(name = "affine_a12", precision = 18, scale = 9)
	private BigDecimal affineA12;

	@Column(name = "affine_a21", precision = 18, scale = 9)
	private BigDecimal affineA21;

	@Column(name = "affine_a22", precision = 18, scale = 9)
	private BigDecimal affineA22;

	@Column(name = "affine_tx", precision = 18, scale = 9)
	private BigDecimal affineTx;

	@Column(name = "affine_ty", precision = 18, scale = 9)
	private BigDecimal affineTy;

	/** 캘리브레이션된 아핀 변환이 있는가 — 있으면 좌표 변환은 이 값을 쓴다 */
	public boolean hasAffineTransform() {
		return affineA11 != null && affineA12 != null && affineA21 != null
			&& affineA22 != null && affineTx != null && affineTy != null;
	}

	public LibraryMap(
		String name,
		String imageUrl,
		BigDecimal resolution,
		BigDecimal originX,
		BigDecimal originY,
		int width,
		int height
	) {
		update(name, imageUrl, resolution, originX, originY, width, height);
	}

	public void update(
		String name,
		String imageUrl,
		BigDecimal resolution,
		BigDecimal originX,
		BigDecimal originY,
		int width,
		int height
	) {
		this.name = name;
		this.imageUrl = imageUrl;
		this.resolution = resolution;
		this.originX = originX;
		this.originY = originY;
		this.width = width;
		this.height = height;
	}
}
