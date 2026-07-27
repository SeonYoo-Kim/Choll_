package com.ssafy.backend.book.domain;

import com.ssafy.backend.classification.domain.ClassificationSection;
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
	name = "books",
	uniqueConstraints = @UniqueConstraint(name = "uk_book_isbn", columnNames = "isbn")
)
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Book {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@Column(length = 13)
	private String isbn;

	@Column(nullable = false, length = 255)
	private String title;

	@Column(length = 255)
	private String author;

	@Column(length = 255)
	private String publisher;

	@Column(name = "publication_year")
	private Integer publicationYear;

	@Column(name = "classification_code", nullable = false, length = 20)
	private String classificationCode;

	@Column(name = "classification_number", nullable = false, precision = 10, scale = 5)
	private BigDecimal classificationNumber;

	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	@JoinColumn(name = "classification_section_id", nullable = false)
	private ClassificationSection classificationSection;

	public Book(
		String isbn,
		String title,
		String author,
		String publisher,
		Integer publicationYear,
		String classificationCode,
		BigDecimal classificationNumber,
		ClassificationSection classificationSection
	) {
		update(
			isbn,
			title,
			author,
			publisher,
			publicationYear,
			classificationCode,
			classificationNumber,
			classificationSection
		);
	}

	public void update(
		String isbn,
		String title,
		String author,
		String publisher,
		Integer publicationYear,
		String classificationCode,
		BigDecimal classificationNumber,
		ClassificationSection classificationSection
	) {
		this.isbn = isbn;
		this.title = title;
		this.author = author;
		this.publisher = publisher;
		this.publicationYear = publicationYear;
		this.classificationCode = classificationCode;
		this.classificationNumber = classificationNumber;
		this.classificationSection = classificationSection;
	}
}
