package com.ssafy.backend.mqtt.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "mqtt")
public class MqttProperties {

	private boolean enabled;
	private String brokerUrl = "tcp://localhost:1883";
	// 브로커 인증 계정 — 비어 있으면 익명 접속 (로컬 개발용)
	private String username = "";
	private String password = "";
	private String clientId = "chollae-backend";
	private String positionTopic = "status/position";
	private String statusTopic = "status/cart";
	private String rfidTopic = "status/slot";
	// AI(Jetson)가 발행하는 추적 후보 목록 — FE 타겟 선택 UI용 (TRACKS_UPDATED로 중계)
	private String tracksTopic = "status/target";
	// BE→EM 명령 토픽 — ⚠️ EM 미확정 임시값. 확정 시 EM·API 명세서와 동시 갱신할 것
	private String commandTopic = "cmd/move/cart";
	// 수신 토픽에 cartId가 없어(EM 계약, 단일 카트 가정) 설정으로 대상 카트를 지정한다
	private long cartId = 1L;
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

	public String getUsername() {
		return username;
	}

	public void setUsername(String username) {
		this.username = username;
	}

	public String getPassword() {
		return password;
	}

	public void setPassword(String password) {
		this.password = password;
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

	public String getStatusTopic() {
		return statusTopic;
	}

	public void setStatusTopic(String statusTopic) {
		this.statusTopic = statusTopic;
	}

	public String getRfidTopic() {
		return rfidTopic;
	}

	public void setRfidTopic(String rfidTopic) {
		this.rfidTopic = rfidTopic;
	}

	public String getTracksTopic() {
		return tracksTopic;
	}

	public void setTracksTopic(String tracksTopic) {
		this.tracksTopic = tracksTopic;
	}

	public String getCommandTopic() {
		return commandTopic;
	}

	public void setCommandTopic(String commandTopic) {
		this.commandTopic = commandTopic;
	}

	public long getCartId() {
		return cartId;
	}

	public void setCartId(long cartId) {
		this.cartId = cartId;
	}

	public int getQos() {
		return qos;
	}

	public void setQos(int qos) {
		this.qos = qos;
	}
}
