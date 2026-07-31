package com.ssafy.backend.bookshelfrange.controller;

import com.ssafy.backend.bookshelfrange.service.BookshelfRangeService;
import com.ssafy.backend.bookshelfrange.service.BookshelfRangeService.Request;
import com.ssafy.backend.bookshelfrange.service.BookshelfRangeService.Response;
import jakarta.validation.Valid;
import java.math.BigDecimal;
import java.net.URI;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/bookshelf-ranges")
public class BookshelfRangeController {

	private final BookshelfRangeService service;

	public BookshelfRangeController(BookshelfRangeService service) {
		this.service = service;
	}

	@PostMapping
	public ResponseEntity<Response> create(@Valid @RequestBody Request request) {
		Response response = service.create(request);
		return ResponseEntity
			.created(URI.create("/api/bookshelf-ranges/" + response.id()))
			.body(response);
	}

	@GetMapping
	public List<Response> findAll(@RequestParam(required = false) Long bookshelfId) {
		return service.findAll(bookshelfId);
	}

	@GetMapping("/{id}")
	public Response findById(@PathVariable Long id) {
		return service.findById(id);
	}

	@GetMapping("/resolve")
	public Response resolve(
		@RequestParam Long mapId,
		@RequestParam BigDecimal classificationNumber
	) {
		return service.resolve(mapId, classificationNumber);
	}

	@PutMapping("/{id}")
	public Response update(@PathVariable Long id, @Valid @RequestBody Request request) {
		return service.update(id, request);
	}

	@DeleteMapping("/{id}")
	public ResponseEntity<Void> delete(@PathVariable Long id) {
		service.delete(id);
		return ResponseEntity.noContent().build();
	}
}
