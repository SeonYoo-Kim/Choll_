package com.ssafy.backend.mqtt.tracks;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import com.ssafy.backend.websocket.CartEventPublisher;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import tools.jackson.databind.ObjectMapper;

@ExtendWith(MockitoExtension.class)
class MqttTracksMessageHandlerTest {

	@Mock
	private CartEventPublisher eventPublisher;

	private MqttTracksMessageHandler handler;

	@BeforeEach
	void setUp() {
		handler = new MqttTracksMessageHandler(new ObjectMapper(), eventPublisher, 1L);
	}

	private Message<String> message(String payload) {
		return MessageBuilder.withPayload(payload)
			.setHeader(MqttHeaders.RECEIVED_TOPIC, "choll/cart/tracks")
			.build();
	}

	@Test
	@DisplayName("정상 tracks 페이로드는 TRACKS_UPDATED 이벤트로 중계된다")
	void relaysValidTracks() {
		handler.handle(message(
			"{\"image_width\":640,\"image_height\":480,"
				+ "\"tracks\":[{\"id\":3,\"x\":120,\"y\":40,\"w\":180,\"h\":360}]}"
		));

		verify(eventPublisher).publish(eq(1L), eq("TRACKS_UPDATED"), any());
	}

	@Test
	@DisplayName("tracks가 빈 배열이어도 중계된다 (검출 없음 상태 표현)")
	void relaysEmptyTracks() {
		handler.handle(message("{\"image_width\":640,\"image_height\":480,\"tracks\":[]}"));

		verify(eventPublisher).publish(eq(1L), eq("TRACKS_UPDATED"), any());
	}

	@Test
	@DisplayName("tracks 배열이 없으면 무시한다")
	void ignoresMissingTracks() {
		handler.handle(message("{\"image_width\":640}"));

		verify(eventPublisher, never()).publish(anyLong(), anyString(), any());
	}

	@Test
	@DisplayName("JSON이 아니면 무시한다")
	void ignoresMalformedJson() {
		handler.handle(message("not-json"));

		verify(eventPublisher, never()).publish(anyLong(), anyString(), any());
	}
}
