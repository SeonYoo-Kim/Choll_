package com.ssafy.backend.navigation.controller;

import com.ssafy.backend.navigation.service.NavigationService;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/carts/{cartId}/navigation")
public class NavigationController {

	private final NavigationService service;

	public NavigationController(NavigationService service) {
		this.service = service;
	}

	@Operation(
		operationId = "startNavigation",
		summary = "목적지 이동 시작 (NAV-01)",
		tags = "navigation"
	)
	@PostMapping
	public ResponseEntity<NavigationService.Response> start(
		@PathVariable Long cartId,
		@Valid @RequestBody Request request
	) {
		return ResponseEntity
			.status(HttpStatus.ACCEPTED)
			.body(service.start(cartId, request.zoneId()));
	}

	@Operation(
		operationId = "cancelNavigation",
		summary = "목적지 이동 취소 (NAV-02)",
		tags = "navigation"
	)
	@DeleteMapping
	public ResponseEntity<Void> cancel(@PathVariable Long cartId) {
		service.cancel(cartId);
		return ResponseEntity.noContent().build();
	}

	public record Request(
		@NotNull(message = "목적지 구역 ID는 필수입니다.")
		Long zoneId
	) {
	}
}
