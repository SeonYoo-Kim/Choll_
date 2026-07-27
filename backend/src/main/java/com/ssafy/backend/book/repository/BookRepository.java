package com.ssafy.backend.book.repository;

import com.ssafy.backend.book.domain.Book;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {

	Optional<Book> findByIsbn(String isbn);

	boolean existsByIsbn(String isbn);

	boolean existsByIsbnAndIdNot(String isbn, Long id);
}
