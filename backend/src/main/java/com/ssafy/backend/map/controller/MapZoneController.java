package com.ssafy.backend.map.controller;

import com.ssafy.backend.zone.service.ZoneService;
import com.ssafy.backend.zone.service.ZoneService.Response;
import io.swagger.v3.oas.annotations.Operation;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/maps/{mapId}/zones")
public class MapZoneController {

	private final ZoneService service;

	public MapZoneController(ZoneService service) {
		this.service = service;
	}

	@GetMapping
	@Operation(operationId = "listShelfZones", tags = "maps")
	public List<Response> findAll(@PathVariable Long mapId) {
		return service.findAll(mapId);
	}
}
