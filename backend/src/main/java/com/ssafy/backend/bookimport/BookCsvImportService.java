package com.ssafy.backend.bookimport;

import com.ssafy.backend.bookimport.BookCsvImportBatchWriter.BatchResult;
import java.io.IOException;
import java.io.Reader;
import java.math.BigDecimal;
import java.nio.charset.Charset;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;
import org.springframework.stereotype.Service;

@Service
public class BookCsvImportService {

	private static final Charset SOURCE_CHARSET = Charset.forName("MS949");
	private static final Pattern CLASSIFICATION_PATTERN = Pattern.compile(
		"(?<!\\d)(\\d{3}(?:\\.\\d+)?)"
	);
	private static final Pattern YEAR_PATTERN = Pattern.compile("(\\d{4})");

	private final BookCsvImportBatchWriter batchWriter;

	public BookCsvImportService(BookCsvImportBatchWriter batchWriter) {
		this.batchWriter = batchWriter;
	}

	public ImportReport importFile(Path path, int limit, int batchSize) throws IOException {
		validateOptions(path, limit, batchSize);
		batchWriter.ensureTopLevelSections();

		int readRows = 0;
		int invalidRows = 0;
		int importedBooks = 0;
		int importedCopies = 0;
		int skippedCopies = 0;
		List<BookImportRow> batch = new ArrayList<>(batchSize);

		CSVFormat format = CSVFormat.DEFAULT.builder()
			.setHeader()
			.setSkipHeaderRecord(true)
			.setIgnoreEmptyLines(true)
			.setTrim(true)
			.get();
		try (
			Reader reader = Files.newBufferedReader(path, SOURCE_CHARSET);
			CSVParser parser = format.parse(reader)
		) {
			for (CSVRecord record : parser) {
				if (limit > 0 && readRows >= limit) {
					break;
				}
				readRows++;

				BookImportRow row = toRow(record);
				if (row == null) {
					invalidRows++;
					continue;
				}
				batch.add(row);

				if (batch.size() >= batchSize) {
					BatchResult result = batchWriter.write(batch);
					importedBooks += result.importedBooks();
					importedCopies += result.importedCopies();
					skippedCopies += result.skippedCopies();
					batch.clear();
				}
			}
		}

		if (!batch.isEmpty()) {
			BatchResult result = batchWriter.write(batch);
			importedBooks += result.importedBooks();
			importedCopies += result.importedCopies();
			skippedCopies += result.skippedCopies();
		}

		return new ImportReport(
			readRows,
			importedBooks,
			importedCopies,
			skippedCopies,
			invalidRows
		);
	}

	private BookImportRow toRow(CSVRecord record) {
		String libraryBookId = trimToNull(record.get("등록번호"), 100);
		String title = trimToNull(record.get("서명"), 255);
		String callNumber = trimToNull(record.get("청구기호"), 255);
		Classification classification = parseClassification(callNumber);
		if (
			libraryBookId == null
				|| title == null
				|| callNumber == null
				|| classification == null
		) {
			return null;
		}

		return new BookImportRow(
			libraryBookId,
			normalizeIsbn(record.get("국제표준도서번호(ISBN)")),
			title,
			trimToNull(record.get("저자"), 255),
			trimToNull(record.get("발행자"), 255),
			parsePublicationYear(record.get("발행년도")),
			callNumber,
			valueOrUnknown(record.get("관리구분"), 100),
			valueOrUnknown(record.get("자료실"), 100),
			classification.code(),
			classification.number(),
			classification.sectionCode()
		);
	}

	private Classification parseClassification(String callNumber) {
		if (callNumber == null) {
			return null;
		}
		Matcher matcher = CLASSIFICATION_PATTERN.matcher(callNumber);
		if (!matcher.find()) {
			return null;
		}

		String code = matcher.group(1);
		BigDecimal number = new BigDecimal(code);
		int sectionStart = number.intValue() / 100 * 100;
		return new Classification(code, number, "%03d".formatted(sectionStart));
	}

	private String normalizeIsbn(String value) {
		String digits = value == null ? "" : value.replaceAll("\\D", "");
		return digits.length() == 10 || digits.length() == 13 ? digits : null;
	}

	private Integer parsePublicationYear(String value) {
		if (value == null) {
			return null;
		}
		Matcher matcher = YEAR_PATTERN.matcher(value);
		return matcher.find() ? Integer.valueOf(matcher.group(1)) : null;
	}

	private String valueOrUnknown(String value, int maxLength) {
		String normalized = trimToNull(value, maxLength);
		return normalized == null ? "미상" : normalized;
	}

	private String trimToNull(String value, int maxLength) {
		if (value == null || value.isBlank()) {
			return null;
		}
		String trimmed = value.trim();
		return trimmed.length() <= maxLength ? trimmed : trimmed.substring(0, maxLength);
	}

	private void validateOptions(Path path, int limit, int batchSize) {
		if (!Files.isRegularFile(path)) {
			throw new IllegalArgumentException("도서 CSV 파일을 찾을 수 없습니다. path=" + path);
		}
		if (limit < 0) {
			throw new IllegalArgumentException("가져오기 제한은 0 이상이어야 합니다.");
		}
		if (batchSize <= 0 || batchSize > 1000) {
			throw new IllegalArgumentException("배치 크기는 1~1000 사이여야 합니다.");
		}
	}

	private record Classification(String code, BigDecimal number, String sectionCode) {
	}

	public record ImportReport(
		int readRows,
		int importedBooks,
		int importedCopies,
		int skippedCopies,
		int invalidRows
	) {
	}
}
