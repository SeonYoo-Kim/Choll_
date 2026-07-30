package com.ssafy.backend.mqtt.heartbeat;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

/**
 * carts/{cartId}/status 하트비트 메시지를 파싱해 연결 상태 갱신으로 넘긴다.
 * EM 페이로드 명세가 미확정이라 timestamp 외 필드는 무시하고,
 * 파싱 불가 페이로드도 생존 신호(수신 시각 기준)로 취급한다.
 */
@Component
public class MqttHeartbeatMessageHandler {

	private static final Logger log =
		LoggerFactory.getLogger(MqttHeartbeatMessageHandler.class);
	private static final Pattern STATUS_TOPIC =
		Pattern.compile("^carts/(\\d+)/status$");

	private final ObjectMapper objectMapper;
	private final CartConnectionService cartConnectionService;

	public MqttHeartbeatMessageHandler(
		ObjectMapper objectMapper,
		CartConnectionService cartConnectionService
	) {
		this.objectMapper = objectMapper;
		this.cartConnectionService = cartConnectionService;
	}

	public void handle(Message<?> message) {
		String topic = message.getHeaders().get(MqttHeaders.RECEIVED_TOPIC, String.class);
		log.info(
			"[MQTT RECEIVE] topic={}, payload={}",
			topic,
			message.getPayload()
		);
		Matcher matcher = STATUS_TOPIC.matcher(topic == null ? "" : topic);
		if (!matcher.matches()) {
			log.warn("지원하지 않는 MQTT 하트비트 토픽입니다. topic={}", topic);
			return;
		}

		cartConnectionService.heartbeat(
			Long.parseLong(matcher.group(1)),
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
