package com.ssafy.backend.mqtt.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "mqtt")
public class MqttProperties {

	private boolean enabled;
	private String brokerUrl = "tcp://localhost:1883";
	private String clientId = "chollae-backend";
	private String positionTopic = "carts/+/telemetry/position";
	private String rfidTopic = "choll/cart/rfid";
	// RFID 페이로드에 cartId가 없어(EM 계약, 단일 카트 가정) 설정으로 대상 카트를 지정한다
	private long rfidCartId = 1L;
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

	public String getRfidTopic() {
		return rfidTopic;
	}

	public void setRfidTopic(String rfidTopic) {
		this.rfidTopic = rfidTopic;
	}

	public long getRfidCartId() {
		return rfidCartId;
	}

	public void setRfidCartId(long rfidCartId) {
		this.rfidCartId = rfidCartId;
	}

	public int getQos() {
		return qos;
	}

	public void setQos(int qos) {
		this.qos = qos;
	}
}
