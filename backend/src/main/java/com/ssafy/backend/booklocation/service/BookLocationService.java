package com.ssafy.backend.booklocation.service;

import com.ssafy.backend.book.domain.Book;
import com.ssafy.backend.bookcopy.domain.BookCopy;
import com.ssafy.backend.bookcopy.domain.BookCopyStatus;
import com.ssafy.backend.bookcopy.repository.BookCopyRepository;
import com.ssafy.backend.bookshelf.domain.Bookshelf;
import com.ssafy.backend.common.exception.InvalidDomainException;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import com.ssafy.backend.zone.domain.Zone;
import com.ssafy.backend.zone.service.ZoneService;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class BookLocationService {

	private final BookCopyRepository bookCopyRepository;
	private final ZoneService zoneService;

	public BookLocationService(
		BookCopyRepository bookCopyRepository,
		ZoneService zoneService
	) {
		this.bookCopyRepository = bookCopyRepository;
		this.zoneService = zoneService;
	}

	public ZoneByRfidResponse findZoneByRfid(String rfidUid) {
		String normalizedRfidUid = normalizeRfidUid(rfidUid);
		BookCopy copy = bookCopyRepository.findByRfidUidWithLocation(normalizedRfidUid)
			.orElseThrow(() -> new ResourceNotFoundException(
				"RFID가 등록된 소장 도서",
				"rfidUid=" + normalizedRfidUid
			));

		Bookshelf bookshelf = copy.getBookshelf();
		if (bookshelf == null) {
			throw new InvalidDomainException("해당 RFID 도서에 책장이 배정되지 않았습니다.");
		}

		return ZoneByRfidResponse.from(copy, bookshelf, bookshelf.getZone());
	}

	public BookInZonePageResponse findBooksByZone(Long zoneId, int page, int size) {
		validatePageRequest(page, size);
		zoneService.getZone(zoneId);
		Page<BookInZoneResponse> result = bookCopyRepository.findAllByZoneId(
			zoneId,
			PageRequest.of(page, size)
		).map(BookInZoneResponse::from);
		return BookInZonePageResponse.from(zoneId, result);
	}

	private String normalizeRfidUid(String rfidUid) {
		if (rfidUid == null || rfidUid.isBlank()) {
			throw new InvalidDomainException("RFID UID는 비어 있을 수 없습니다.");
		}
		return rfidUid.trim();
	}

	private void validatePageRequest(int page, int size) {
		if (page < 0) {
			throw new InvalidDomainException("페이지 번호는 0 이상이어야 합니다.");
		}
		if (size < 1 || size > 100) {
			throw new InvalidDomainException("페이지 크기는 1 이상 100 이하여야 합니다.");
		}
	}

	public record ZoneByRfidResponse(
		Long bookCopyId,
		Long bookId,
		String rfidUid,
		String title,
		String callNumber,
		Long bookshelfId,
		String bookshelfNumber,
		Long zoneId,
		String zoneCode,
		String zoneName
	) {
		public static ZoneByRfidResponse from(
			BookCopy copy,
			Bookshelf bookshelf,
			Zone zone
		) {
			return new ZoneByRfidResponse(
				copy.getId(),
				copy.getBook().getId(),
				copy.getRfidUid(),
				copy.getBook().getTitle(),
				copy.getCallNumber(),
				bookshelf.getId(),
				bookshelf.getShelfNumber(),
				zone.getId(),
				zone.getCode(),
				zone.getName()
			);
		}
	}

	public record BookInZoneResponse(
		Long bookCopyId,
		Long bookId,
		String isbn,
		String title,
		String author,
		String libraryBookId,
		String rfidUid,
		String callNumber,
		Long bookshelfId,
		String bookshelfNumber,
		BookCopyStatus status
	) {
		public static BookInZoneResponse from(BookCopy copy) {
			Book book = copy.getBook();
			Bookshelf bookshelf = copy.getBookshelf();
			return new BookInZoneResponse(
				copy.getId(),
				book.getId(),
				book.getIsbn(),
				book.getTitle(),
				book.getAuthor(),
				copy.getLibraryBookId(),
				copy.getRfidUid(),
				copy.getCallNumber(),
				bookshelf.getId(),
				bookshelf.getShelfNumber(),
				copy.getStatus()
			);
		}
	}

	public record BookInZonePageResponse(
		Long zoneId,
		List<BookInZoneResponse> books,
		int page,
		int size,
		long totalElements,
		int totalPages,
		boolean hasNext
	) {
		public static BookInZonePageResponse from(
			Long zoneId,
			Page<BookInZoneResponse> result
		) {
			return new BookInZonePageResponse(
				zoneId,
				result.getContent(),
				result.getNumber(),
				result.getSize(),
				result.getTotalElements(),
				result.getTotalPages(),
				result.hasNext()
			);
		}
	}
}
