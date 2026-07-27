package com.ssafy.backend.task;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

import com.ssafy.backend.slot.service.SlotService;
import com.ssafy.backend.slot.service.SlotService.Response;
import com.ssafy.backend.slot.service.SlotService.Status;
import com.ssafy.backend.task.service.TaskService;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class TaskServiceTests {

	@Mock
	private SlotService slotService;

	private TaskService service;

	@BeforeEach
	void setUp() {
		service = new TaskService(slotService);
	}

	@Test
	void countsOccupiedAndCurrentZoneSlots() {
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

		TaskService.ProgressResponse response = service.findProgress(1L);

		assertEquals(1, response.totalBooks());
		assertEquals(0, response.shelvedBooks());
		assertEquals(1, response.remainingBooks());
		assertEquals(List.of(2), response.currentZoneSlotNumbers());
	}
}
