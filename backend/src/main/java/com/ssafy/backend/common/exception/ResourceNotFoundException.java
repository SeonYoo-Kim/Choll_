package com.ssafy.backend.common.exception;

public class ResourceNotFoundException extends RuntimeException {

	public ResourceNotFoundException(String resourceName, Long id) {
		super("%s을(를) 찾을 수 없습니다. id=%d".formatted(resourceName, id));
	}

	public ResourceNotFoundException(String resourceName, String condition) {
		super("%s을(를) 찾을 수 없습니다. %s".formatted(resourceName, condition));
	}
}
