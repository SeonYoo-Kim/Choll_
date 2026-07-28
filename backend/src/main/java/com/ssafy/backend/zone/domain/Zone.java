package com.ssafy.backend.zone.domain;

import com.ssafy.backend.map.domain.LibraryMap;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Lob;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@Entity
@Table(
	name = "zones",
	uniqueConstraints = @UniqueConstraint(
		name = "uk_zone_map_code",
		columnNames = {"map_id", "code"}
	)
)
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Zone {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	@JoinColumn(name = "map_id", nullable = false)
	private LibraryMap map;

	@Column(nullable = false, length = 50)
	private String code;

	@Column(nullable = false, length = 100)
	private String name;

	@Lob
	@Column(name = "polygon_json", nullable = false, columnDefinition = "TEXT")
	private String polygonJson;

	public Zone(LibraryMap map, String code, String name, String polygonJson) {
		update(map, code, name, polygonJson);
	}

	public void update(LibraryMap map, String code, String name, String polygonJson) {
		this.map = map;
		this.code = code;
		this.name = name;
		this.polygonJson = polygonJson;
	}
}
