package com.ssafy.backend.mqtt.rfid;

import com.fasterxml.jackson.annotation.JsonProperty;
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
 * choll/cart/rfid 토픽의 RFID 태깅 메시지를 파싱해 슬롯 이벤트로 변환한다.
 * 페이로드 예: {"slot_id": 1, "uid": "0437F306", "event": "DETECTED",
 * "timestamp": "2026-07-29T13:32:27.680+09:00"}
 */
@Component
public class MqttRfidMessageHandler {

	private static final Logger log =
		LoggerFactory.getLogger(MqttRfidMessageHandler.class);

	private final ObjectMapper objectMapper;
	private final SlotRfidEventService slotRfidEventService;
	private final long rfidCartId;

	public MqttRfidMessageHandler(
		ObjectMapper objectMapper,
		SlotRfidEventService slotRfidEventService,
		@Value("${mqtt.rfid-cart-id:1}") long rfidCartId
	) {
		this.objectMapper = objectMapper;
		this.slotRfidEventService = slotRfidEventService;
		this.rfidCartId = rfidCartId;
	}

	public void handle(Message<?> message) {
		String topic = message.getHeaders().get(MqttHeaders.RECEIVED_TOPIC, String.class);
		log.info(
			"[MQTT RECEIVE] topic={}, payload={}",
			topic,
			message.getPayload()
		);

		try {
			RfidPayload payload = objectMapper.readValue(
				String.valueOf(message.getPayload()),
				RfidPayload.class
			);
			if (payload.slotId() == null || payload.uid() == null || payload.uid().isBlank()) {
				throw new IllegalArgumentException("slot_id와 uid는 필수입니다.");
			}
			if (payload.event() == null) {
				throw new IllegalArgumentException("event는 필수입니다.");
			}
			slotRfidEventService.accept(new RfidSlotEvent(
				rfidCartId,
				payload.slotId(),
				payload.uid(),
				RfidSlotEvent.Type.valueOf(payload.event()),
				payload.timestamp() == null
					? Instant.now()
					: payload.timestamp().toInstant()
			));
		} catch (JacksonException | IllegalArgumentException exception) {
			log.warn(
				"MQTT RFID 메시지를 처리할 수 없습니다. topic={}, payload={}",
				topic,
				message.getPayload(),
				exception
			);
		}
	}

	private record RfidPayload(
		@JsonProperty("slot_id") Integer slotId,
		String uid,
		String event,
		OffsetDateTime timestamp
	) {
	}
}
