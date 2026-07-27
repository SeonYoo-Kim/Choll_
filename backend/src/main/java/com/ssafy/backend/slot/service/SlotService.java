package com.ssafy.backend.slot.service;

import com.ssafy.backend.bookcopy.domain.BookCopy;
import com.ssafy.backend.bookshelf.domain.Bookshelf;
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
		cartService.getCart(cartId);
		return repository.findAllByCartId(cartId)
			.stream()
			.map(Response::from)
			.toList();
	}

	public Response findByNumber(Long cartId, int slotNumber) {
		cartService.getCart(cartId);
		Slot slot = repository.findByCartIdAndSlotNumber(cartId, slotNumber)
			.orElseThrow(() -> new ResourceNotFoundException(
				"슬롯",
				"cartId=%d, slotNumber=%d".formatted(cartId, slotNumber)
			));
		return Response.from(slot);
	}

	public record Response(
		Long id,
		Long cartId,
		int slotNumber,
		SlotStatus status,
		LocalDateTime lastScannedAt,
		BookResponse book
	) {
		public static Response from(Slot slot) {
			return new Response(
				slot.getId(),
				slot.getCart().getId(),
				slot.getSlotNumber(),
				slot.getStatus(),
				slot.getLastScannedAt(),
				slot.getBookCopy() == null ? null : BookResponse.from(slot.getBookCopy())
			);
		}
	}

	public record BookResponse(
		Long bookCopyId,
		Long bookId,
		String rfidUid,
		String title,
		String callNumber,
		Long targetBookshelfId,
		String targetBookshelfNumber,
		Long targetZoneId,
		String targetZoneCode,
		String targetZoneName
	) {
		public static BookResponse from(BookCopy copy) {
			Bookshelf bookshelf = copy.getBookshelf();
			Zone zone = bookshelf == null ? null : bookshelf.getZone();
			return new BookResponse(
				copy.getId(),
				copy.getBook().getId(),
				copy.getRfidUid(),
				copy.getBook().getTitle(),
				copy.getCallNumber(),
				bookshelf == null ? null : bookshelf.getId(),
				bookshelf == null ? null : bookshelf.getShelfNumber(),
				zone == null ? null : zone.getId(),
				zone == null ? null : zone.getCode(),
				zone == null ? null : zone.getName()
			);
		}
	}
}
