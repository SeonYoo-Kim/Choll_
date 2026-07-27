package com.ssafy.backend.zone.service;

import com.ssafy.backend.common.exception.DuplicateResourceException;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import com.ssafy.backend.map.domain.LibraryMap;
import com.ssafy.backend.map.service.LibraryMapService;
import com.ssafy.backend.zone.domain.Zone;
import com.ssafy.backend.zone.repository.ZoneRepository;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class ZoneService {

	private final ZoneRepository repository;
	private final LibraryMapService mapService;

	public ZoneService(ZoneRepository repository, LibraryMapService mapService) {
		this.repository = repository;
		this.mapService = mapService;
	}

	@Transactional
	public Response create(Request request) {
		validateDuplicateCode(request.mapId(), request.code(), null);
		LibraryMap map = mapService.getMap(request.mapId());
		Zone zone = new Zone(map, request.code(), request.name(), request.polygonJson());
		return Response.from(repository.save(zone));
	}

	public List<Response> findAll(Long mapId) {
		if (mapId != null) {
			mapService.getMap(mapId);
		}
		List<Zone> zones = mapId == null
			? repository.findAll(Sort.by("code").ascending())
			: repository.findAllByMapIdOrderByCodeAsc(mapId);
		return zones.stream().map(Response::from).toList();
	}

	public Response findById(Long id) {
		return Response.from(getZone(id));
	}

	@Transactional
	public Response update(Long id, Request request) {
		Zone zone = getZone(id);
		validateDuplicateCode(request.mapId(), request.code(), id);
		LibraryMap map = mapService.getMap(request.mapId());
		zone.update(map, request.code(), request.name(), request.polygonJson());
		return Response.from(zone);
	}

	@Transactional
	public void delete(Long id) {
		repository.delete(getZone(id));
	}

	public Zone getZone(Long id) {
		return repository.findById(id)
			.orElseThrow(() -> new ResourceNotFoundException("구역", id));
	}

	private void validateDuplicateCode(Long mapId, String code, Long id) {
		boolean exists = id == null
			? repository.existsByMapIdAndCode(mapId, code)
			: repository.existsByMapIdAndCodeAndIdNot(mapId, code, id);
		if (exists) {
			throw new DuplicateResourceException(
				"같은 지도에서 이미 사용 중인 구역 코드입니다. code=" + code
			);
		}
	}

	public record Request(
		@NotNull
		Long mapId,

		@NotBlank
		@Size(max = 50)
		String code,

		@NotBlank
		@Size(max = 100)
		String name,

		@NotBlank
		String polygonJson
	) {
	}

	@Schema(name = "ShelfZone")
	public record Response(
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		Long id,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		Long mapId,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		String code,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		String name,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		String boundaryData
	) {
		public static Response from(Zone zone) {
			return new Response(
				zone.getId(),
				zone.getMap().getId(),
				zone.getCode(),
				zone.getName(),
				zone.getPolygonJson()
			);
		}
	}
}
