package com.ssafy.backend.bookimport;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.backend.bookimport.BookCsvImportBatchWriter.BatchResult;
import com.ssafy.backend.bookimport.BookCsvImportService.ImportReport;
import java.math.BigDecimal;
import java.nio.charset.Charset;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class BookCsvImportServiceTests {

	@Mock
	private BookCsvImportBatchWriter batchWriter;

	@TempDir
	private Path tempDir;

	@Test
	@SuppressWarnings("unchecked")
	void importsMs949CsvAndExtractsClassification() throws Exception {
		String csv = """
			관리구분,등록번호,서명,저자,발행자,발행년도,청구기호,국제표준도서번호(ISBN),자료실
			김영삼도서관,EK0000000001,"100℃ : 뜨거운 기억",최규석,창비,2017,청 911.075-최16ㅂ,978-89-3647-365-5,[김영삼]7F_이음
			""";
		Path csvPath = tempDir.resolve("books.csv");
		Files.writeString(csvPath, csv, Charset.forName("MS949"));
		when(batchWriter.write(anyList())).thenReturn(new BatchResult(1, 1, 0));

		BookCsvImportService service = new BookCsvImportService(batchWriter);
		ImportReport report = service.importFile(csvPath, 0, 10);

		ArgumentCaptor<List<BookImportRow>> captor = ArgumentCaptor.forClass(List.class);
		verify(batchWriter).ensureTopLevelSections();
		verify(batchWriter).write(captor.capture());
		BookImportRow row = captor.getValue().getFirst();

		assertEquals(1, report.readRows());
		assertEquals(1, report.importedBooks());
		assertEquals(1, report.importedCopies());
		assertEquals("9788936473655", row.isbn());
		assertEquals("911.075", row.classificationCode());
		assertEquals(new BigDecimal("911.075"), row.classificationNumber());
		assertEquals("900", row.sectionCode());
		assertEquals("[김영삼]7F_이음", row.roomName());
	}
}
