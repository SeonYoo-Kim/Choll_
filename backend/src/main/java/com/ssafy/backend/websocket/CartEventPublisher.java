package com.ssafy.backend.websocket;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

/**
 * BE→FE WebSocket 이벤트를 {"type":...,"payload":...} 형식으로 직렬화해 발행한다.
 */
@Component
public class CartEventPublisher {

	private static final Logger log = LoggerFactory.getLogger(CartEventPublisher.class);

	private final CartWebSocketHandler webSocketHandler;
	private final ObjectMapper objectMapper;

	public CartEventPublisher(
		CartWebSocketHandler webSocketHandler,
		ObjectMapper objectMapper
	) {
		this.webSocketHandler = webSocketHandler;
		this.objectMapper = objectMapper;
	}

	public void publish(Long cartId, String type, Object payload) {
		try {
			String json = objectMapper.writeValueAsString(new Event(type, payload));
			webSocketHandler.send(cartId, json);
		} catch (JacksonException exception) {
			log.warn(
				"WebSocket 이벤트 직렬화 실패 cartId={}, type={}",
				cartId,
				type,
				exception
			);
		}
	}

	private record Event(String type, Object payload) {
	}
}
