package com.ssafy.backend.bookcopy.repository;

import com.ssafy.backend.bookcopy.domain.BookCopy;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookCopyRepository extends JpaRepository<BookCopy, Long> {

	boolean existsByBookId(Long bookId);

	boolean existsByLibraryBookId(String libraryBookId);

	boolean existsByLibraryBookIdAndIdNot(String libraryBookId, Long id);

	boolean existsByRfidUid(String rfidUid);

	boolean existsByRfidUidAndIdNot(String rfidUid, Long id);

	List<BookCopy> findAllByBookIdOrderByLibraryBookIdAsc(Long bookId);

	List<BookCopy> findAllByBookshelfIdOrderByLibraryBookIdAsc(Long bookshelfId);

	List<BookCopy> findAllByBookIdAndBookshelfIdOrderByLibraryBookIdAsc(
		Long bookId,
		Long bookshelfId
	);
}
