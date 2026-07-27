package com.ssafy.backend.book.service;

import com.ssafy.backend.book.domain.Book;
import com.ssafy.backend.book.repository.BookRepository;
import com.ssafy.backend.bookcopy.repository.BookCopyRepository;
import com.ssafy.backend.classification.domain.ClassificationSection;
import com.ssafy.backend.classification.service.ClassificationSectionService;
import com.ssafy.backend.common.exception.DuplicateResourceException;
import com.ssafy.backend.common.exception.InvalidDomainException;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class BookService {

	private final BookRepository repository;
	private final BookCopyRepository bookCopyRepository;
	private final ClassificationSectionService classificationSectionService;

	public BookService(
		BookRepository repository,
		BookCopyRepository bookCopyRepository,
		ClassificationSectionService classificationSectionService
	) {
		this.repository = repository;
		this.bookCopyRepository = bookCopyRepository;
		this.classificationSectionService = classificationSectionService;
	}

	@Transactional
	public Response create(Request request) {
		String isbn = normalizeNullable(request.isbn());
		validateDuplicateIsbn(isbn, null);
		ClassificationSection section = classificationSectionService.getSection(
			request.classificationSectionId()
		);
		validateClassificationRange(section, request.classificationNumber());
		Book book = new Book(
			isbn,
			request.title(),
			normalizeNullable(request.author()),
			normalizeNullable(request.publisher()),
			request.publicationYear(),
			request.classificationCode(),
			request.classificationNumber(),
			section
		);
		return Response.from(repository.save(book));
	}

	public List<Response> findAll() {
		return repository.findAll(Sort.by("classificationNumber").ascending())
			.stream()
			.map(Response::from)
			.toList();
	}

	public Response findById(Long id) {
		return Response.from(getBook(id));
	}

	@Transactional
	public Response update(Long id, Request request) {
		Book book = getBook(id);
		String isbn = normalizeNullable(request.isbn());
		validateDuplicateIsbn(isbn, id);
		ClassificationSection section = classificationSectionService.getSection(
			request.classificationSectionId()
		);
		validateClassificationRange(section, request.classificationNumber());
		book.update(
			isbn,
			request.title(),
			normalizeNullable(request.author()),
			normalizeNullable(request.publisher()),
			request.publicationYear(),
			request.classificationCode(),
			request.classificationNumber(),
			section
		);
		return Response.from(book);
	}

	@Transactional
	public void delete(Long id) {
		if (bookCopyRepository.existsByBookId(id)) {
			throw new InvalidDomainException("소장 도서가 연결된 도서 정보는 삭제할 수 없습니다.");
		}
		repository.delete(getBook(id));
	}

	public Book getBook(Long id) {
		return repository.findById(id)
			.orElseThrow(() -> new ResourceNotFoundException("도서", id));
	}

	private void validateDuplicateIsbn(String isbn, Long id) {
		if (isbn == null) {
			return;
		}

		boolean exists = id == null
			? repository.existsByIsbn(isbn)
			: repository.existsByIsbnAndIdNot(isbn, id);
		if (exists) {
			throw new DuplicateResourceException("이미 등록된 ISBN입니다. isbn=" + isbn);
		}
	}

	private String normalizeNullable(String value) {
		return value == null || value.isBlank() ? null : value.trim();
	}

	private void validateClassificationRange(
		ClassificationSection section,
		BigDecimal classificationNumber
	) {
		boolean outsideRange = classificationNumber.compareTo(section.getStartNumber()) < 0
			|| classificationNumber.compareTo(section.getEndNumber()) > 0;
		if (outsideRange) {
			throw new InvalidDomainException(
				"도서 분류번호가 선택한 분류 섹터의 범위를 벗어났습니다."
			);
		}
	}

	public record Request(
		@Size(max = 13)
		@Pattern(regexp = "^$|\\d{10}|\\d{13}$", message = "ISBN은 10자리 또는 13자리 숫자여야 합니다.")
		String isbn,

		@NotBlank
		@Size(max = 255)
		String title,

		@Size(max = 255)
		String author,

		@Size(max = 255)
		String publisher,

		@Positive
		Integer publicationYear,

		@NotBlank
		@Size(max = 20)
		@Pattern(regexp = "\\d{3}(\\.\\d+)?", message = "000 또는 813.7 형식이어야 합니다.")
		String classificationCode,

		@NotNull
		@DecimalMin("0")
		BigDecimal classificationNumber,

		@NotNull
		Long classificationSectionId
	) {
	}

	public record Response(
		Long id,
		String isbn,
		String title,
		String author,
		String publisher,
		Integer publicationYear,
		String classificationCode,
		BigDecimal classificationNumber,
		Long classificationSectionId,
		String classificationSectionCode
	) {
		public static Response from(Book book) {
			return new Response(
				book.getId(),
				book.getIsbn(),
				book.getTitle(),
				book.getAuthor(),
				book.getPublisher(),
				book.getPublicationYear(),
				book.getClassificationCode(),
				book.getClassificationNumber(),
				book.getClassificationSection().getId(),
				book.getClassificationSection().getCode()
			);
		}
	}
}
