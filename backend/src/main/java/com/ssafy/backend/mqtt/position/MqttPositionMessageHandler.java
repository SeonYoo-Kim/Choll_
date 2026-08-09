package com.ssafy.backend.mqtt.position;

import java.math.BigDecimal;
import java.time.Instant;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

/**
 * status/position 토픽의 카트 위치 메시지를 파싱해 텔레메트리 샘플로 넘긴다.
 * 토픽에 cartId가 없어(단일 카트 가정) mqtt.cart-id 설정값으로 귀속한다.
 * ⚠️ 다중 카트 도입 시 토픽/페이로드에 cartId를 넣도록 EM과 재협의 필요.
 */
@Component
public class MqttPositionMessageHandler {

	private static final Logger log =
		LoggerFactory.getLogger(MqttPositionMessageHandler.class);

	private final ObjectMapper objectMapper;
	private final CartPositionTelemetryService telemetryService;
	private final String positionTopic;
	private final long cartId;

	public MqttPositionMessageHandler(
		ObjectMapper objectMapper,
		CartPositionTelemetryService telemetryService,
		@Value("${mqtt.position-topic:status/position}") String positionTopic,
		@Value("${mqtt.cart-id:1}") long cartId
	) {
		this.objectMapper = objectMapper;
		this.telemetryService = telemetryService;
		this.positionTopic = positionTopic;
		this.cartId = cartId;
	}

	public void handle(Message<?> message) {
		String topic = message.getHeaders().get(MqttHeaders.RECEIVED_TOPIC, String.class);
		log.info(
			"[MQTT RECEIVE] topic={}, payload={}",
			topic,
			message.getPayload()
		);
		if (!positionTopic.equals(topic)) {
			log.warn("지원하지 않는 MQTT 위치 토픽입니다. topic={}", topic);
			return;
		}

		try {
			PositionPayload payload = objectMapper.readValue(
				String.valueOf(message.getPayload()),
				PositionPayload.class
			);
			if (payload.x() == null || payload.y() == null) {
				throw new IllegalArgumentException("x와 y 좌표는 필수입니다.");
			}
			telemetryService.accept(new PositionSample(
				cartId,
				payload.x(),
				payload.y(),
				payload.yaw(),
				payload.timestamp() == null ? Instant.now() : payload.timestamp()
			));
		} catch (JacksonException | IllegalArgumentException exception) {
			log.warn(
				"MQTT 위치 메시지를 처리할 수 없습니다. topic={}, payload={}",
				topic,
				message.getPayload(),
				exception
			);
		}
	}

	// yaw: 라디안(CCW+), EM 2026-08-09 실기 확정 페이로드. 구버전(yaw 없음)도 계속 수용
	private record PositionPayload(
		BigDecimal x,
		BigDecimal y,
		BigDecimal yaw,
		Instant timestamp
	) {
	}
}
