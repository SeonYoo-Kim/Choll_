package com.ssafy.backend.classification.service;

import com.ssafy.backend.classification.domain.ClassificationSection;
import com.ssafy.backend.classification.repository.ClassificationSectionRepository;
import com.ssafy.backend.common.exception.DuplicateResourceException;
import com.ssafy.backend.common.exception.InvalidDomainException;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class ClassificationSectionService {

	private final ClassificationSectionRepository repository;

	public ClassificationSectionService(ClassificationSectionRepository repository) {
		this.repository = repository;
	}

	@Transactional
	public Response create(Request request) {
		validateRange(request.startNumber(), request.endNumber());
		validateDuplicateCode(request.code(), null);
		ClassificationSection parent = resolveParent(request.parentId(), null);
		ClassificationSection section = new ClassificationSection(
			request.code(),
			request.name(),
			parent,
			request.startNumber(),
			request.endNumber()
		);
		return Response.from(repository.save(section));
	}

	public List<Response> findAll() {
		return repository.findAll(Sort.by("startNumber").ascending())
			.stream()
			.map(Response::from)
			.toList();
	}

	public Response findById(Long id) {
		return Response.from(getSection(id));
	}

	@Transactional
	public Response update(Long id, Request request) {
		ClassificationSection section = getSection(id);
		validateRange(request.startNumber(), request.endNumber());
		validateDuplicateCode(request.code(), id);
		ClassificationSection parent = resolveParent(request.parentId(), id);
		section.update(
			request.code(),
			request.name(),
			parent,
			request.startNumber(),
			request.endNumber()
		);
		return Response.from(section);
	}

	@Transactional
	public void delete(Long id) {
		repository.delete(getSection(id));
	}

	public ClassificationSection getSection(Long id) {
		return repository.findById(id)
			.orElseThrow(() -> new ResourceNotFoundException("분류 섹터", id));
	}

	private ClassificationSection resolveParent(Long parentId, Long currentId) {
		if (parentId == null) {
			return null;
		}
		if (parentId.equals(currentId)) {
			throw new InvalidDomainException("분류 섹터는 자기 자신을 상위 분류로 지정할 수 없습니다.");
		}

		ClassificationSection parent = getSection(parentId);
		ClassificationSection ancestor = parent;
		while (ancestor != null) {
			if (ancestor.getId().equals(currentId)) {
				throw new InvalidDomainException("분류 섹터에 순환 참조가 발생합니다.");
			}
			ancestor = ancestor.getParent();
		}
		return parent;
	}

	private void validateRange(BigDecimal startNumber, BigDecimal endNumber) {
		if (startNumber.compareTo(endNumber) > 0) {
			throw new InvalidDomainException("분류 시작 번호는 종료 번호보다 클 수 없습니다.");
		}
	}

	private void validateDuplicateCode(String code, Long id) {
		boolean exists = id == null
			? repository.existsByCode(code)
			: repository.existsByCodeAndIdNot(code, id);
		if (exists) {
			throw new DuplicateResourceException("이미 사용 중인 분류 코드입니다. code=" + code);
		}
	}

	public record Request(
		@NotBlank
		@Size(max = 20)
		@Pattern(regexp = "\\d{3}(\\.\\d+)?", message = "000 또는 813.7 형식이어야 합니다.")
		String code,

		@NotBlank
		@Size(max = 100)
		String name,

		Long parentId,

		@NotNull
		@DecimalMin("0")
		BigDecimal startNumber,

		@NotNull
		@DecimalMin("0")
		BigDecimal endNumber
	) {
	}

	public record Response(
		Long id,
		String code,
		String name,
		Long parentId,
		int depth,
		BigDecimal startNumber,
		BigDecimal endNumber
	) {
		public static Response from(ClassificationSection section) {
			Long parentId = section.getParent() == null ? null : section.getParent().getId();
			return new Response(
				section.getId(),
				section.getCode(),
				section.getName(),
				parentId,
				section.getDepth(),
				section.getStartNumber(),
				section.getEndNumber()
			);
		}
	}
}
