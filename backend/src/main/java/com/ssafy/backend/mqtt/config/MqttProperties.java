package com.ssafy.backend.mqtt.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "mqtt")
public class MqttProperties {

	private boolean enabled;
	private String brokerUrl = "tcp://localhost:1883";
	private String clientId = "chollae-backend";
	private String positionTopic = "carts/+/telemetry/position";
	private int qos;

	public boolean isEnabled() {
		return enabled;
	}

	public void setEnabled(boolean enabled) {
		this.enabled = enabled;
	}

	public String getBrokerUrl() {
		return brokerUrl;
	}

	public void setBrokerUrl(String brokerUrl) {
		this.brokerUrl = brokerUrl;
	}

	public String getClientId() {
		return clientId;
	}

	public void setClientId(String clientId) {
		this.clientId = clientId;
	}

	public String getPositionTopic() {
		return positionTopic;
	}

	public void setPositionTopic(String positionTopic) {
		this.positionTopic = positionTopic;
	}

	public int getQos() {
		return qos;
	}

	public void setQos(int qos) {
		this.qos = qos;
	}
}
