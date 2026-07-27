package com.ssafy.backend.bookcopy.service;

import com.ssafy.backend.book.domain.Book;
import com.ssafy.backend.book.repository.BookRepository;
import com.ssafy.backend.bookcopy.domain.BookCopy;
import com.ssafy.backend.bookcopy.domain.BookCopyStatus;
import com.ssafy.backend.bookcopy.repository.BookCopyRepository;
import com.ssafy.backend.bookshelf.domain.Bookshelf;
import com.ssafy.backend.bookshelf.service.BookshelfService;
import com.ssafy.backend.common.exception.DuplicateResourceException;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class BookCopyService {

	private final BookCopyRepository repository;
	private final BookRepository bookRepository;
	private final BookshelfService bookshelfService;

	public BookCopyService(
		BookCopyRepository repository,
		BookRepository bookRepository,
		BookshelfService bookshelfService
	) {
		this.repository = repository;
		this.bookRepository = bookRepository;
		this.bookshelfService = bookshelfService;
	}

	@Transactional
	public Response create(Request request) {
		validateDuplicates(request, null);
		Book book = getBook(request.bookId());
		Bookshelf bookshelf = resolveBookshelf(request.bookshelfId());
		BookCopy bookCopy = new BookCopy(
			book,
			request.libraryBookId(),
			normalizeNullable(request.rfidUid()),
			request.callNumber(),
			request.libraryName(),
			request.roomName(),
			bookshelf,
			request.status()
		);
		return Response.from(repository.save(bookCopy));
	}

	public List<Response> findAll(Long bookId, Long bookshelfId) {
		List<BookCopy> copies;
		if (bookId != null && bookshelfId != null) {
			copies = repository.findAllByBookIdAndBookshelfIdOrderByLibraryBookIdAsc(
				bookId,
				bookshelfId
			);
		} else if (bookId != null) {
			copies = repository.findAllByBookIdOrderByLibraryBookIdAsc(bookId);
		} else if (bookshelfId != null) {
			copies = repository.findAllByBookshelfIdOrderByLibraryBookIdAsc(bookshelfId);
		} else {
			copies = repository.findAll(Sort.by("libraryBookId").ascending());
		}
		return copies.stream().map(Response::from).toList();
	}

	public Response findById(Long id) {
		return Response.from(getBookCopy(id));
	}

	@Transactional
	public Response update(Long id, Request request) {
		BookCopy bookCopy = getBookCopy(id);
		validateDuplicates(request, id);
		Book book = getBook(request.bookId());
		Bookshelf bookshelf = resolveBookshelf(request.bookshelfId());
		bookCopy.update(
			book,
			request.libraryBookId(),
			normalizeNullable(request.rfidUid()),
			request.callNumber(),
			request.libraryName(),
			request.roomName(),
			bookshelf,
			request.status()
		);
		return Response.from(bookCopy);
	}

	@Transactional
	public void delete(Long id) {
		repository.delete(getBookCopy(id));
	}

	private BookCopy getBookCopy(Long id) {
		return repository.findById(id)
			.orElseThrow(() -> new ResourceNotFoundException("소장 도서", id));
	}

	private Book getBook(Long id) {
		return bookRepository.findById(id)
			.orElseThrow(() -> new ResourceNotFoundException("도서", id));
	}

	private Bookshelf resolveBookshelf(Long id) {
		return id == null ? null : bookshelfService.getBookshelf(id);
	}

	private void validateDuplicates(Request request, Long id) {
		boolean duplicatedLibraryBookId = id == null
			? repository.existsByLibraryBookId(request.libraryBookId())
			: repository.existsByLibraryBookIdAndIdNot(request.libraryBookId(), id);
		if (duplicatedLibraryBookId) {
			throw new DuplicateResourceException(
				"이미 사용 중인 도서 등록번호입니다. libraryBookId=" + request.libraryBookId()
			);
		}

		String rfidUid = normalizeNullable(request.rfidUid());
		if (rfidUid == null) {
			return;
		}

		boolean duplicatedRfid = id == null
			? repository.existsByRfidUid(rfidUid)
			: repository.existsByRfidUidAndIdNot(rfidUid, id);
		if (duplicatedRfid) {
			throw new DuplicateResourceException("이미 사용 중인 RFID UID입니다. rfidUid=" + rfidUid);
		}
	}

	private String normalizeNullable(String value) {
		return value == null || value.isBlank() ? null : value.trim();
	}

	public record Request(
		@NotNull
		Long bookId,

		@NotBlank
		@Size(max = 100)
		String libraryBookId,

		@Size(max = 100)
		String rfidUid,

		@NotBlank
		@Size(max = 255)
		String callNumber,

		@NotBlank
		@Size(max = 100)
		String libraryName,

		@NotBlank
		@Size(max = 100)
		String roomName,

		Long bookshelfId,

		@NotNull
		BookCopyStatus status
	) {
	}

	public record Response(
		Long id,
		Long bookId,
		String isbn,
		String title,
		String libraryBookId,
		String rfidUid,
		String callNumber,
		String libraryName,
		String roomName,
		Long bookshelfId,
		String bookshelfNumber,
		BookCopyStatus status
	) {
		public static Response from(BookCopy copy) {
			Bookshelf bookshelf = copy.getBookshelf();
			return new Response(
				copy.getId(),
				copy.getBook().getId(),
				copy.getBook().getIsbn(),
				copy.getBook().getTitle(),
				copy.getLibraryBookId(),
				copy.getRfidUid(),
				copy.getCallNumber(),
				copy.getLibraryName(),
				copy.getRoomName(),
				bookshelf == null ? null : bookshelf.getId(),
				bookshelf == null ? null : bookshelf.getShelfNumber(),
				copy.getStatus()
			);
		}
	}
}
