package com.ssafy.backend.websocket;

import java.net.URI;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.BinaryMessage;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.BinaryWebSocketHandler;
import org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator;

/**
 * 카트 카메라 영상(JPEG 프레임) 릴레이.
 *
 * <pre>
 * Jetson ─(binary WS: /ws/carts/{id}/video/publish)→ BE ─→ 시청자들 (/ws/carts/{id}/video)
 * </pre>
 *
 * 프레임 = JPEG 1장 = 바이너리 메시지 1건. BE는 디코딩 없이 그대로 중계한다.
 * 느린 시청자는 버퍼 초과 시 프레임이 버려지거나(OVERFLOW 시 세션 종료) 연결이
 * 끊기며, 영상은 최신 프레임만 의미 있으므로 재접속으로 복구한다.
 */
@Component
public class VideoRelayHandler extends BinaryWebSocketHandler {

	private static final Logger log = LoggerFactory.getLogger(VideoRelayHandler.class);
	private static final int SEND_TIME_LIMIT_MS = 1_000;
	// 640x480 JPEG(~50KB) 기준 수 프레임 분량 — 초과하면 느린 시청자로 보고 정리
	private static final int BUFFER_SIZE_LIMIT_BYTES = 512 * 1024;
	private static final String ROLE_PUBLISHER = "publisher";
	private static final String ROLE_VIEWER = "viewer";

	private final Map<Long, WebSocketSession> publisherByCartId = new ConcurrentHashMap<>();
	private final Map<Long, Set<WebSocketSession>> viewersByCartId = new ConcurrentHashMap<>();

	@Override
	public void afterConnectionEstablished(WebSocketSession session) {
		// JPEG 프레임(수십 KB)이 컨테이너 기본 한도(8KB)를 넘으므로 세션별로 확장
		session.setBinaryMessageSizeLimit(1024 * 1024);
		Endpoint endpoint = parseEndpoint(session.getUri());
		session.getAttributes().put("cartId", endpoint.cartId());
		session.getAttributes().put("role", endpoint.role());

		if (ROLE_PUBLISHER.equals(endpoint.role())) {
			WebSocketSession previous =
				publisherByCartId.put(endpoint.cartId(), session);
			closeQuietly(previous); // 재접속한 Jetson이 이전 세션을 대체
			log.info(
				"영상 발행자 연결 cartId={}, sessionId={}",
				endpoint.cartId(),
				session.getId()
			);
			return;
		}

		WebSocketSession decorated = new ConcurrentWebSocketSessionDecorator(
			session,
			SEND_TIME_LIMIT_MS,
			BUFFER_SIZE_LIMIT_BYTES
		);
		viewersByCartId
			.computeIfAbsent(endpoint.cartId(), ignored -> ConcurrentHashMap.newKeySet())
			.add(decorated);
		log.info(
			"영상 시청자 연결 cartId={}, sessionId={}",
			endpoint.cartId(),
			session.getId()
		);
	}

	@Override
	protected void handleBinaryMessage(WebSocketSession session, BinaryMessage message) {
		if (!ROLE_PUBLISHER.equals(session.getAttributes().get("role"))) {
			return; // 시청자가 보낸 바이너리는 무시
		}
		Long cartId = (Long) session.getAttributes().get("cartId");
		Set<WebSocketSession> viewers = viewersByCartId.getOrDefault(cartId, Set.of());

		for (WebSocketSession viewer : viewers) {
			if (!viewer.isOpen()) {
				viewers.remove(viewer);
				continue;
			}
			try {
				// ByteBuffer 위치 공유를 피하기 위해 시청자마다 읽기 전용 뷰로 전송
				viewer.sendMessage(
					new BinaryMessage(message.getPayload().asReadOnlyBuffer())
				);
			} catch (Exception exception) {
				viewers.remove(viewer);
				closeQuietly(viewer);
				log.warn(
					"영상 프레임 전송 실패로 시청자 정리 cartId={}, sessionId={}",
					cartId,
					viewer.getId()
				);
			}
		}
	}

	@Override
	public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
		Long cartId = (Long) session.getAttributes().get("cartId");
		if (cartId == null) {
			return;
		}
		publisherByCartId.remove(cartId, session);
		Set<WebSocketSession> viewers = viewersByCartId.get(cartId);
		if (viewers != null) {
			viewers.removeIf(viewer -> viewer.getId().equals(session.getId()));
		}
		log.info("영상 세션 종료 cartId={}, sessionId={}, status={}", cartId,
			session.getId(), status);
	}

	@Override
	public void handleTransportError(WebSocketSession session, Throwable exception) {
		log.warn("영상 세션 전송 오류 sessionId={}", session.getId(), exception);
		closeQuietly(session);
	}

	/** URI 경로 /ws/carts/{id}/video[/publish] 에서 cartId와 역할을 해석한다. */
	private Endpoint parseEndpoint(URI uri) {
		if (uri == null) {
			throw new IllegalArgumentException("WebSocket 요청 URI가 없습니다.");
		}
		String[] segments = uri.getPath().split("/");
		// ["", "ws", "carts", "{id}", "video"] 또는 [..., "video", "publish"]
		boolean publisher = "publish".equals(segments[segments.length - 1]);
		String cartIdSegment = publisher
			? segments[segments.length - 3]
			: segments[segments.length - 2];
		try {
			return new Endpoint(
				Long.valueOf(cartIdSegment),
				publisher ? ROLE_PUBLISHER : ROLE_VIEWER
			);
		} catch (NumberFormatException exception) {
			throw new IllegalArgumentException(
				"올바르지 않은 cartId입니다: " + cartIdSegment, exception);
		}
	}

	private void closeQuietly(WebSocketSession session) {
		if (session == null) {
			return;
		}
		try {
			session.close(CloseStatus.NORMAL);
		} catch (Exception ignored) {
			// 이미 닫힌 세션 정리 중 예외는 무시
		}
	}

	private record Endpoint(Long cartId, String role) {
	}
}
