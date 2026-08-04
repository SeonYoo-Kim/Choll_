package com.ssafy.backend.follow.service;

import com.ssafy.backend.cart.domain.Cart;
import com.ssafy.backend.cart.domain.CartConnectionStatus;
import com.ssafy.backend.cart.domain.CartOperationStatus;
import com.ssafy.backend.cart.repository.CartRepository;
import com.ssafy.backend.common.exception.InvalidDomainException;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import com.ssafy.backend.mqtt.command.MqttCommandPublisher;
import com.ssafy.backend.websocket.CartEventPublisher;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 사서 추종 제어(FOLLOW-01/02/04): FE REST 요청을 MQTT 추종 명령으로 변환하고
 * FOLLOW_STATUS_UPDATED WebSocket 이벤트로 상태를 FE에 전달한다.
 * 추종 상태는 인메모리(카트당 1건) — 카트의 상행 결과 토픽이 확정되면
 * 대상 인식 여부·거리·대상 상실 전환을 붙일 자리다.
 * 일시정지 중에는 카트 동작 상태를 FOLLOWING으로 유지한다(추종 세션은 살아있음).
 */
@Service
public class FollowControlService {

	private static final Logger log = LoggerFactory.getLogger(FollowControlService.class);
	private static final String FOLLOW_EVENT_TYPE = "FOLLOW_STATUS_UPDATED";

	private final CartRepository cartRepository;
	private final CartEventPublisher eventPublisher;
	private final ObjectProvider<MqttCommandPublisher> commandPublisher;

	private final ConcurrentHashMap<Long, ActiveFollow> activeByCartId =
		new ConcurrentHashMap<>();
	private final AtomicLong followSequence = new AtomicLong();

	public FollowControlService(
		CartRepository cartRepository,
		CartEventPublisher eventPublisher,
		ObjectProvider<MqttCommandPublisher> commandPublisher
	) {
		this.cartRepository = cartRepository;
		this.eventPublisher = eventPublisher;
		this.commandPublisher = commandPublisher;
	}

	@Transactional
	public Response start(Long cartId) {
		Cart cart = cartRepository.findById(cartId)
			.orElseThrow(() -> new ResourceNotFoundException("카트", cartId));
		if (cart.getConnectionStatus() != CartConnectionStatus.ONLINE) {
			throw new InvalidDomainException("카트가 오프라인 상태라 추종을 시작할 수 없습니다.");
		}
		if (cart.getOperationStatus() == CartOperationStatus.NAVIGATING) {
			throw new InvalidDomainException(
				"목적지 이동 중에는 추종을 시작할 수 없습니다. 이동 취소 후 다시 시도하세요.");
		}
		ActiveFollow active = activeByCartId.get(cartId);
		if (active != null && !active.paused()) {
			throw new InvalidDomainException("이미 추종 중입니다.");
		}

		// 일시정지 중 재시작이면 같은 followId로 재개한다
		long followId = active != null ? active.followId() : followSequence.incrementAndGet();
		activeByCartId.put(cartId, new ActiveFollow(followId, false));
		cart.updateStatus(
			cart.getConnectionStatus(),
			CartOperationStatus.FOLLOWING,
			cart.getLastCommunicationAt()
		);

		publishCommand(new FollowCommand(followId, "FOLLOW_START"));
		publishFollowEvent(cartId, followId, "FOLLOWING", null);
		log.info("추종 시작 명령 접수 cartId={}, followId={}", cartId, followId);
		return new Response(followId, "FOLLOWING");
	}

	@Transactional
	public Response pause(Long cartId) {
		cartRepository.findById(cartId)
			.orElseThrow(() -> new ResourceNotFoundException("카트", cartId));
		ActiveFollow active = activeByCartId.get(cartId);
		if (active == null) {
			throw new InvalidDomainException("진행 중인 추종이 없어 일시정지할 수 없습니다.");
		}
		if (active.paused()) {
			log.info("이미 일시정지된 추종입니다. cartId={}, followId={} (무시)", cartId, active.followId());
			return new Response(active.followId(), "PAUSED");
		}

		activeByCartId.put(cartId, new ActiveFollow(active.followId(), true));
		publishCommand(new FollowCommand(active.followId(), "FOLLOW_PAUSE"));
		publishFollowEvent(cartId, active.followId(), "PAUSED", null);
		log.info("추종 일시정지 cartId={}, followId={}", cartId, active.followId());
		return new Response(active.followId(), "PAUSED");
	}

	@Transactional
	public void stop(Long cartId) {
		Cart cart = cartRepository.findById(cartId)
			.orElseThrow(() -> new ResourceNotFoundException("카트", cartId));
		ActiveFollow active = activeByCartId.remove(cartId);
		if (active == null) {
			// 세션은 인메모리라 재시작하면 사라지는데 DB 상태만 FOLLOWING으로
			// 남을 수 있다 — 종료 요청이 오면 그 고아 상태도 청소한다
			if (cart.getOperationStatus() == CartOperationStatus.FOLLOWING) {
				cart.updateStatus(
					cart.getConnectionStatus(),
					CartOperationStatus.IDLE,
					cart.getLastCommunicationAt()
				);
				log.info("세션 없는 FOLLOWING 상태 정리 (재시작 잔재) cartId={}", cartId);
				return;
			}
			log.info("종료할 진행 중 추종이 없습니다. cartId={} (무시)", cartId);
			return;
		}
		cart.updateStatus(
			cart.getConnectionStatus(),
			CartOperationStatus.IDLE,
			cart.getLastCommunicationAt()
		);
		publishCommand(new FollowCommand(active.followId(), "FOLLOW_STOP"));
		publishFollowEvent(cartId, active.followId(), "STOPPED", null);
		log.info("추종 종료 cartId={}, followId={}", cartId, active.followId());
	}

	private void publishCommand(FollowCommand command) {
		MqttCommandPublisher publisher = commandPublisher.getIfAvailable();
		if (publisher == null) {
			log.warn("MQTT 비활성 — 명령을 발행하지 못했습니다. command={}", command);
			return;
		}
		publisher.publish(command);
	}

	private void publishFollowEvent(Long cartId, long followId, String status, String failReason) {
		eventPublisher.publish(cartId, FOLLOW_EVENT_TYPE, new FollowEventPayload(
			followId,
			status,
			failReason
		));
	}

	private record ActiveFollow(long followId, boolean paused) {
	}

	// BE→EM 추종 명령 페이로드 — ⚠️ EM 미확정 임시 계약 (cmd/move/cart)
	private record FollowCommand(
		long requestId,
		String command
	) {
	}

	// WS-FE-07 FOLLOW_STATUS_UPDATED 페이로드 — 대상 인식 여부·거리는 카트 상행 확정 후 추가
	private record FollowEventPayload(
		long followId,
		String status,
		String failReason
	) {
	}

	@Schema(name = "FollowCommandResult")
	public record Response(
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED)
		long followId,
		@Schema(requiredMode = Schema.RequiredMode.REQUIRED, example = "FOLLOWING")
		String status
	) {
	}
}
