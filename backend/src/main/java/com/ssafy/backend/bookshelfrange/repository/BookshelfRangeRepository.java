package com.ssafy.backend.bookshelfrange.repository;

import com.ssafy.backend.bookshelfrange.domain.BookshelfRange;
import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface BookshelfRangeRepository extends JpaRepository<BookshelfRange, Long> {

	List<BookshelfRange> findAllByBookshelfIdOrderByStartNumberAsc(Long bookshelfId);

	@Query("""
		select case when count(r) > 0 then true else false end
		from BookshelfRange r
		where r.bookshelf.zone.map.id = :mapId
		  and r.startNumber <= :endNumber
		  and r.endNumber >= :startNumber
		""")
	boolean existsOverlappingRange(
		@Param("mapId") Long mapId,
		@Param("startNumber") BigDecimal startNumber,
		@Param("endNumber") BigDecimal endNumber
	);

	@Query("""
		select case when count(r) > 0 then true else false end
		from BookshelfRange r
		where r.bookshelf.zone.map.id = :mapId
		  and r.id <> :id
		  and r.startNumber <= :endNumber
		  and r.endNumber >= :startNumber
		""")
	boolean existsOverlappingRangeExceptId(
		@Param("mapId") Long mapId,
		@Param("id") Long id,
		@Param("startNumber") BigDecimal startNumber,
		@Param("endNumber") BigDecimal endNumber
	);

	@Query("""
		select r
		from BookshelfRange r
		where r.bookshelf.zone.map.id = :mapId
		  and :classificationNumber between r.startNumber and r.endNumber
		""")
	Optional<BookshelfRange> findPlacement(
		@Param("mapId") Long mapId,
		@Param("classificationNumber") BigDecimal classificationNumber
	);
}
