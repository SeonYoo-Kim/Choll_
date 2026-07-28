package com.ssafy.backend.bookshelf.domain;

import com.ssafy.backend.zone.domain.Zone;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.math.BigDecimal;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@Entity
@Table(
	name = "bookshelves",
	uniqueConstraints = @UniqueConstraint(
		name = "uk_bookshelf_zone_number",
		columnNames = {"zone_id", "shelf_number"}
	)
)
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Bookshelf {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	@JoinColumn(name = "zone_id", nullable = false)
	private Zone zone;

	@Column(name = "shelf_number", nullable = false, length = 50)
	private String shelfNumber;

	@Column(nullable = false, length = 100)
	private String name;

	@Column(nullable = false, precision = 12, scale = 6)
	private BigDecimal x;

	@Column(nullable = false, precision = 12, scale = 6)
	private BigDecimal y;

	@Column(name = "display_order", nullable = false)
	private int displayOrder;

	public Bookshelf(
		Zone zone,
		String shelfNumber,
		String name,
		BigDecimal x,
		BigDecimal y,
		int displayOrder
	) {
		update(zone, shelfNumber, name, x, y, displayOrder);
	}

	public void update(
		Zone zone,
		String shelfNumber,
		String name,
		BigDecimal x,
		BigDecimal y,
		int displayOrder
	) {
		this.zone = zone;
		this.shelfNumber = shelfNumber;
		this.name = name;
		this.x = x;
		this.y = y;
		this.displayOrder = displayOrder;
	}
}
