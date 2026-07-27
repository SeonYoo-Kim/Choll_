package com.ssafy.backend.bookshelf.repository;

import com.ssafy.backend.bookshelf.domain.Bookshelf;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookshelfRepository extends JpaRepository<Bookshelf, Long> {

	boolean existsByZoneIdAndShelfNumber(Long zoneId, String shelfNumber);

	boolean existsByZoneIdAndShelfNumberAndIdNot(Long zoneId, String shelfNumber, Long id);

	List<Bookshelf> findAllByZoneIdOrderByDisplayOrderAsc(Long zoneId);
}
