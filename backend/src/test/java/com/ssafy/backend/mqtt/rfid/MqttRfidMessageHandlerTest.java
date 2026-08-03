package com.ssafy.backend.mqtt.rfid;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.support.MessageBuilder;
import tools.jackson.databind.ObjectMapper;

@ExtendWith(MockitoExtension.class)
class MqttRfidMessageHandlerTest {

	private static final String TOPIC = "status/slot";

	@Mock
	private SlotRfidEventService slotRfidEventService;

	private MqttRfidMessageHandler handler() {
		return new MqttRfidMessageHandler(new ObjectMapper(), slotRfidEventService, 1L);
	}

	@Test
	void convertsADetectedMessageIntoASlotEvent() {
		handler().handle(MessageBuilder
			.withPayload(
				"{\"slot_id\": 1, \"uid\": \"0437F306\", \"event\": \"DETECTED\","
					+ " \"timestamp\": \"2026-07-29T13:32:27.680+09:00\"}"
			)
			.setHeader(MqttHeaders.RECEIVED_TOPIC, TOPIC)
			.build());

		ArgumentCaptor<RfidSlotEvent> captor =
			ArgumentCaptor.forClass(RfidSlotEvent.class);
		verify(slotRfidEventService).accept(captor.capture());
		RfidSlotEvent event = captor.getValue();
		assertThat(event.cartId()).isEqualTo(1L);
		assertThat(event.slotNumber()).isEqualTo(1);
		assertThat(event.uid()).isEqualTo("0437F306");
		assertThat(event.type()).isEqualTo(RfidSlotEvent.Type.DETECTED);
		assertThat(event.measuredAt())
			.isEqualTo(Instant.parse("2026-07-29T04:32:27.680Z"));
	}

	@Test
	void convertsARemovedMessageIntoASlotEvent() {
		handler().handle(MessageBuilder
			.withPayload(
				"{\"slot_id\": 3, \"uid\": \"3E40F306\", \"event\": \"REMOVED\","
					+ " \"timestamp\": \"2026-07-29T13:32:30.128+09:00\"}"
			)
			.setHeader(MqttHeaders.RECEIVED_TOPIC, TOPIC)
			.build());

		ArgumentCaptor<RfidSlotEvent> captor =
			ArgumentCaptor.forClass(RfidSlotEvent.class);
		verify(slotRfidEventService).accept(captor.capture());
		assertThat(captor.getValue().slotNumber()).isEqualTo(3);
		assertThat(captor.getValue().type()).isEqualTo(RfidSlotEvent.Type.REMOVED);
	}

	@Test
	void ignoresPayloadsWithoutSlotIdOrUid() {
		handler().handle(MessageBuilder
			.withPayload("{\"uid\": \"0437F306\", \"event\": \"DETECTED\"}")
			.setHeader(MqttHeaders.RECEIVED_TOPIC, TOPIC)
			.build());
		handler().handle(MessageBuilder
			.withPayload("{\"slot_id\": 1, \"event\": \"DETECTED\"}")
			.setHeader(MqttHeaders.RECEIVED_TOPIC, TOPIC)
			.build());

		verifyNoInteractions(slotRfidEventService);
	}

	@Test
	void ignoresUnknownEventTypesAndMalformedJson() {
		handler().handle(MessageBuilder
			.withPayload("{\"slot_id\": 1, \"uid\": \"0437F306\", \"event\": \"TAGGED\"}")
			.setHeader(MqttHeaders.RECEIVED_TOPIC, TOPIC)
			.build());
		handler().handle(MessageBuilder
			.withPayload("not-a-json")
			.setHeader(MqttHeaders.RECEIVED_TOPIC, TOPIC)
			.build());

		verifyNoInteractions(slotRfidEventService);
	}
}
