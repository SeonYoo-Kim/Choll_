package com.ssafy.backend.map.service;

import com.ssafy.backend.common.exception.DuplicateResourceException;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import com.ssafy.backend.map.domain.LibraryMap;
import com.ssafy.backend.map.repository.LibraryMapRepository;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class LibraryMapService {

	private final LibraryMapRepository repository;

	public LibraryMapService(LibraryMapRepository repository) {
		this.repository = repository;
	}

	@Transactional
	public Response create(Request request) {
		validateDuplicateName(request.name(), null);
		LibraryMap map = new LibraryMap(
			request.name(),
			request.imageUrl(),
			request.resolution(),
			request.originX(),
			request.originY(),
			request.width(),
			request.height()
		);
		return Response.from(repository.save(map));
	}

	public List<Response> findAll() {
		return repository.findAll(Sort.by("id").ascending())
			.stream()
			.map(Response::from)
			.toList();
	}

	public Response findById(Long id) {
		return Response.from(getMap(id));
	}

	@Transactional
	public Response update(Long id, Request request) {
		LibraryMap map = getMap(id);
		validateDuplicateName(request.name(), id);
		map.update(
			request.name(),
			request.imageUrl(),
			request.resolution(),
			request.originX(),
			request.originY(),
			request.width(),
			request.height()
		);
		return Response.from(map);
	}

	@Transactional
	public void delete(Long id) {
		repository.delete(getMap(id));
	}

	public LibraryMap getMap(Long id) {
		return repository.findById(id)
			.orElseThrow(() -> new ResourceNotFoundException("지도", id));
	}

	private void validateDuplicateName(String name, Long id) {
		boolean exists = id == null
			? repository.existsByName(name)
			: repository.existsByNameAndIdNot(name, id);
		if (exists) {
			throw new DuplicateResourceException("이미 사용 중인 지도 이름입니다. name=" + name);
		}
	}

	public record Request(
		@NotBlank
		@Size(max = 100)
		String name,

		@NotBlank
		@Size(max = 500)
		String imageUrl,

		@NotNull
		@Positive
		BigDecimal resolution,

		@NotNull
		BigDecimal originX,

		@NotNull
		BigDecimal originY,

		@Positive
		int width,

		@Positive
		int height
	) {
	}

	@Schema(name = "MapInfo")
	public record Response(
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		Long id,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		String name,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		String imageUrl,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		BigDecimal resolution,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		BigDecimal originX,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		BigDecimal originY,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		int imageWidth,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		int imageHeight
	) {
		public static Response from(LibraryMap map) {
			return new Response(
				map.getId(),
				map.getName(),
				map.getImageUrl(),
				map.getResolution(),
				map.getOriginX(),
				map.getOriginY(),
				map.getWidth(),
				map.getHeight()
			);
		}
	}
}
