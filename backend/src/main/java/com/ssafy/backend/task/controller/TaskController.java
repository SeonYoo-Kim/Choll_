package com.ssafy.backend.task.controller;

import com.ssafy.backend.task.service.TaskService;
import com.ssafy.backend.task.service.TaskService.ProgressResponse;
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/carts/{cartId}/tasks")
public class TaskController {

	private final TaskService service;

	public TaskController(TaskService service) {
		this.service = service;
	}

	@GetMapping("/progress")
	@Operation(operationId = "getTaskProgress", tags = "tasks")
	public ProgressResponse findProgress(@PathVariable Long cartId) {
		return service.findProgress(cartId);
	}
}
