package com.ssafy.backend.follow.service;

import com.ssafy.backend.cart.repository.CartRepository;
import com.ssafy.backend.common.exception.InvalidDomainException;
import com.ssafy.backend.common.exception.ResourceNotFoundException;
import com.ssafy.backend.mqtt.command.MqttCommandPublisher;
import io.swagger.v3.oas.annotations.media.Schema;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

/**
 * FE 타겟 선택(추종 대상 지정)을 카트로 하행한다.
 * FE가 영상+TRACKS_UPDATED로 고른 track id를 MQTT SELECT_TARGET 명령으로 변환하면,
 * Jetson의 브릿지 노드가 /select_target ROS 토픽으로 넘겨 Re-ID가 등록을 시작한다.
 */
@Service
public class FollowTargetService {

	private static final Logger log = LoggerFactory.getLogger(FollowTargetService.class);

	private final CartRepository cartRepository;
	private final ObjectProvider<MqttCommandPublisher> commandPublisher;

	public FollowTargetService(
		CartRepository cartRepository,
		ObjectProvider<MqttCommandPublisher> commandPublisher
	) {
		this.cartRepository = cartRepository;
		this.commandPublisher = commandPublisher;
	}

	public Response selectTarget(Long cartId, Long trackId) {
		cartRepository.findById(cartId)
			.orElseThrow(() -> new ResourceNotFoundException("카트", cartId));

		MqttCommandPublisher publisher = commandPublisher.getIfAvailable();
		if (publisher == null) {
			throw new InvalidDomainException(
				"MQTT 발행이 비활성화되어 타겟 선택 명령을 보낼 수 없습니다.");
		}
		publisher.publish(new SelectTargetCommand("SELECT_TARGET", trackId));
		log.info("타겟 선택 명령 발행 cartId={}, trackId={}", cartId, trackId);
		return new Response(trackId, "SENT");
	}

	private record SelectTargetCommand(String command, Long trackId) {
	}

	@Schema(name = "FollowTargetResult")
	public record Response(
		@Schema(description = "선택한 추적 후보 track id") Long trackId,
		@Schema(description = "명령 상태", example = "SENT") String status
	) {
	}
}
