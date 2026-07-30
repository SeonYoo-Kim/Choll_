package com.ssafy.backend.mqtt.rfid;

import com.ssafy.backend.bookcopy.domain.BookCopy;
import com.ssafy.backend.bookcopy.repository.BookCopyRepository;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import com.ssafy.backend.slot.domain.Slot;
import com.ssafy.backend.slot.domain.SlotStatus;
import com.ssafy.backend.slot.repository.SlotRepository;
import com.ssafy.backend.slot.service.SlotService;
import com.ssafy.backend.websocket.CartEventPublisher;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Objects;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * RFID 태깅 이벤트로 슬롯 상태를 갱신하고 SLOT_UPDATED WebSocket 이벤트를 발행한다.
 * DETECTED: uid→book_copies 매칭 후 배정(미등록 uid는 인식 실패), REMOVED: 슬롯 비움.
 */
@Service
public class SlotRfidEventService {

	private static final Logger log = LoggerFactory.getLogger(SlotRfidEventService.class);
	private static final ZoneId DATABASE_ZONE = ZoneId.of("Asia/Seoul");
	private static final String SLOT_UPDATED_EVENT_TYPE = "SLOT_UPDATED";

	private final SlotRepository slotRepository;
	private final BookCopyRepository bookCopyRepository;
	private final CartEventPublisher eventPublisher;

	public SlotRfidEventService(
		SlotRepository slotRepository,
		BookCopyRepository bookCopyRepository,
		CartEventPublisher eventPublisher
	) {
		this.slotRepository = slotRepository;
		this.bookCopyRepository = bookCopyRepository;
		this.eventPublisher = eventPublisher;
	}

	@Transactional
	public void accept(RfidSlotEvent event) {
		Slot slot = slotRepository
			.findByCartIdAndSlotNumber(event.cartId(), event.slotNumber())
			.orElseThrow(() -> new ResourceNotFoundException(
				"슬롯",
				"cartId=%d, slotNumber=%d".formatted(event.cartId(), event.slotNumber())
			));
		LocalDateTime scannedAt = LocalDateTime.ofInstant(event.measuredAt(), DATABASE_ZONE);

		switch (event.type()) {
			case DETECTED -> detect(slot, event.uid(), scannedAt);
			case REMOVED -> slot.clear(scannedAt);
		}
		publishSlotUpdated(slot);

		log.info(
			"RFID 슬롯 이벤트 처리 cartId={}, slotNumber={}, uid={}, event={}, status={}",
			event.cartId(),
			event.slotNumber(),
			event.uid(),
			event.type(),
			slot.getStatus()
		);
	}

	private void detect(Slot slot, String uid, LocalDateTime scannedAt) {
		Optional<BookCopy> copy = bookCopyRepository.findByRfidUidWithLocation(uid);
		if (copy.isEmpty()) {
			slot.updateStatus(SlotStatus.RFID_ERROR, scannedAt);
			log.warn(
				"미등록 RFID 태그 uid={} — slotNumber={}를 인식 실패로 표시",
				uid,
				slot.getSlotNumber()
			);
			return;
		}
		releaseIfHeldElsewhere(copy.get(), slot, scannedAt);
		slot.assignBook(copy.get(), scannedAt);
	}

	private void releaseIfHeldElsewhere(BookCopy copy, Slot target, LocalDateTime scannedAt) {
		slotRepository.findByBookCopyId(copy.getId())
			.filter(other -> !Objects.equals(other.getId(), target.getId()))
			.ifPresent(other -> {
				other.clear(scannedAt);
				// uk_slot_book_copy 제약: 해제 UPDATE가 새 배정보다 먼저 DB에 반영돼야 한다
				slotRepository.flush();
				publishSlotUpdated(other);
			});
	}

	private void publishSlotUpdated(Slot slot) {
		Long currentZoneId = slot.getCart().getCurrentZone() == null
			? null
			: slot.getCart().getCurrentZone().getId();
		eventPublisher.publish(
			slot.getCart().getId(),
			SLOT_UPDATED_EVENT_TYPE,
			SlotService.Response.from(slot, currentZoneId)
		);
	}
}
