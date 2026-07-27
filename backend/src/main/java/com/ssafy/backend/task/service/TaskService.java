package com.ssafy.backend.task.service;

import com.ssafy.backend.slot.service.SlotService;
import com.ssafy.backend.slot.service.SlotService.Response;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class TaskService {

	private final SlotService slotService;

	public TaskService(SlotService slotService) {
		this.slotService = slotService;
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

		return new ProgressResponse(
			occupiedSlots.size(),
			0,
			occupiedSlots.size(),
			currentZoneSlotNumbers
		);
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
