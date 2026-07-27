package com.ssafy.backend.book.service;

import com.ssafy.backend.book.domain.Book;
import com.ssafy.backend.book.repository.BookRepository;
import com.ssafy.backend.classification.domain.ClassificationSection;
import com.ssafy.backend.classification.service.ClassificationSectionService;
import com.ssafy.backend.common.exception.DuplicateResourceException;
import com.ssafy.backend.common.exception.InvalidDomainException;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
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
	private final ClassificationSectionService classificationSectionService;

	public BookService(
		BookRepository repository,
		ClassificationSectionService classificationSectionService
	) {
		this.repository = repository;
		this.classificationSectionService = classificationSectionService;
	}

	@Transactional
	public Response create(Request request) {
		validateDuplicates(request, null);
		ClassificationSection section = classificationSectionService.getSection(
			request.classificationSectionId()
		);
		validateClassificationRange(section, request.classificationNumber());
		Book book = new Book(
			request.libraryBookId(),
			request.title(),
			request.rfidUid(),
			request.callNumber(),
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
		validateDuplicates(request, id);
		ClassificationSection section = classificationSectionService.getSection(
			request.classificationSectionId()
		);
		validateClassificationRange(section, request.classificationNumber());
		book.update(
			request.libraryBookId(),
			request.title(),
			request.rfidUid(),
			request.callNumber(),
			request.classificationCode(),
			request.classificationNumber(),
			section
		);
		return Response.from(book);
	}

	@Transactional
	public void delete(Long id) {
		repository.delete(getBook(id));
	}

	private Book getBook(Long id) {
		return repository.findById(id)
			.orElseThrow(() -> new ResourceNotFoundException("도서", id));
	}

	private void validateDuplicates(Request request, Long id) {
		boolean duplicatedLibraryBookId = id == null
			? repository.existsByLibraryBookId(request.libraryBookId())
			: repository.existsByLibraryBookIdAndIdNot(request.libraryBookId(), id);
		if (duplicatedLibraryBookId) {
			throw new DuplicateResourceException(
				"이미 사용 중인 도서 관리 ID입니다. libraryBookId=" + request.libraryBookId()
			);
		}

		boolean duplicatedRfid = id == null
			? repository.existsByRfidUid(request.rfidUid())
			: repository.existsByRfidUidAndIdNot(request.rfidUid(), id);
		if (duplicatedRfid) {
			throw new DuplicateResourceException(
				"이미 사용 중인 RFID UID입니다. rfidUid=" + request.rfidUid()
			);
		}
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
		@NotBlank
		@Size(max = 100)
		String libraryBookId,

		@NotBlank
		@Size(max = 255)
		String title,

		@NotBlank
		@Size(max = 100)
		String rfidUid,

		@NotBlank
		@Size(max = 100)
		String callNumber,

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
		String libraryBookId,
		String title,
		String rfidUid,
		String callNumber,
		String classificationCode,
		BigDecimal classificationNumber,
		Long classificationSectionId,
		String classificationSectionCode
	) {
		public static Response from(Book book) {
			return new Response(
				book.getId(),
				book.getLibraryBookId(),
				book.getTitle(),
				book.getRfidUid(),
				book.getCallNumber(),
				book.getClassificationCode(),
				book.getClassificationNumber(),
				book.getClassificationSection().getId(),
				book.getClassificationSection().getCode()
			);
		}
	}
}
