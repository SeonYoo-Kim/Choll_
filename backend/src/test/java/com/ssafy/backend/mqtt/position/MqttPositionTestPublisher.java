package com.ssafy.backend.mqtt.position;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.eclipse.paho.client.mqttv3.MqttClient;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.eclipse.paho.client.mqttv3.MqttMessage;
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence;

public final class MqttPositionTestPublisher {

	private static final List<Point> TEST_POINTS = List.of(
		new Point(new BigDecimal("100.000000"), new BigDecimal("100.000000")),
		new Point(new BigDecimal("120.000000"), new BigDecimal("110.000000")),
		new Point(new BigDecimal("140.000000"), new BigDecimal("120.000000")),
		new Point(new BigDecimal("160.000000"), new BigDecimal("130.000000")),
		new Point(new BigDecimal("180.000000"), new BigDecimal("140.000000"))
	);

	private MqttPositionTestPublisher() {
	}

	public static void main(String[] args) throws Exception {
		String brokerUrl = value("MQTT_BROKER_URL", "tcp://localhost:1883");
		// 토픽에 cartId가 없다 — 수신 측(BE)의 mqtt.cart-id가 귀속 카트를 정한다
		String topic = value("MQTT_POSITION_TOPIC", "status/position");
		MqttClient client = new MqttClient(
			brokerUrl,
			"chollae-position-test-" + UUID.randomUUID(),
			new MemoryPersistence()
		);
		MqttConnectOptions options = new MqttConnectOptions();
		options.setCleanSession(true);

		try {
			client.connect(options);
			for (Point point : TEST_POINTS) {
				String payload = """
					{"x":%s,"y":%s,"timestamp":"%s"}
					""".formatted(point.x(), point.y(), Instant.now()).trim();
				MqttMessage message = new MqttMessage(
					payload.getBytes(StandardCharsets.UTF_8)
				);
				message.setQos(0);
				message.setRetained(false);
				client.publish(topic, message);
				System.out.printf("published topic=%s payload=%s%n", topic, payload);
				Thread.sleep(500);
			}
		} finally {
			if (client.isConnected()) {
				client.disconnect();
			}
			client.close();
		}
	}

	private static String value(String name, String defaultValue) {
		String property = System.getProperty(name);
		if (property != null && !property.isBlank()) {
			return property;
		}
		String environment = System.getenv(name);
		return environment == null || environment.isBlank() ? defaultValue : environment;
	}

	private record Point(BigDecimal x, BigDecimal y) {
	}

}
