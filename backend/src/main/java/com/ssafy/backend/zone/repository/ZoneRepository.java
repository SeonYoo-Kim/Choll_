package com.ssafy.backend.zone.repository;

import com.ssafy.backend.zone.domain.Zone;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ZoneRepository extends JpaRepository<Zone, Long> {

	boolean existsByMapIdAndCode(Long mapId, String code);

	boolean existsByMapIdAndCodeAndIdNot(Long mapId, String code, Long id);

	List<Zone> findAllByMapIdOrderByCodeAsc(Long mapId);
}
