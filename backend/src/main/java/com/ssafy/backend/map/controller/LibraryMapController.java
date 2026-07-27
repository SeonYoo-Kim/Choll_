package com.ssafy.backend.map.controller;

import com.ssafy.backend.map.service.LibraryMapService;
import com.ssafy.backend.map.service.LibraryMapService.Request;
import com.ssafy.backend.map.service.LibraryMapService.Response;
import jakarta.validation.Valid;
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
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/maps")
public class LibraryMapController {

	private final LibraryMapService service;

	public LibraryMapController(LibraryMapService service) {
		this.service = service;
	}

	@PostMapping
	public ResponseEntity<Response> create(@Valid @RequestBody Request request) {
		Response response = service.create(request);
		return ResponseEntity.created(URI.create("/api/maps/" + response.id())).body(response);
	}

	@GetMapping
	public List<Response> findAll() {
		return service.findAll();
	}

	@GetMapping("/{id}")
	public Response findById(@PathVariable Long id) {
		return service.findById(id);
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
