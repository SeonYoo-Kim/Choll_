package com.ssafy.backend.mqtt.heartbeat;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
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
class MqttHeartbeatMessageHandlerTest {

	@Mock
	private CartConnectionService cartConnectionService;

	private MqttHeartbeatMessageHandler handler() {
		return new MqttHeartbeatMessageHandler(new ObjectMapper(), cartConnectionService);
	}

	@Test
	void convertsAValidHeartbeatWithTimestamp() {
		handler().handle(MessageBuilder
			.withPayload("{\"timestamp\": \"2026-07-30T13:00:00.000+09:00\"}")
			.setHeader(MqttHeaders.RECEIVED_TOPIC, "carts/7/status")
			.build());

		verify(cartConnectionService).heartbeat(
			eq(7L),
			eq(Instant.parse("2026-07-30T04:00:00.000Z"))
		);
	}

	@Test
	void treatsUnparseablePayloadAsALivenessSignal() {
		Instant before = Instant.now();
		handler().handle(MessageBuilder
			.withPayload("ping")
			.setHeader(MqttHeaders.RECEIVED_TOPIC, "carts/7/status")
			.build());

		ArgumentCaptor<Instant> captor = ArgumentCaptor.forClass(Instant.class);
		verify(cartConnectionService).heartbeat(eq(7L), captor.capture());
		assertThat(captor.getValue()).isAfterOrEqualTo(before);
	}

	@Test
	void ignoresUnsupportedTopics() {
		handler().handle(MessageBuilder
			.withPayload("{}")
			.setHeader(MqttHeaders.RECEIVED_TOPIC, "carts/abc/status")
			.build());

		verifyNoInteractions(cartConnectionService);
	}
}
