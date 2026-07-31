package com.ssafy.backend.task;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.backend.bookcopy.domain.BookCopy;
import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.slot.service.SlotService;
import com.ssafy.backend.slot.service.SlotService.Response;
import com.ssafy.backend.slot.service.SlotService.Status;
import com.ssafy.backend.task.domain.SortingTask;
import com.ssafy.backend.task.domain.SortingTaskStatus;
import com.ssafy.backend.task.repository.SortingTaskRepository;
import com.ssafy.backend.task.service.TaskService;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class TaskServiceTests {

	private static final LocalDateTime SCANNED_AT =
		LocalDateTime.of(2026, 7, 30, 14, 0);

	@Mock
	private SlotService slotService;

	@Mock
	private SortingTaskRepository sortingTaskRepository;

	@Mock
	private Cart cart;

	@Mock
	private BookCopy bookCopy;

	private TaskService service;

	@BeforeEach
	void setUp() {
		service = new TaskService(slotService, sortingTaskRepository);
	}

	@Test
	void countsOccupiedCurrentZoneAndShelvedBooks() {
		Response empty = new Response(1L, 1, Status.EMPTY, false, null, null);
		Response target = new Response(
			2L,
			2,
			Status.OCCUPIED,
			true,
			new SlotService.BookResponse(
				10L,
				20L,
				"테스트 도서",
				"저자",
				"325.04-공44ㅅ",
				null,
				3L,
				"300",
				4L,
				"테스트실"
			),
			null
		);
		when(slotService.findAll(1L)).thenReturn(List.of(empty, target));
		when(sortingTaskRepository.countByCartIdAndStatus(1L, SortingTaskStatus.COMPLETED))
			.thenReturn(3L);

		TaskService.ProgressResponse response = service.findProgress(1L);

		assertEquals(2, response.totalSlots());
		assertEquals(4, response.totalBooks());
		assertEquals(3, response.shelvedBooks());
		assertEquals(1, response.remainingBooks());
		assertEquals(List.of(2), response.currentZoneSlotNumbers());
	}

	@Test
	void createsTaskOnLoadOnlyWhenNoActiveTaskExists() {
		when(cart.getId()).thenReturn(1L);
		when(bookCopy.getId()).thenReturn(10L);
		when(sortingTaskRepository.findByCartIdAndBookCopyIdAndStatus(
			1L, 10L, SortingTaskStatus.ACTIVE
		)).thenReturn(Optional.empty());

		service.recordLoaded(cart, bookCopy, SCANNED_AT);

		verify(sortingTaskRepository).save(any(SortingTask.class));
	}

	@Test
	void doesNotDuplicateActiveTaskOnRepeatedLoad() {
		when(cart.getId()).thenReturn(1L);
		when(bookCopy.getId()).thenReturn(10L);
		when(sortingTaskRepository.findByCartIdAndBookCopyIdAndStatus(
			1L, 10L, SortingTaskStatus.ACTIVE
		)).thenReturn(Optional.of(new SortingTask(cart, bookCopy, SCANNED_AT)));

		service.recordLoaded(cart, bookCopy, SCANNED_AT);

		verify(sortingTaskRepository, never()).save(any());
	}

	@Test
	void completesActiveTaskOnShelved() {
		SortingTask task = new SortingTask(cart, bookCopy, SCANNED_AT);
		when(cart.getId()).thenReturn(1L);
		when(bookCopy.getId()).thenReturn(10L);
		when(sortingTaskRepository.findByCartIdAndBookCopyIdAndStatus(
			1L, 10L, SortingTaskStatus.ACTIVE
		)).thenReturn(Optional.of(task));

		service.recordShelved(cart, bookCopy, SCANNED_AT.plusMinutes(5));

		assertEquals(SortingTaskStatus.COMPLETED, task.getStatus());
		assertEquals(SCANNED_AT.plusMinutes(5), task.getCompletedAt());
	}
}
