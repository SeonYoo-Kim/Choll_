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

	private static final String TOPIC = "status/position";
	private static final long CART_ID = 7L;

	@Mock
	private CartPositionTelemetryService telemetryService;

	private MqttPositionMessageHandler handler() {
		return new MqttPositionMessageHandler(
			new ObjectMapper(),
			telemetryService,
			TOPIC,
			CART_ID
		);
	}

	@Test
	void convertsAValidPositionMessageIntoATelemetrySample() {
		// EM 실기 페이로드 형식 (2026-08-09 브로커 실측) — yaw 포함
		handler().handle(MessageBuilder
			.withPayload("{\"x\":100.5,\"y\":200.25,\"yaw\":0.0591,"
				+ "\"timestamp\":\"2026-08-08T18:14:39.719Z\"}")
			.setHeader(MqttHeaders.RECEIVED_TOPIC, TOPIC)
			.build());

		ArgumentCaptor<PositionSample> captor =
			ArgumentCaptor.forClass(PositionSample.class);
		verify(telemetryService).accept(captor.capture());
		PositionSample sample = captor.getValue();
		assertThat(sample.cartId()).isEqualTo(CART_ID);
		assertThat(sample.x()).isEqualByComparingTo("100.5");
		assertThat(sample.y()).isEqualByComparingTo("200.25");
		assertThat(sample.yaw()).isEqualByComparingTo("0.0591");
		assertThat(sample.measuredAt()).isNotNull();
	}

	@Test
	void acceptsLegacyPayloadWithoutYaw() {
		handler().handle(MessageBuilder
			.withPayload("{\"x\":100.5,\"y\":200.25}")
			.setHeader(MqttHeaders.RECEIVED_TOPIC, TOPIC)
			.build());

		ArgumentCaptor<PositionSample> captor =
			ArgumentCaptor.forClass(PositionSample.class);
		verify(telemetryService).accept(captor.capture());
		assertThat(captor.getValue().yaw()).isNull();
	}

	@Test
	void ignoresUnsupportedTopics() {
		handler().handle(MessageBuilder
			.withPayload("{\"x\":100,\"y\":200}")
			.setHeader(MqttHeaders.RECEIVED_TOPIC, "status/cart")
			.build());

		verifyNoInteractions(telemetryService);
	}

	@Test
	void ignoresPayloadsWithoutRequiredCoordinates() {
		handler().handle(MessageBuilder
			.withPayload("{\"x\":100}")
			.setHeader(MqttHeaders.RECEIVED_TOPIC, TOPIC)
			.build());

		verify(telemetryService, never()).accept(
			org.mockito.ArgumentMatchers.any()
		);
	}
}
