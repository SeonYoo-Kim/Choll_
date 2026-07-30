package com.ssafy.backend.mqtt.command;

import com.ssafy.backend.mqtt.config.MqttProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

/**
 * BE→EM 명령 MQTT 발행기.
 * ⚠️ 토픽(choll/cart/cmd)·페이로드는 EM 미확정 임시 계약 — 확정 시 동시 갱신할 것.
 * mqtt.enabled=false면 빈이 생성되지 않으며, 호출측은 ObjectProvider로 부재를 허용한다.
 */
@Component
@ConditionalOnProperty(prefix = "mqtt", name = "enabled", havingValue = "true")
public class MqttCommandPublisher {

	private static final Logger log = LoggerFactory.getLogger(MqttCommandPublisher.class);

	private final MessageChannel mqttOutboundChannel;
	private final ObjectMapper objectMapper;
	private final MqttProperties properties;

	public MqttCommandPublisher(
		@Qualifier("mqttOutboundChannel") MessageChannel mqttOutboundChannel,
		ObjectMapper objectMapper,
		MqttProperties properties
	) {
		this.mqttOutboundChannel = mqttOutboundChannel;
		this.objectMapper = objectMapper;
		this.properties = properties;
	}

	public void publish(Object payload) {
		String json = objectMapper.writeValueAsString(payload);
		mqttOutboundChannel.send(MessageBuilder
			.withPayload(json)
			.setHeader(MqttHeaders.TOPIC, properties.getCommandTopic())
			.build());
		log.info(
			"[MQTT PUBLISH] topic={}, payload={}",
			properties.getCommandTopic(),
			json
		);
	}
}
