package com.ssafy.backend.websocket;

import java.io.IOException;
import java.net.URI;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class CartWebSocketHandler extends TextWebSocketHandler {

	private static final Logger log = LoggerFactory.getLogger(CartWebSocketHandler.class);
	private static final int SEND_TIME_LIMIT_MS = 5_000;
	private static final int BUFFER_SIZE_LIMIT_BYTES = 64 * 1024;

	private final ConcurrentHashMap<Long, Set<WebSocketSession>> sessionsByCartId =
		new ConcurrentHashMap<>();

	@Override
	public void afterConnectionEstablished(WebSocketSession session) {
		Long cartId = extractCartId(session.getUri());
		WebSocketSession concurrentSession = new ConcurrentWebSocketSessionDecorator(
			session,
			SEND_TIME_LIMIT_MS,
			BUFFER_SIZE_LIMIT_BYTES
		);
		concurrentSession.getAttributes().put("cartId", cartId);
		sessionsByCartId.computeIfAbsent(cartId, ignored -> ConcurrentHashMap.newKeySet())
			.add(concurrentSession);
		log.info("카트 WebSocket 연결 cartId={}, sessionId={}", cartId, session.getId());
	}

	@Override
	public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
		removeSession(session.getId());
		log.info("카트 WebSocket 종료 sessionId={}, status={}", session.getId(), status);
	}

	@Override
	public void handleTransportError(WebSocketSession session, Throwable exception) {
		removeSession(session.getId());
		log.warn("카트 WebSocket 전송 오류 sessionId={}", session.getId(), exception);
	}

	public void send(Long cartId, String json) {
		Set<WebSocketSession> sessions = sessionsByCartId.getOrDefault(cartId, Set.of());
		TextMessage message = new TextMessage(json);

		for (WebSocketSession session : sessions) {
			if (!session.isOpen()) {
				removeSession(session.getId());
				continue;
			}
			try {
				session.sendMessage(message);
			} catch (IOException exception) {
				removeSession(session.getId());
				log.warn(
					"카트 WebSocket 메시지 전송 실패 cartId={}, sessionId={}",
					cartId,
					session.getId(),
					exception
				);
			}
		}
	}

	private Long extractCartId(URI uri) {
		if (uri == null) {
			throw new IllegalArgumentException("WebSocket 요청 URI가 없습니다.");
		}
		String path = uri.getPath();
		String value = path.substring(path.lastIndexOf('/') + 1);
		try {
			return Long.valueOf(value);
		} catch (NumberFormatException exception) {
			throw new IllegalArgumentException("올바르지 않은 cartId입니다: " + value, exception);
		}
	}

	private void removeSession(String sessionId) {
		sessionsByCartId.forEach((cartId, sessions) -> {
			sessions.removeIf(session -> session.getId().equals(sessionId));
			if (sessions.isEmpty()) {
				sessionsByCartId.remove(cartId, sessions);
			}
		});
	}
}
