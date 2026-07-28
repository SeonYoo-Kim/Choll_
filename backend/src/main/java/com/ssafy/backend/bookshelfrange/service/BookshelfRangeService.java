package com.ssafy.backend.bookshelfrange.service;

import com.ssafy.backend.bookshelf.domain.Bookshelf;
import com.ssafy.backend.bookshelf.service.BookshelfService;
import com.ssafy.backend.bookshelfrange.domain.BookshelfRange;
import com.ssafy.backend.bookshelfrange.repository.BookshelfRangeRepository;
import com.ssafy.backend.common.exception.InvalidDomainException;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class BookshelfRangeService {

	private final BookshelfRangeRepository repository;
	private final BookshelfService bookshelfService;

	public BookshelfRangeService(
		BookshelfRangeRepository repository,
		BookshelfService bookshelfService
	) {
		this.repository = repository;
		this.bookshelfService = bookshelfService;
	}

	@Transactional
	public Response create(Request request) {
		validateRange(request.startNumber(), request.endNumber());
		Bookshelf bookshelf = bookshelfService.getBookshelf(request.bookshelfId());
		validateOverlap(
			bookshelf.getZone().getMap().getId(),
			request.startNumber(),
			request.endNumber(),
			null
		);
		BookshelfRange range = new BookshelfRange(
			bookshelf,
			request.startNumber(),
			request.endNumber()
		);
		return Response.from(repository.save(range));
	}

	public List<Response> findAll(Long bookshelfId) {
		List<BookshelfRange> ranges = bookshelfId == null
			? repository.findAll(Sort.by("startNumber").ascending())
			: repository.findAllByBookshelfIdOrderByStartNumberAsc(bookshelfId);
		return ranges.stream().map(Response::from).toList();
	}

	public Response findById(Long id) {
		return Response.from(getRange(id));
	}

	public Response resolve(Long mapId, BigDecimal classificationNumber) {
		return repository.findPlacement(mapId, classificationNumber)
			.map(Response::from)
			.orElseThrow(
				() -> new InvalidDomainException(
					"해당 분류번호에 배정된 책장이 없습니다. classificationNumber="
						+ classificationNumber
				)
			);
	}

	@Transactional
	public Response update(Long id, Request request) {
		BookshelfRange range = getRange(id);
		validateRange(request.startNumber(), request.endNumber());
		Bookshelf bookshelf = bookshelfService.getBookshelf(request.bookshelfId());
		validateOverlap(
			bookshelf.getZone().getMap().getId(),
			request.startNumber(),
			request.endNumber(),
			id
		);
		range.update(bookshelf, request.startNumber(), request.endNumber());
		return Response.from(range);
	}

	@Transactional
	public void delete(Long id) {
		repository.delete(getRange(id));
	}

	private BookshelfRange getRange(Long id) {
		return repository.findById(id)
			.orElseThrow(() -> new ResourceNotFoundException("책장 배치 범위", id));
	}

	private void validateRange(BigDecimal startNumber, BigDecimal endNumber) {
		if (startNumber.compareTo(endNumber) > 0) {
			throw new InvalidDomainException("배치 시작 번호는 종료 번호보다 클 수 없습니다.");
		}
	}

	private void validateOverlap(
		Long mapId,
		BigDecimal startNumber,
		BigDecimal endNumber,
		Long id
	) {
		boolean overlaps = id == null
			? repository.existsOverlappingRange(mapId, startNumber, endNumber)
			: repository.existsOverlappingRangeExceptId(mapId, id, startNumber, endNumber);
		if (overlaps) {
			throw new InvalidDomainException(
				"같은 지도 안에서 분류번호 배치 범위가 기존 범위와 겹칩니다."
			);
		}
	}

	public record Request(
		@NotNull
		Long bookshelfId,

		@NotNull
		@DecimalMin("0")
		BigDecimal startNumber,

		@NotNull
		@DecimalMin("0")
		BigDecimal endNumber
	) {
	}

	public record Response(
		Long id,
		Long bookshelfId,
		String shelfNumber,
		Long zoneId,
		String zoneCode,
		BigDecimal startNumber,
		BigDecimal endNumber
	) {
		public static Response from(BookshelfRange range) {
			Bookshelf bookshelf = range.getBookshelf();
			return new Response(
				range.getId(),
				bookshelf.getId(),
				bookshelf.getShelfNumber(),
				bookshelf.getZone().getId(),
				bookshelf.getZone().getCode(),
				range.getStartNumber(),
				range.getEndNumber()
			);
		}
	}
}
