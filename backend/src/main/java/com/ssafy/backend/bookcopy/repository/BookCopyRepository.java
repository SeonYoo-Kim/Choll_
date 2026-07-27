package com.ssafy.backend.bookcopy.repository;

import com.ssafy.backend.bookcopy.domain.BookCopy;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface BookCopyRepository extends JpaRepository<BookCopy, Long> {

	boolean existsByBookId(Long bookId);

	boolean existsByLibraryBookId(String libraryBookId);

	boolean existsByLibraryBookIdAndIdNot(String libraryBookId, Long id);

	boolean existsByRfidUid(String rfidUid);

	boolean existsByRfidUidAndIdNot(String rfidUid, Long id);

	@Query("""
		select copy.libraryBookId
		from BookCopy copy
		where copy.libraryBookId in :libraryBookIds
		""")
	List<String> findExistingLibraryBookIds(Collection<String> libraryBookIds);

	List<BookCopy> findAllByBookIdOrderByLibraryBookIdAsc(Long bookId);

	List<BookCopy> findAllByBookshelfIdOrderByLibraryBookIdAsc(Long bookshelfId);

	List<BookCopy> findAllByBookIdAndBookshelfIdOrderByLibraryBookIdAsc(
		Long bookId,
		Long bookshelfId
	);

	@Query("""
		select copy
		from BookCopy copy
		join fetch copy.book
		left join fetch copy.bookshelf bookshelf
		left join fetch bookshelf.zone
		where copy.rfidUid = :rfidUid
		""")
	Optional<BookCopy> findByRfidUidWithLocation(@Param("rfidUid") String rfidUid);

	@Query(
		value = """
			select copy
			from BookCopy copy
			join fetch copy.book
			join fetch copy.bookshelf bookshelf
			join fetch bookshelf.zone zone
			where zone.id = :zoneId
			order by bookshelf.displayOrder, copy.callNumber, copy.libraryBookId
			""",
		countQuery = """
			select count(copy)
			from BookCopy copy
			join copy.bookshelf bookshelf
			join bookshelf.zone zone
			where zone.id = :zoneId
			"""
	)
	Page<BookCopy> findAllByZoneId(
		@Param("zoneId") Long zoneId,
		Pageable pageable
	);
}
