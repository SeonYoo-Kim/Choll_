package com.ssafy.backend.bookshelfrange.domain;

import com.ssafy.backend.bookshelf.domain.Bookshelf;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@Entity
@Table(name = "bookshelf_ranges")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class BookshelfRange {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	@JoinColumn(name = "bookshelf_id", nullable = false)
	private Bookshelf bookshelf;

	@Column(name = "start_number", nullable = false, precision = 10, scale = 5)
	private BigDecimal startNumber;

	@Column(name = "end_number", nullable = false, precision = 10, scale = 5)
	private BigDecimal endNumber;

	public BookshelfRange(
		Bookshelf bookshelf,
		BigDecimal startNumber,
		BigDecimal endNumber
	) {
		update(bookshelf, startNumber, endNumber);
	}

	public void update(
		Bookshelf bookshelf,
		BigDecimal startNumber,
		BigDecimal endNumber
	) {
		this.bookshelf = bookshelf;
		this.startNumber = startNumber;
		this.endNumber = endNumber;
	}
}
