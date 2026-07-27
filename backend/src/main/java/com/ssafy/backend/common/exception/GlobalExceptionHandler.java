package com.ssafy.backend.common.exception;

import jakarta.servlet.http.HttpServletRequest;
import java.time.LocalDateTime;
import java.util.stream.Collectors;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

	@ExceptionHandler(ResourceNotFoundException.class)
	public ResponseEntity<ErrorResponse> handleNotFound(
		ResourceNotFoundException exception,
		HttpServletRequest request
	) {
		return buildResponse(HttpStatus.NOT_FOUND, "RESOURCE_NOT_FOUND", exception.getMessage(), request);
	}

	@ExceptionHandler(DuplicateResourceException.class)
	public ResponseEntity<ErrorResponse> handleDuplicate(
		DuplicateResourceException exception,
		HttpServletRequest request
	) {
		return buildResponse(HttpStatus.CONFLICT, "DUPLICATE_RESOURCE", exception.getMessage(), request);
	}

	@ExceptionHandler(InvalidDomainException.class)
	public ResponseEntity<ErrorResponse> handleInvalidDomain(
		InvalidDomainException exception,
		HttpServletRequest request
	) {
		return buildResponse(HttpStatus.BAD_REQUEST, "INVALID_DOMAIN", exception.getMessage(), request);
	}

	@ExceptionHandler(MethodArgumentNotValidException.class)
	public ResponseEntity<ErrorResponse> handleValidation(
		MethodArgumentNotValidException exception,
		HttpServletRequest request
	) {
		String message = exception.getBindingResult()
			.getFieldErrors()
			.stream()
			.map(error -> "%s: %s".formatted(error.getField(), error.getDefaultMessage()))
			.collect(Collectors.joining(", "));

		return buildResponse(HttpStatus.BAD_REQUEST, "VALIDATION_ERROR", message, request);
	}

	@ExceptionHandler(DataIntegrityViolationException.class)
	public ResponseEntity<ErrorResponse> handleDataIntegrity(
		DataIntegrityViolationException exception,
		HttpServletRequest request
	) {
		return buildResponse(
			HttpStatus.CONFLICT,
			"DATA_INTEGRITY_VIOLATION",
			"연결된 데이터가 있거나 중복된 값이 있어 요청을 처리할 수 없습니다.",
			request
		);
	}

	private ResponseEntity<ErrorResponse> buildResponse(
		HttpStatus status,
		String code,
		String message,
		HttpServletRequest request
	) {
		ErrorResponse response = new ErrorResponse(
			LocalDateTime.now(),
			status.value(),
			code,
			message,
			request.getRequestURI()
		);
		return ResponseEntity.status(status).body(response);
	}
}
