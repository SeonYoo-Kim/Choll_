package com.ssafy.backend.bookimport;

import java.math.BigDecimal;

record BookImportRow(
	String libraryBookId,
	String isbn,
	String title,
	String author,
	String publisher,
	Integer publicationYear,
	String callNumber,
	String libraryName,
	String roomName,
	String classificationCode,
	BigDecimal classificationNumber,
	String sectionCode
) {
}
