package com.ssafy.backend.mqtt.position;

import com.ssafy.backend.zone.domain.Zone;
import com.ssafy.backend.zone.repository.ZoneRepository;
import java.math.BigDecimal;
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
public class ZoneLocator {

	private final ZoneRepository repository;
	private final PolygonZoneMatcher matcher;

	public ZoneLocator(ZoneRepository repository, PolygonZoneMatcher matcher) {
		this.repository = repository;
		this.matcher = matcher;
	}

	public Optional<Zone> locate(BigDecimal x, BigDecimal y) {
		return repository.findAll()
			.stream()
			.filter(zone -> matcher.contains(zone.getPolygonJson(), x, y))
			.findFirst();
	}
}
