package com.ssafy.backend.bookimport;

import com.ssafy.backend.book.domain.Book;
import com.ssafy.backend.book.repository.BookRepository;
import com.ssafy.backend.bookcopy.domain.BookCopy;
import com.ssafy.backend.bookcopy.domain.BookCopyStatus;
import com.ssafy.backend.bookcopy.repository.BookCopyRepository;
import com.ssafy.backend.classification.domain.ClassificationSection;
import com.ssafy.backend.classification.repository.ClassificationSectionRepository;
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class BookCsvImportBatchWriter {

	private static final Map<String, String> SECTION_NAMES = createSectionNames();

	private final BookRepository bookRepository;
	private final BookCopyRepository bookCopyRepository;
	private final ClassificationSectionRepository sectionRepository;

	public BookCsvImportBatchWriter(
		BookRepository bookRepository,
		BookCopyRepository bookCopyRepository,
		ClassificationSectionRepository sectionRepository
	) {
		this.bookRepository = bookRepository;
		this.bookCopyRepository = bookCopyRepository;
		this.sectionRepository = sectionRepository;
	}

	@Transactional
	public void ensureTopLevelSections() {
		for (Map.Entry<String, String> entry : SECTION_NAMES.entrySet()) {
			if (sectionRepository.existsByCode(entry.getKey())) {
				continue;
			}

			int start = Integer.parseInt(entry.getKey());
			sectionRepository.save(
				new ClassificationSection(
					entry.getKey(),
					entry.getValue(),
					null,
					BigDecimal.valueOf(start),
					BigDecimal.valueOf(start + 99).add(new BigDecimal("0.99999"))
				)
			);
		}
	}

	@Transactional
	public BatchResult write(List<BookImportRow> rows) {
		Set<String> requestedIsbns = new HashSet<>();
		Set<String> requestedLibraryBookIds = new HashSet<>();
		for (BookImportRow row : rows) {
			if (row.isbn() != null) {
				requestedIsbns.add(row.isbn());
			}
			requestedLibraryBookIds.add(row.libraryBookId());
		}

		Map<String, Book> booksByIsbn = new HashMap<>();
		for (Book book : bookRepository.findAllByIsbnIn(requestedIsbns)) {
			booksByIsbn.put(book.getIsbn(), book);
		}

		Set<String> existingLibraryBookIds = new HashSet<>(
			bookCopyRepository.findExistingLibraryBookIds(requestedLibraryBookIds)
		);
		Map<String, ClassificationSection> sectionsByCode = new HashMap<>();
		for (ClassificationSection section : sectionRepository.findAll()) {
			sectionsByCode.put(section.getCode(), section);
		}

		int importedBooks = 0;
		int importedCopies = 0;
		int skippedCopies = 0;
		for (BookImportRow row : rows) {
			if (!existingLibraryBookIds.add(row.libraryBookId())) {
				skippedCopies++;
				continue;
			}

			ClassificationSection section = sectionsByCode.get(row.sectionCode());
			if (section == null) {
				skippedCopies++;
				continue;
			}

			Book book = row.isbn() == null ? null : booksByIsbn.get(row.isbn());
			if (book == null) {
				book = bookRepository.save(
					new Book(
						row.isbn(),
						row.title(),
						row.author(),
						row.publisher(),
						row.publicationYear(),
						row.classificationCode(),
						row.classificationNumber(),
						section
					)
				);
				importedBooks++;
				if (row.isbn() != null) {
					booksByIsbn.put(row.isbn(), book);
				}
			}

			bookCopyRepository.save(
				new BookCopy(
					book,
					row.libraryBookId(),
					null,
					row.callNumber(),
					row.libraryName(),
					row.roomName(),
					null,
					BookCopyStatus.AVAILABLE
				)
			);
			importedCopies++;
		}
		return new BatchResult(importedBooks, importedCopies, skippedCopies);
	}

	private static Map<String, String> createSectionNames() {
		Map<String, String> names = new LinkedHashMap<>();
		names.put("000", "총류");
		names.put("100", "철학");
		names.put("200", "종교");
		names.put("300", "사회과학");
		names.put("400", "자연과학");
		names.put("500", "기술과학");
		names.put("600", "예술");
		names.put("700", "언어");
		names.put("800", "문학");
		names.put("900", "역사");
		return names;
	}

	public record BatchResult(int importedBooks, int importedCopies, int skippedCopies) {
	}
}
