package com.ssafy.backend.slot.service;

import com.ssafy.backend.bookcopy.domain.BookCopy;
import com.ssafy.backend.bookshelf.domain.Bookshelf;
import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.service.CartService;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import com.ssafy.backend.slot.domain.Slot;
import com.ssafy.backend.slot.domain.SlotStatus;
import com.ssafy.backend.slot.repository.SlotRepository;
import com.ssafy.backend.zone.domain.Zone;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class SlotService {

	private final SlotRepository repository;
	private final CartService cartService;

	public SlotService(SlotRepository repository, CartService cartService) {
		this.repository = repository;
		this.cartService = cartService;
	}

	public List<Response> findAll(Long cartId) {
		Long currentZoneId = currentZoneId(cartService.getCart(cartId));
		return repository.findAllByCartId(cartId)
			.stream()
			.map(slot -> Response.from(slot, currentZoneId))
			.toList();
	}

	public Response findByNumber(Long cartId, int slotNumber) {
		Long currentZoneId = currentZoneId(cartService.getCart(cartId));
		Slot slot = repository.findByCartIdAndSlotNumber(cartId, slotNumber)
			.orElseThrow(() -> new ResourceNotFoundException(
				"슬롯",
				"cartId=%d, slotNumber=%d".formatted(cartId, slotNumber)
			));
		return Response.from(slot, currentZoneId);
	}

	private Long currentZoneId(Cart cart) {
		return cart.getCurrentZone() == null ? null : cart.getCurrentZone().getId();
	}

	public record Response(
		Long id,
		int slotNumber,
		Status status,
		boolean isTarget,
		BookResponse book,
		LocalDateTime lastDetectedAt
	) {
		public static Response from(Slot slot, Long currentZoneId) {
			BookCopy copy = slot.getBookCopy();
			BookResponse book = copy == null ? null : BookResponse.from(copy);
			return new Response(
				slot.getId(),
				slot.getSlotNumber(),
				Status.from(slot.getStatus()),
				book != null
					&& currentZoneId != null
					&& currentZoneId.equals(book.shelfZoneId()),
				book,
				slot.getLastScannedAt()
			);
		}
	}

	public record BookResponse(
		Long id,
		Long bookId,
		String title,
		String author,
		String callNumber,
		String rfidTagId,
		Long bookshelfId,
		String bookshelfNumber,
		Long shelfZoneId,
		String zoneName
	) {
		public static BookResponse from(BookCopy copy) {
			Bookshelf bookshelf = copy.getBookshelf();
			Zone zone = bookshelf == null ? null : bookshelf.getZone();
			return new BookResponse(
				copy.getId(),
				copy.getBook().getId(),
				copy.getBook().getTitle(),
				copy.getBook().getAuthor(),
				copy.getCallNumber(),
				copy.getRfidUid(),
				bookshelf == null ? null : bookshelf.getId(),
				bookshelf == null ? null : bookshelf.getShelfNumber(),
				zone == null ? null : zone.getId(),
				zone == null ? null : zone.getName()
			);
		}
	}

	public enum Status {
		EMPTY,
		OCCUPIED,
		RECOGNIZING,
		RECOGNITION_FAILED;

		private static Status from(SlotStatus status) {
			return switch (status) {
				case EMPTY -> EMPTY;
				case OCCUPIED -> OCCUPIED;
				case RFID_READING -> RECOGNIZING;
				case RFID_ERROR -> RECOGNITION_FAILED;
			};
		}
	}
}
