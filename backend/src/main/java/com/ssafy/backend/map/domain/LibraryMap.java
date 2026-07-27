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
