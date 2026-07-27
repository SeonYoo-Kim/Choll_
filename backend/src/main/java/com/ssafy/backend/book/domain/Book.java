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
	uniqueConstraints = {
		@UniqueConstraint(name = "uk_book_library_book_id", columnNames = "library_book_id"),
		@UniqueConstraint(name = "uk_book_rfid_uid", columnNames = "rfid_uid")
	}
)
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Book {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@Column(name = "library_book_id", nullable = false, length = 100)
	private String libraryBookId;

	@Column(nullable = false, length = 255)
	private String title;

	@Column(name = "rfid_uid", nullable = false, length = 100)
	private String rfidUid;

	@Column(name = "call_number", nullable = false, length = 100)
	private String callNumber;

	@Column(name = "classification_code", nullable = false, length = 20)
	private String classificationCode;

	@Column(name = "classification_number", nullable = false, precision = 10, scale = 5)
	private BigDecimal classificationNumber;

	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	@JoinColumn(name = "classification_section_id", nullable = false)
	private ClassificationSection classificationSection;

	public Book(
		String libraryBookId,
		String title,
		String rfidUid,
		String callNumber,
		String classificationCode,
		BigDecimal classificationNumber,
		ClassificationSection classificationSection
	) {
		update(
			libraryBookId,
			title,
			rfidUid,
			callNumber,
			classificationCode,
			classificationNumber,
			classificationSection
		);
	}

	public void update(
		String libraryBookId,
		String title,
		String rfidUid,
		String callNumber,
		String classificationCode,
		BigDecimal classificationNumber,
		ClassificationSection classificationSection
	) {
		this.libraryBookId = libraryBookId;
		this.title = title;
		this.rfidUid = rfidUid;
		this.callNumber = callNumber;
		this.classificationCode = classificationCode;
		this.classificationNumber = classificationNumber;
		this.classificationSection = classificationSection;
	}
}
