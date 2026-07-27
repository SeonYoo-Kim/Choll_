package com.ssafy.backend.booklocation;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.backend.book.domain.Book;
import com.ssafy.backend.bookcopy.domain.BookCopy;
import com.ssafy.backend.bookcopy.domain.BookCopyStatus;
import com.ssafy.backend.bookcopy.repository.BookCopyRepository;
import com.ssafy.backend.booklocation.service.BookLocationService;
import com.ssafy.backend.booklocation.service.BookLocationService.BookInZonePageResponse;
import com.ssafy.backend.booklocation.service.BookLocationService.BookInZoneResponse;
import com.ssafy.backend.booklocation.service.BookLocationService.ZoneByRfidResponse;
import com.ssafy.backend.bookshelf.domain.Bookshelf;
import com.ssafy.backend.common.exception.InvalidDomainException;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import com.ssafy.backend.zone.domain.Zone;
import com.ssafy.backend.zone.service.ZoneService;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class BookLocationServiceTests {

	@Mock
	private BookCopyRepository bookCopyRepository;

	@Mock
	private ZoneService zoneService;

	@Mock
	private BookCopy copy;

	@Mock
	private Book book;

	@Mock
	private Bookshelf bookshelf;

	@Mock
	private Zone zone;

	private BookLocationService service;

	@BeforeEach
	void setUp() {
		service = new BookLocationService(bookCopyRepository, zoneService);
	}

	@Test
	void findsZoneByRfid() {
		when(bookCopyRepository.findByRfidUidWithLocation("RFID-001"))
			.thenReturn(Optional.of(copy));
		when(copy.getId()).thenReturn(30L);
		when(copy.getBook()).thenReturn(book);
		when(copy.getRfidUid()).thenReturn("RFID-001");
		when(copy.getCallNumber()).thenReturn("325.04-공44ㅅ");
		when(copy.getBookshelf()).thenReturn(bookshelf);
		when(book.getId()).thenReturn(20L);
		when(book.getTitle()).thenReturn("테스트 도서");
		when(bookshelf.getId()).thenReturn(10L);
		when(bookshelf.getShelfNumber()).thenReturn("300");
		when(bookshelf.getZone()).thenReturn(zone);
		when(zone.getId()).thenReturn(1L);
		when(zone.getCode()).thenReturn("TEST_ROOM");
		when(zone.getName()).thenReturn("테스트실");

		ZoneByRfidResponse response = service.findZoneByRfid(" RFID-001 ");

		assertEquals(30L, response.bookCopyId());
		assertEquals(1L, response.zoneId());
		assertEquals("TEST_ROOM", response.zoneCode());
		assertEquals("300", response.bookshelfNumber());
	}

	@Test
	void rejectsBookWithoutBookshelf() {
		when(bookCopyRepository.findByRfidUidWithLocation("RFID-002"))
			.thenReturn(Optional.of(copy));
		when(copy.getBookshelf()).thenReturn(null);

		assertThrows(
			InvalidDomainException.class,
			() -> service.findZoneByRfid("RFID-002")
		);
	}

	@Test
	void throwsWhenRfidIsNotRegistered() {
		when(bookCopyRepository.findByRfidUidWithLocation("UNKNOWN"))
			.thenReturn(Optional.empty());

		assertThrows(
			ResourceNotFoundException.class,
			() -> service.findZoneByRfid("UNKNOWN")
		);
	}

	@Test
	void findsBooksByZoneWithoutCreatingTemporaryRfid() {
		when(zoneService.getZone(1L)).thenReturn(zone);
		when(bookCopyRepository.findAllByZoneId(1L, PageRequest.of(0, 20)))
			.thenReturn(new PageImpl<>(List.of(copy), PageRequest.of(0, 20), 1));
		when(copy.getId()).thenReturn(30L);
		when(copy.getBook()).thenReturn(book);
		when(copy.getLibraryBookId()).thenReturn("LIB-001");
		when(copy.getRfidUid()).thenReturn(null);
		when(copy.getCallNumber()).thenReturn("325.04-공44ㅅ");
		when(copy.getBookshelf()).thenReturn(bookshelf);
		when(copy.getStatus()).thenReturn(BookCopyStatus.AVAILABLE);
		when(book.getId()).thenReturn(20L);
		when(book.getTitle()).thenReturn("테스트 도서");
		when(bookshelf.getId()).thenReturn(10L);
		when(bookshelf.getShelfNumber()).thenReturn("300");

		BookInZonePageResponse response = service.findBooksByZone(1L, 0, 20);
		List<BookInZoneResponse> books = response.books();

		assertEquals(1, books.size());
		assertEquals(1, response.totalElements());
		assertNull(books.getFirst().rfidUid());
		verify(zoneService).getZone(1L);
	}

	@Test
	void rejectsOversizedPage() {
		assertThrows(
			InvalidDomainException.class,
			() -> service.findBooksByZone(1L, 0, 101)
		);
	}
}
