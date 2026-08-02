package com.ssafy.backend.follow.controller;

import com.ssafy.backend.follow.service.FollowTargetService;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/carts/{cartId}/follow")
public class FollowTargetController {

	private final FollowTargetService service;

	public FollowTargetController(FollowTargetService service) {
		this.service = service;
	}

	@Operation(
		operationId = "selectFollowTarget",
		summary = "추종 대상(track id) 선택 — 영상 UI에서 고른 사람을 카트로 하행",
		tags = "follow"
	)
	@PostMapping("/target")
	public ResponseEntity<FollowTargetService.Response> selectTarget(
		@PathVariable Long cartId,
		@Valid @RequestBody Request request
	) {
		return ResponseEntity
			.status(HttpStatus.ACCEPTED)
			.body(service.selectTarget(cartId, request.trackId()));
	}

	public record Request(
		@NotNull(message = "trackId는 필수입니다.")
		Long trackId
	) {
	}
}
