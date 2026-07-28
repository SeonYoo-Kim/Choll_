package com.ssafy.backend.map.repository;

import com.ssafy.backend.map.domain.LibraryMap;
import org.springframework.data.jpa.repository.JpaRepository;

public interface LibraryMapRepository extends JpaRepository<LibraryMap, Long> {

	boolean existsByName(String name);

	boolean existsByNameAndIdNot(String name, Long id);
}
