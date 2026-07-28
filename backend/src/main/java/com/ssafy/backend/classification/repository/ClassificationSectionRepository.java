package com.ssafy.backend.classification.repository;

import com.ssafy.backend.classification.domain.ClassificationSection;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ClassificationSectionRepository extends JpaRepository<ClassificationSection, Long> {

	boolean existsByCode(String code);

	boolean existsByCodeAndIdNot(String code, Long id);
}
