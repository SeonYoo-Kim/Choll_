package com.ssafy.backend.book.repository;

import com.ssafy.backend.book.domain.Book;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {

	Optional<Book> findByIsbn(String isbn);

	List<Book> findAllByIsbnIn(Collection<String> isbns);

	boolean existsByIsbn(String isbn);

	boolean existsByIsbnAndIdNot(String isbn, Long id);
}
