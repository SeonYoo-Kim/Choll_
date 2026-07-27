package com.ssafy.backend.mqtt.position;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

@Component
public class MqttPositionMessageHandler {

	private static final Logger log =
		LoggerFactory.getLogger(MqttPositionMessageHandler.class);
	private static final Pattern POSITION_TOPIC =
		Pattern.compile("^carts/(\\d+)/telemetry/position$");

	private final ObjectMapper objectMapper;
	private final CartPositionTelemetryService telemetryService;

	public MqttPositionMessageHandler(
		ObjectMapper objectMapper,
		CartPositionTelemetryService telemetryService
	) {
		this.objectMapper = objectMapper;
		this.telemetryService = telemetryService;
	}

	public void handle(Message<?> message) {
		String topic = message.getHeaders().get(MqttHeaders.RECEIVED_TOPIC, String.class);
		log.info(
			"[MQTT RECEIVE] topic={}, payload={}",
			topic,
			message.getPayload()
		);
		Matcher matcher = POSITION_TOPIC.matcher(topic == null ? "" : topic);
		if (!matcher.matches()) {
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
				Long.parseLong(matcher.group(1)),
				payload.x(),
				payload.y(),
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

	private record PositionPayload(
		BigDecimal x,
		BigDecimal y,
		Instant timestamp
	) {
	}
}
