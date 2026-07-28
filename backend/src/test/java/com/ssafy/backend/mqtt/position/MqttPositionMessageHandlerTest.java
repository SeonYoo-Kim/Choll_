package com.ssafy.backend.mqtt.position;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.support.MessageBuilder;
import tools.jackson.databind.ObjectMapper;

@ExtendWith(MockitoExtension.class)
class MqttPositionMessageHandlerTest {

	@Mock
	private CartPositionTelemetryService telemetryService;

	@Test
	void convertsAValidPositionMessageIntoATelemetrySample() {
		MqttPositionMessageHandler handler = new MqttPositionMessageHandler(
			new ObjectMapper(),
			telemetryService
		);

		handler.handle(MessageBuilder
			.withPayload("{\"x\":100.5,\"y\":200.25}")
			.setHeader(
				MqttHeaders.RECEIVED_TOPIC,
				"carts/7/telemetry/position"
			)
			.build());

		ArgumentCaptor<PositionSample> captor =
			ArgumentCaptor.forClass(PositionSample.class);
		verify(telemetryService).accept(captor.capture());
		PositionSample sample = captor.getValue();
		assertThat(sample.cartId()).isEqualTo(7L);
		assertThat(sample.x()).isEqualByComparingTo("100.5");
		assertThat(sample.y()).isEqualByComparingTo("200.25");
		assertThat(sample.measuredAt()).isNotNull();
	}

	@Test
	void ignoresUnsupportedTopics() {
		MqttPositionMessageHandler handler = new MqttPositionMessageHandler(
			new ObjectMapper(),
			telemetryService
		);

		handler.handle(MessageBuilder
			.withPayload("{\"x\":100,\"y\":200}")
			.setHeader(MqttHeaders.RECEIVED_TOPIC, "carts/7/status")
			.build());

		verifyNoInteractions(telemetryService);
	}

	@Test
	void ignoresPayloadsWithoutRequiredCoordinates() {
		MqttPositionMessageHandler handler = new MqttPositionMessageHandler(
			new ObjectMapper(),
			telemetryService
		);

		handler.handle(MessageBuilder
			.withPayload("{\"x\":100}")
			.setHeader(
				MqttHeaders.RECEIVED_TOPIC,
				"carts/7/telemetry/position"
			)
			.build());

		verify(telemetryService, never()).accept(
			org.mockito.ArgumentMatchers.any()
		);
	}
}
