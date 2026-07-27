package com.ssafy.backend.booklocation.controller;

import com.ssafy.backend.booklocation.service.BookLocationService;
import com.ssafy.backend.booklocation.service.BookLocationService.BookInZoneResponse;
import com.ssafy.backend.booklocation.service.BookLocationService.ZoneByRfidResponse;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BookLocationController {

	private final BookLocationService service;

	public BookLocationController(BookLocationService service) {
		this.service = service;
	}

	@GetMapping("/api/book-copies/rfid/{rfidUid}/zone")
	public ZoneByRfidResponse findZoneByRfid(@PathVariable String rfidUid) {
		return service.findZoneByRfid(rfidUid);
	}

	@GetMapping("/api/zones/{zoneId}/book-copies")
	public List<BookInZoneResponse> findBooksByZone(@PathVariable Long zoneId) {
		return service.findBooksByZone(zoneId);
	}
}
