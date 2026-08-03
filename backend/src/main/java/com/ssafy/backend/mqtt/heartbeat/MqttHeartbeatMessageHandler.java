package com.ssafy.backend.mqtt.heartbeat;

import java.time.Instant;
import java.time.OffsetDateTime;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

/**
 * status/cart 하트비트 메시지를 파싱해 연결 상태 갱신으로 넘긴다.
 * 토픽에 cartId가 없어(단일 카트 가정) mqtt.cart-id 설정값으로 귀속한다.
 * EM 페이로드 명세가 미확정이라 timestamp 외 필드는 무시하고,
 * 파싱 불가 페이로드도 생존 신호(수신 시각 기준)로 취급한다.
 */
@Component
public class MqttHeartbeatMessageHandler {

	private static final Logger log =
		LoggerFactory.getLogger(MqttHeartbeatMessageHandler.class);

	private final ObjectMapper objectMapper;
	private final CartConnectionService cartConnectionService;
	private final long cartId;

	public MqttHeartbeatMessageHandler(
		ObjectMapper objectMapper,
		CartConnectionService cartConnectionService,
		@Value("${mqtt.cart-id:1}") long cartId
	) {
		this.objectMapper = objectMapper;
		this.cartConnectionService = cartConnectionService;
		this.cartId = cartId;
	}

	public void handle(Message<?> message) {
		log.info(
			"[MQTT RECEIVE] topic={}, payload={}",
			message.getHeaders().get(MqttHeaders.RECEIVED_TOPIC, String.class),
			message.getPayload()
		);
		cartConnectionService.heartbeat(
			cartId,
			parseMeasuredAt(String.valueOf(message.getPayload()))
		);
	}

	private Instant parseMeasuredAt(String payload) {
		try {
			HeartbeatPayload parsed = objectMapper.readValue(payload, HeartbeatPayload.class);
			if (parsed.timestamp() != null) {
				return parsed.timestamp().toInstant();
			}
		} catch (JacksonException exception) {
			log.debug("하트비트 페이로드 파싱 불가 — 수신 시각으로 대체. payload={}", payload);
		}
		return Instant.now();
	}

	private record HeartbeatPayload(OffsetDateTime timestamp) {
	}
}
