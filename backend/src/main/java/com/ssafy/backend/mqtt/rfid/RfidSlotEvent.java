package com.ssafy.backend.mqtt.rfid;

import java.time.Instant;

/**
 * MQTT status/slot 토픽에서 수신한 슬롯 RFID 이벤트.
 * 페이로드에 cartId가 없어(단일 카트 가정) mqtt.rfid-cart-id 설정값으로 채운다.
 */
public record RfidSlotEvent(
	long cartId,
	int slotNumber,
	String uid,
	Type type,
	Instant measuredAt
) {

	public enum Type {
		DETECTED,
		REMOVED
	}
}
