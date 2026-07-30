package com.ssafy.backend.task.service;

import com.ssafy.backend.bookcopy.domain.BookCopy;
import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.slot.service.SlotService;
import com.ssafy.backend.slot.service.SlotService.Response;
import com.ssafy.backend.task.domain.SortingTask;
import com.ssafy.backend.task.domain.SortingTaskStatus;
import com.ssafy.backend.task.repository.SortingTaskRepository;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDateTime;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class TaskService {

	private static final Logger log = LoggerFactory.getLogger(TaskService.class);

	private final SlotService slotService;
	private final SortingTaskRepository sortingTaskRepository;

	public TaskService(
		SlotService slotService,
		SortingTaskRepository sortingTaskRepository
	) {
		this.slotService = slotService;
		this.sortingTaskRepository = sortingTaskRepository;
	}

	public ProgressResponse findProgress(Long cartId) {
		List<Response> occupiedSlots = slotService.findAll(cartId)
			.stream()
			.filter(slot -> slot.book() != null)
			.toList();
		List<Integer> currentZoneSlotNumbers = occupiedSlots.stream()
			.filter(Response::isTarget)
			.map(Response::slotNumber)
			.toList();
		int shelvedBooks = (int) sortingTaskRepository
			.countByCartIdAndStatus(cartId, SortingTaskStatus.COMPLETED);
		int remainingBooks = occupiedSlots.size();

		return new ProgressResponse(
			shelvedBooks + remainingBooks,
			shelvedBooks,
			remainingBooks,
			currentZoneSlotNumbers
		);
	}

	/** 카트에 책이 실림(RFID DETECTED) — 진행 중 작업이 없으면 새 작업 생성. */
	@Transactional
	public void recordLoaded(Cart cart, BookCopy bookCopy, LocalDateTime loadedAt) {
		boolean alreadyActive = sortingTaskRepository
			.findByCartIdAndBookCopyIdAndStatus(
				cart.getId(),
				bookCopy.getId(),
				SortingTaskStatus.ACTIVE
			)
			.isPresent();
		if (alreadyActive) {
			return;
		}
		sortingTaskRepository.save(new SortingTask(cart, bookCopy, loadedAt));
		log.info(
			"정리 작업 생성 cartId={}, bookCopyId={}",
			cart.getId(),
			bookCopy.getId()
		);
	}

	/** 카트에서 책이 제거됨(RFID REMOVED = 서가에 꽂음) — 진행 중 작업 완료 처리. */
	@Transactional
	public void recordShelved(Cart cart, BookCopy bookCopy, LocalDateTime shelvedAt) {
		sortingTaskRepository
			.findByCartIdAndBookCopyIdAndStatus(
				cart.getId(),
				bookCopy.getId(),
				SortingTaskStatus.ACTIVE
			)
			.ifPresent(task -> {
				task.complete(shelvedAt);
				log.info(
					"정리 작업 완료 cartId={}, bookCopyId={}, taskId={}",
					cart.getId(),
					bookCopy.getId(),
					task.getId()
				);
			});
	}

	@Schema(name = "TaskProgress")
	public record ProgressResponse(
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		int totalBooks,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		int shelvedBooks,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		int remainingBooks,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		List<Integer> currentZoneSlotNumbers
	) {
	}
}
