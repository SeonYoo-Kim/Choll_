package com.ssafy.backend.mqtt.rfid;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.ssafy.backend.book.domain.Book;
import com.ssafy.backend.bookcopy.domain.BookCopy;
import com.ssafy.backend.bookcopy.repository.BookCopyRepository;
import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.mqtt.heartbeat.CartConnectionService;
import com.ssafy.backend.slot.domain.Slot;
import com.ssafy.backend.slot.domain.SlotStatus;
import com.ssafy.backend.slot.repository.SlotRepository;
import com.ssafy.backend.slot.service.SlotService;
import com.ssafy.backend.websocket.CartEventPublisher;
import java.time.Instant;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

@ExtendWith(MockitoExtension.class)
class SlotRfidEventServiceTest {

	private static final Instant MEASURED_AT =
		Instant.parse("2026-07-29T04:32:27.680Z");

	@Mock
	private SlotRepository slotRepository;

	@Mock
	private BookCopyRepository bookCopyRepository;

	@Mock
	private CartEventPublisher eventPublisher;

	@Mock
	private CartConnectionService connectionService;

	@Mock
	private Cart cart;

	@Mock
	private BookCopy bookCopy;

	@Mock
	private Book book;

	private SlotRfidEventService service;

	@BeforeEach
	void setUp() {
		service = new SlotRfidEventService(
			slotRepository,
			bookCopyRepository,
			eventPublisher,
			connectionService
		);
	}

	private Slot slotWithId(int slotNumber, long id) {
		Slot slot = new Slot(cart, slotNumber);
		ReflectionTestUtils.setField(slot, "id", id);
		return slot;
	}

	private void stubBookCopy() {
		when(bookCopy.getId()).thenReturn(100L);
		when(bookCopy.getBook()).thenReturn(book);
		when(book.getId()).thenReturn(200L);
		when(book.getTitle()).thenReturn("초록 눈 코끼리");
		when(bookCopy.getBookshelf()).thenReturn(null);
	}

	@Test
	void assignsBookAndPublishesSlotUpdatedOnDetected() {
		Slot slot = slotWithId(1, 10L);
		when(slotRepository.findByCartIdAndSlotNumber(1L, 1))
			.thenReturn(Optional.of(slot));
		when(bookCopyRepository.findByRfidUidWithLocation("0437F306"))
			.thenReturn(Optional.of(bookCopy));
		when(slotRepository.findByBookCopyId(100L)).thenReturn(Optional.empty());
		when(cart.getId()).thenReturn(1L);
		when(cart.getCurrentZone()).thenReturn(null);
		stubBookCopy();

		service.accept(new RfidSlotEvent(
			1L, 1, "0437F306", RfidSlotEvent.Type.DETECTED, MEASURED_AT
		));

		assertThat(slot.getStatus()).isEqualTo(SlotStatus.OCCUPIED);
		assertThat(slot.getBookCopy()).isEqualTo(bookCopy);
		verify(connectionService).markAlive(
			eq(cart),
			org.mockito.ArgumentMatchers.any(java.time.LocalDateTime.class)
		);
		ArgumentCaptor<Object> captor = ArgumentCaptor.forClass(Object.class);
		verify(eventPublisher).publish(eq(1L), eq("SLOT_UPDATED"), captor.capture());
		SlotService.Response payload = (SlotService.Response) captor.getValue();
		assertThat(payload.slotNumber()).isEqualTo(1);
		assertThat(payload.status()).isEqualTo(SlotService.Status.OCCUPIED);
		assertThat(payload.book().title()).isEqualTo("초록 눈 코끼리");
	}

	@Test
	void marksSlotAsRecognitionFailedWhenUidIsUnknown() {
		Slot slot = slotWithId(1, 10L);
		when(slotRepository.findByCartIdAndSlotNumber(1L, 1))
			.thenReturn(Optional.of(slot));
		when(bookCopyRepository.findByRfidUidWithLocation("DEADBEEF"))
			.thenReturn(Optional.empty());
		when(cart.getId()).thenReturn(1L);
		when(cart.getCurrentZone()).thenReturn(null);

		service.accept(new RfidSlotEvent(
			1L, 1, "DEADBEEF", RfidSlotEvent.Type.DETECTED, MEASURED_AT
		));

		assertThat(slot.getStatus()).isEqualTo(SlotStatus.RFID_ERROR);
		ArgumentCaptor<Object> captor = ArgumentCaptor.forClass(Object.class);
		verify(eventPublisher).publish(eq(1L), eq("SLOT_UPDATED"), captor.capture());
		SlotService.Response payload = (SlotService.Response) captor.getValue();
		assertThat(payload.status()).isEqualTo(SlotService.Status.RECOGNITION_FAILED);
		assertThat(payload.book()).isNull();
	}

	@Test
	void clearsSlotOnRemoved() {
		Slot slot = slotWithId(1, 10L);
		slot.assignBook(bookCopy, java.time.LocalDateTime.now());
		when(slotRepository.findByCartIdAndSlotNumber(1L, 1))
			.thenReturn(Optional.of(slot));
		when(cart.getId()).thenReturn(1L);
		when(cart.getCurrentZone()).thenReturn(null);

		service.accept(new RfidSlotEvent(
			1L, 1, "0437F306", RfidSlotEvent.Type.REMOVED, MEASURED_AT
		));

		assertThat(slot.getStatus()).isEqualTo(SlotStatus.EMPTY);
		assertThat(slot.getBookCopy()).isNull();
		verifyNoInteractions(bookCopyRepository);
		verify(eventPublisher).publish(
			eq(1L),
			eq("SLOT_UPDATED"),
			org.mockito.ArgumentMatchers.any()
		);
	}

	@Test
	void releasesBookFromPreviousSlotWhenDetectedElsewhere() {
		Slot previous = slotWithId(2, 20L);
		previous.assignBook(bookCopy, java.time.LocalDateTime.now());
		Slot slot = slotWithId(1, 10L);
		when(slotRepository.findByCartIdAndSlotNumber(1L, 1))
			.thenReturn(Optional.of(slot));
		when(bookCopyRepository.findByRfidUidWithLocation("0437F306"))
			.thenReturn(Optional.of(bookCopy));
		when(slotRepository.findByBookCopyId(100L)).thenReturn(Optional.of(previous));
		when(cart.getId()).thenReturn(1L);
		when(cart.getCurrentZone()).thenReturn(null);
		stubBookCopy();

		service.accept(new RfidSlotEvent(
			1L, 1, "0437F306", RfidSlotEvent.Type.DETECTED, MEASURED_AT
		));

		assertThat(previous.getStatus()).isEqualTo(SlotStatus.EMPTY);
		assertThat(previous.getBookCopy()).isNull();
		assertThat(slot.getStatus()).isEqualTo(SlotStatus.OCCUPIED);
		verify(slotRepository).flush();
		verify(eventPublisher, times(2)).publish(
			eq(1L),
			eq("SLOT_UPDATED"),
			org.mockito.ArgumentMatchers.any()
		);
	}
}
