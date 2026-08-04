package com.ssafy.backend.mqtt.tracks;

import com.ssafy.backend.websocket.CartEventPublisher;
import com.ssafy.backend.websocket.VideoRelayHandler;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

/**
 * status/target 토픽의 추적 후보 목록을 FE로 중계한다 (TRACKS_UPDATED).
 * AI(Jetson)가 5~10Hz로 발행하며, FE는 영상 위에 bbox를 그려 타겟 선택 UI를 만든다.
 * 영상 시청자(추종 대상 선택 모달)가 없는 동안은 중계하지 않는다 —
 * AI는 항상 발행하지만 FE가 그릴 화면이 없으면 WS 트래픽·콘솔 스팸만 되기 때문.
 * 페이로드 예:
 * {"image_width":640,"image_height":480,
 *  "tracks":[{"id":3,"x":120,"y":40,"w":180,"h":360}]}
 * (x,y = bbox 좌상단 픽셀, w/h = 픽셀 크기. BE는 구조 검증만 하고 그대로 전달)
 */
@Component
public class MqttTracksMessageHandler {

	private static final Logger log =
		LoggerFactory.getLogger(MqttTracksMessageHandler.class);
	private static final String EVENT_TYPE = "TRACKS_UPDATED";

	private final ObjectMapper objectMapper;
	private final CartEventPublisher eventPublisher;
	private final VideoRelayHandler videoRelayHandler;
	private final long cartId;

	public MqttTracksMessageHandler(
		ObjectMapper objectMapper,
		CartEventPublisher eventPublisher,
		VideoRelayHandler videoRelayHandler,
		@Value("${mqtt.cart-id:1}") long cartId
	) {
		this.objectMapper = objectMapper;
		this.eventPublisher = eventPublisher;
		this.videoRelayHandler = videoRelayHandler;
		this.cartId = cartId;
	}

	public void handle(Message<?> message) {
		if (!videoRelayHandler.hasViewers(cartId)) {
			return;
		}
		String topic = message.getHeaders().get(MqttHeaders.RECEIVED_TOPIC, String.class);
		try {
			Map<?, ?> payload = objectMapper.readValue(
				String.valueOf(message.getPayload()),
				Map.class
			);
			if (!(payload.get("tracks") instanceof java.util.List)) {
				throw new IllegalArgumentException("tracks 배열은 필수입니다.");
			}
			eventPublisher.publish(cartId, EVENT_TYPE, payload);
		} catch (JacksonException | IllegalArgumentException exception) {
			log.warn(
				"MQTT tracks 메시지를 처리할 수 없습니다. topic={}, payload={}",
				topic,
				message.getPayload(),
				exception
			);
		}
	}
}
