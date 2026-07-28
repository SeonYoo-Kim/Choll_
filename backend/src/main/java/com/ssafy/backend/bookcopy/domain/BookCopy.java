package com.ssafy.backend.bookcopy.domain;

import com.ssafy.backend.book.domain.Book;
import com.ssafy.backend.bookshelf.domain.Bookshelf;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@Entity
@Table(
	name = "book_copies",
	uniqueConstraints = {
		@UniqueConstraint(name = "uk_book_copy_library_book_id", columnNames = "library_book_id"),
		@UniqueConstraint(name = "uk_book_copy_rfid_uid", columnNames = "rfid_uid")
	}
)
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class BookCopy {

	@Id
	@GeneratedValue(strategy = GenerationType.IDENTITY)
	private Long id;

	@ManyToOne(fetch = FetchType.LAZY, optional = false)
	@JoinColumn(name = "book_id", nullable = false)
	private Book book;

	@Column(name = "library_book_id", nullable = false, length = 100)
	private String libraryBookId;

	@Column(name = "rfid_uid", length = 100)
	private String rfidUid;

	@Column(name = "call_number", nullable = false, length = 255)
	private String callNumber;

	@Column(name = "library_name", nullable = false, length = 100)
	private String libraryName;

	@Column(name = "room_name", nullable = false, length = 100)
	private String roomName;

	@ManyToOne(fetch = FetchType.LAZY)
	@JoinColumn(name = "bookshelf_id")
	private Bookshelf bookshelf;

	@Enumerated(EnumType.STRING)
	@Column(nullable = false, length = 20)
	private BookCopyStatus status;

	public BookCopy(
		Book book,
		String libraryBookId,
		String rfidUid,
		String callNumber,
		String libraryName,
		String roomName,
		Bookshelf bookshelf,
		BookCopyStatus status
	) {
		update(
			book,
			libraryBookId,
			rfidUid,
			callNumber,
			libraryName,
			roomName,
			bookshelf,
			status
		);
	}

	public void update(
		Book book,
		String libraryBookId,
		String rfidUid,
		String callNumber,
		String libraryName,
		String roomName,
		Bookshelf bookshelf,
		BookCopyStatus status
	) {
		this.book = book;
		this.libraryBookId = libraryBookId;
		this.rfidUid = rfidUid;
		this.callNumber = callNumber;
		this.libraryName = libraryName;
		this.roomName = roomName;
		this.bookshelf = bookshelf;
		this.status = status;
	}
}
