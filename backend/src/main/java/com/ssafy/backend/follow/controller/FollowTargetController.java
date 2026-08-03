package com.ssafy.backend.follow.controller;

import com.ssafy.backend.follow.service.FollowControlService;
import com.ssafy.backend.follow.service.FollowTargetService;
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
@RequestMapping("/api/carts/{cartId}/follow")
public class FollowTargetController {

	private final FollowTargetService service;
	private final FollowControlService controlService;

	public FollowTargetController(
		FollowTargetService service,
		FollowControlService controlService
	) {
		this.service = service;
		this.controlService = controlService;
	}

	@Operation(
		operationId = "startFollow",
		summary = "사서 추종 시작 (FOLLOW-04)",
		tags = "follow"
	)
	@PostMapping
	public ResponseEntity<FollowControlService.Response> start(@PathVariable Long cartId) {
		return ResponseEntity
			.status(HttpStatus.ACCEPTED)
			.body(controlService.start(cartId));
	}

	@Operation(
		operationId = "pauseFollow",
		summary = "사서 추종 일시정지 (FOLLOW-01)",
		tags = "follow"
	)
	@PostMapping("/pause")
	public ResponseEntity<FollowControlService.Response> pause(@PathVariable Long cartId) {
		return ResponseEntity
			.status(HttpStatus.ACCEPTED)
			.body(controlService.pause(cartId));
	}

	@Operation(
		operationId = "stopFollow",
		summary = "사서 추종 종료 (FOLLOW-02)",
		tags = "follow"
	)
	@DeleteMapping
	public ResponseEntity<Void> stop(@PathVariable Long cartId) {
		controlService.stop(cartId);
		return ResponseEntity.noContent().build();
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
