package com.ssafy.backend.slot.controller;

import com.ssafy.backend.slot.service.SlotService;
import com.ssafy.backend.slot.service.SlotService.Response;
import io.swagger.v3.oas.annotations.Operation;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/carts/{cartId}/slots")
public class SlotController {

	private final SlotService service;

	public SlotController(SlotService service) {
		this.service = service;
	}

	@GetMapping
	@Operation(operationId = "listSlots", tags = "slots")
	public List<Response> findAll(@PathVariable Long cartId) {
		return service.findAll(cartId);
	}

	@GetMapping("/{slotNumber}")
	@Operation(operationId = "getSlot", tags = "slots")
	public Response findByNumber(
		@PathVariable Long cartId,
		@PathVariable int slotNumber
	) {
		return service.findByNumber(cartId, slotNumber);
	}
}
