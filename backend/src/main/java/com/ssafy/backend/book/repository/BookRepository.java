package com.ssafy.backend.book.repository;

import com.ssafy.backend.book.domain.Book;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {

	boolean existsByLibraryBookId(String libraryBookId);

	boolean existsByLibraryBookIdAndIdNot(String libraryBookId, Long id);

	boolean existsByRfidUid(String rfidUid);

	boolean existsByRfidUidAndIdNot(String rfidUid, Long id);
}
