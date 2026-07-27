package com.ssafy.backend.bookimport;

import com.ssafy.backend.bookimport.BookCsvImportService.ImportReport;
import java.nio.file.Path;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix = "book.import", name = "enabled", havingValue = "true")
public class BookCsvImportRunner implements ApplicationRunner {

	private static final Logger log = LoggerFactory.getLogger(BookCsvImportRunner.class);

	private final BookCsvImportService importService;
	private final String importPath;
	private final int limit;
	private final int batchSize;

	public BookCsvImportRunner(
		BookCsvImportService importService,
		@Value("${book.import.path}") String importPath,
		@Value("${book.import.limit}") int limit,
		@Value("${book.import.batch-size}") int batchSize
	) {
		this.importService = importService;
		this.importPath = importPath;
		this.limit = limit;
		this.batchSize = batchSize;
	}

	@Override
	public void run(ApplicationArguments args) throws Exception {
		if (importPath.isBlank()) {
			throw new IllegalArgumentException(
				"BOOK_IMPORT_ENABLED=true일 때 BOOK_IMPORT_PATH가 필요합니다."
			);
		}

		log.info("도서 CSV 가져오기를 시작합니다. path={}, limit={}", importPath, limit);
		ImportReport report = importService.importFile(Path.of(importPath), limit, batchSize);
		log.info(
			"도서 CSV 가져오기를 완료했습니다. readRows={}, importedBooks={}, "
				+ "importedCopies={}, skippedCopies={}, invalidRows={}",
			report.readRows(),
			report.importedBooks(),
			report.importedCopies(),
			report.skippedCopies(),
			report.invalidRows()
		);
	}
}
