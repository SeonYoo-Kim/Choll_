package com.ssafy.backend.bookshelf.service;

import com.ssafy.backend.bookshelf.domain.Bookshelf;
import com.ssafy.backend.bookshelf.repository.BookshelfRepository;
import com.ssafy.backend.common.exception.DuplicateResourceException;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import com.ssafy.backend.zone.domain.Zone;
import com.ssafy.backend.zone.service.ZoneService;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class BookshelfService {

	private final BookshelfRepository repository;
	private final ZoneService zoneService;

	public BookshelfService(BookshelfRepository repository, ZoneService zoneService) {
		this.repository = repository;
		this.zoneService = zoneService;
	}

	@Transactional
	public Response create(Request request) {
		validateDuplicateNumber(request.zoneId(), request.shelfNumber(), null);
		Zone zone = zoneService.getZone(request.zoneId());
		Bookshelf bookshelf = new Bookshelf(
			zone,
			request.shelfNumber(),
			request.name(),
			request.x(),
			request.y(),
			request.displayOrder()
		);
		return Response.from(repository.save(bookshelf));
	}

	public List<Response> findAll(Long zoneId) {
		List<Bookshelf> bookshelves = zoneId == null
			? repository.findAll(Sort.by("displayOrder").ascending())
			: repository.findAllByZoneIdOrderByDisplayOrderAsc(zoneId);
		return bookshelves.stream().map(Response::from).toList();
	}

	public Response findById(Long id) {
		return Response.from(getBookshelf(id));
	}

	@Transactional
	public Response update(Long id, Request request) {
		Bookshelf bookshelf = getBookshelf(id);
		validateDuplicateNumber(request.zoneId(), request.shelfNumber(), id);
		Zone zone = zoneService.getZone(request.zoneId());
		bookshelf.update(
			zone,
			request.shelfNumber(),
			request.name(),
			request.x(),
			request.y(),
			request.displayOrder()
		);
		return Response.from(bookshelf);
	}

	@Transactional
	public void delete(Long id) {
		repository.delete(getBookshelf(id));
	}

	public Bookshelf getBookshelf(Long id) {
		return repository.findById(id)
			.orElseThrow(() -> new ResourceNotFoundException("책장", id));
	}

	private void validateDuplicateNumber(Long zoneId, String shelfNumber, Long id) {
		boolean exists = id == null
			? repository.existsByZoneIdAndShelfNumber(zoneId, shelfNumber)
			: repository.existsByZoneIdAndShelfNumberAndIdNot(zoneId, shelfNumber, id);
		if (exists) {
			throw new DuplicateResourceException(
				"같은 구역에서 이미 사용 중인 책장 번호입니다. shelfNumber=" + shelfNumber
			);
		}
	}

	public record Request(
		@NotNull
		Long zoneId,

		@NotBlank
		@Size(max = 50)
		String shelfNumber,

		@NotBlank
		@Size(max = 100)
		String name,

		@NotNull
		BigDecimal x,

		@NotNull
		BigDecimal y,

		@PositiveOrZero
		int displayOrder
	) {
	}

	public record Response(
		Long id,
		Long zoneId,
		String zoneCode,
		String shelfNumber,
		String name,
		BigDecimal x,
		BigDecimal y,
		int displayOrder
	) {
		public static Response from(Bookshelf bookshelf) {
			return new Response(
				bookshelf.getId(),
				bookshelf.getZone().getId(),
				bookshelf.getZone().getCode(),
				bookshelf.getShelfNumber(),
				bookshelf.getName(),
				bookshelf.getX(),
				bookshelf.getY(),
				bookshelf.getDisplayOrder()
			);
		}
	}
}
