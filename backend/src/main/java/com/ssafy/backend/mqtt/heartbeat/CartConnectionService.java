package com.ssafy.backend.mqtt.heartbeat;

import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.domain.CartConnectionStatus;
import com.ssafy.backend.cart.repository.CartRepository;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import com.ssafy.backend.websocket.CartEventPublisher;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 카트 연결 상태(ONLINE/OFFLINE) 판정.
 * 하트비트·텔레메트리 수신 시 ONLINE 처리하고, 워치독이 타임아웃된 카트를 OFFLINE으로
 * 전환한다. 상태가 바뀔 때마다 CART_CONNECTION_UPDATED WebSocket 이벤트를 발행한다.
 */
@Service
public class CartConnectionService {

	private static final Logger log = LoggerFactory.getLogger(CartConnectionService.class);
	private static final ZoneId DATABASE_ZONE = ZoneId.of("Asia/Seoul");
	private static final String CONNECTION_EVENT_TYPE = "CART_CONNECTION_UPDATED";

	private final CartRepository cartRepository;
	private final CartEventPublisher eventPublisher;
	private final long offlineTimeoutSeconds;

	public CartConnectionService(
		CartRepository cartRepository,
		CartEventPublisher eventPublisher,
		@Value("${cart.connection.offline-timeout-seconds:15}") long offlineTimeoutSeconds
	) {
		this.cartRepository = cartRepository;
		this.eventPublisher = eventPublisher;
		this.offlineTimeoutSeconds = offlineTimeoutSeconds;
	}

	/** MQTT 하트비트 수신 처리. */
	@Transactional
	public void heartbeat(long cartId, Instant measuredAt) {
		Cart cart = cartRepository.findById(cartId)
			.orElseThrow(() -> new ResourceNotFoundException("카트", cartId));
		markAlive(cart, LocalDateTime.ofInstant(measuredAt, DATABASE_ZONE));
	}

	/**
	 * 생존 신호 반영: ONLINE 갱신 + OFFLINE→ONLINE 전환 시에만 이벤트 발행.
	 * 하트비트 외에 위치 텔레메트리 수신 경로에서도 호출된다 (호출측 트랜잭션 안에서).
	 */
	public void markAlive(Cart cart, LocalDateTime communicationAt) {
		boolean wasOffline =
			cart.getConnectionStatus() != CartConnectionStatus.ONLINE;
		cart.updateStatus(
			CartConnectionStatus.ONLINE,
			cart.getOperationStatus(),
			communicationAt
		);
		if (wasOffline) {
			publishConnection(cart, true);
			log.info("카트 ONLINE 전환 cartId={}", cart.getId());
		}
	}

	/** 워치독: 타임아웃 동안 신호가 없는 ONLINE 카트를 OFFLINE으로 전환. */
	@Scheduled(fixedDelayString = "${cart.connection.watchdog-interval-ms:5000}")
	@Transactional
	public void markStaleCartsOffline() {
		LocalDateTime threshold = LocalDateTime.now(DATABASE_ZONE)
			.minusSeconds(offlineTimeoutSeconds);
		for (Cart cart : cartRepository.findAllByConnectionStatus(CartConnectionStatus.ONLINE)) {
			LocalDateTime lastSeen = cart.getLastCommunicationAt();
			if (lastSeen != null && !lastSeen.isBefore(threshold)) {
				continue;
			}
			cart.updateStatus(
				CartConnectionStatus.OFFLINE,
				cart.getOperationStatus(),
				lastSeen
			);
			publishConnection(cart, false);
			log.info(
				"카트 OFFLINE 전환 cartId={}, lastSeenAt={} (timeout={}s)",
				cart.getId(),
				lastSeen,
				offlineTimeoutSeconds
			);
		}
	}

	private void publishConnection(Cart cart, boolean online) {
		eventPublisher.publish(
			cart.getId(),
			CONNECTION_EVENT_TYPE,
			new ConnectionEventPayload(online, cart.getLastCommunicationAt())
		);
	}

	// WS-FE-03 CART_CONNECTION_UPDATED 페이로드
	private record ConnectionEventPayload(boolean online, LocalDateTime lastSeenAt) {
	}
}
