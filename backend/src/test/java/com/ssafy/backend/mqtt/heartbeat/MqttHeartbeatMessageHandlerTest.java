package com.ssafy.backend.mqtt.heartbeat;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;

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

	private static final String TOPIC = "carts/status";
	private static final long CART_ID = 1L;

	@Mock
	private CartConnectionService cartConnectionService;

	private MqttHeartbeatMessageHandler handler() {
		return new MqttHeartbeatMessageHandler(
			new ObjectMapper(),
			cartConnectionService,
			CART_ID
		);
	}

	@Test
	void attributesHeartbeatToConfiguredCartWithPayloadTimestamp() {
		handler().handle(MessageBuilder
			.withPayload("{\"timestamp\": \"2026-07-30T13:00:00.000+09:00\"}")
			.setHeader(MqttHeaders.RECEIVED_TOPIC, TOPIC)
			.build());

		verify(cartConnectionService).heartbeat(
			eq(CART_ID),
			eq(Instant.parse("2026-07-30T04:00:00.000Z"))
		);
	}

	@Test
	void treatsUnparseablePayloadAsALivenessSignal() {
		Instant before = Instant.now();
		handler().handle(MessageBuilder
			.withPayload("ping")
			.setHeader(MqttHeaders.RECEIVED_TOPIC, TOPIC)
			.build());

		ArgumentCaptor<Instant> captor = ArgumentCaptor.forClass(Instant.class);
		verify(cartConnectionService).heartbeat(eq(CART_ID), captor.capture());
		assertThat(captor.getValue()).isAfterOrEqualTo(before);
	}
}
