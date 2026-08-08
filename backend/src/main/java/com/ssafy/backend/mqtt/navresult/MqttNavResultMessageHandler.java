package com.ssafy.backend.mqtt.navresult;

import com.ssafy.backend.navigation.service.NavigationService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * status/nav-result 토픽의 주행 결과를 파싱해 이동 세션에 반영한다.
 *
 * 발행원은 EM SLAM Nav — 원래 ROS2 토픽(/cart/nav_status, ROS2-16)의 7종 상태를
 * MQTT로 중계한다(2026-08-07 합의). 페이로드는 {"status":"SUCCEEDED", ...} JSON을
 * 기본으로 하되, ROS2 브리지가 std_msgs/String을 평문으로 흘릴 가능성이 있어
 * 따옴표 없는 순수 문자열("SUCCEEDED")도 받는다.
 *
 * 토픽에 cartId가 없어(단일 카트 가정) mqtt.cart-id 설정값으로 귀속한다 —
 * 다른 수신 핸들러 3종과 같은 제약이며 다중 카트 도입 시 함께 재협의한다.
 */
@Component
public class MqttNavResultMessageHandler {

	private static final Logger log =
		LoggerFactory.getLogger(MqttNavResultMessageHandler.class);

	private final ObjectMapper objectMapper;
	private final NavigationService navigationService;
	private final long cartId;

	public MqttNavResultMessageHandler(
		ObjectMapper objectMapper,
		NavigationService navigationService,
		@Value("${mqtt.cart-id:1}") long cartId
	) {
		this.objectMapper = objectMapper;
		this.navigationService = navigationService;
		this.cartId = cartId;
	}

	public void handle(Message<?> message) {
		String payload = String.valueOf(message.getPayload());
		log.info("[MQTT RECEIVE] topic=status/nav-result, payload={}", payload);
		String status = parseStatus(payload);
		if (status == null || status.isBlank()) {
			log.warn("주행 결과에서 상태를 읽지 못했습니다. payload={}", payload);
			return;
		}
		navigationService.applyCartNavResult(cartId, status.trim().toUpperCase());
	}

	/** JSON {"status": "..."} 우선, 아니면 페이로드 전체를 상태 문자열로 본다. */
	private String parseStatus(String payload) {
		try {
			JsonNode node = objectMapper.readTree(payload);
			if (node.isObject()) {
				JsonNode status = node.get("status");
				return status == null ? null : status.asString();
			}
			if (node.isString()) {
				return node.asString();
			}
		} catch (JacksonException exception) {
			// JSON이 아니면 평문 상태 문자열로 취급
		}
		return payload;
	}
}
