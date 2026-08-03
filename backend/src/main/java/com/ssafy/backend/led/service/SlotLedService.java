package com.ssafy.backend.led.service;

import com.ssafy.backend.mqtt.command.MqttCommandPublisher;
import com.ssafy.backend.slot.service.SlotService;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 카트의 구역이 바뀔 때마다 그 구역에서 내려놓을 슬롯 목록을 라즈베리파이에 발행한다.
 *
 * <p>페이로드의 {@code slot_id}는 <b>그 시점에 켜져 있어야 할 슬롯 전체</b>다 —
 * 빈 목록은 전부 소등하라는 뜻이다. 구역을 벗어날 때 책이 남아 있어도 LED가 켜진 채로
 * 남지 않도록, 직전에 구역 안에 있었다면 대상이 없어도 빈 목록을 보낸다.
 *
 * <p>켜고 끄는 실제 제어는 라즈베리파이 몫이다(BE 범위 밖). 슬롯에서 책이 빠졌을 때의
 * 소등도 라즈베리파이가 RFID REMOVED를 보고 자체 처리하므로 BE는 재발행하지 않는다.
 */
@Service
@Transactional(readOnly = true)
public class SlotLedService {

	private static final Logger log = LoggerFactory.getLogger(SlotLedService.class);

	private final SlotService slotService;
	private final ObjectProvider<MqttCommandPublisher> commandPublisher;

	public SlotLedService(
		SlotService slotService,
		ObjectProvider<MqttCommandPublisher> commandPublisher
	) {
		this.slotService = slotService;
		this.commandPublisher = commandPublisher;
	}

	/**
	 * 구역이 바뀐 직후 점등 대상을 발행한다.
	 *
	 * @param cartId       구역이 바뀐 카트 (호출 전에 카트의 현재 구역이 갱신돼 있어야 한다)
	 * @param leftLitZone  직전에 구역 안에 있었는지 — true면 대상이 없어도 빈 목록을 보내 소등시킨다.
	 *                     false(구역 밖 → 대상 없는 구역)면 켤 것도 끌 것도 없으므로 발행하지 않는다.
	 */
	public void syncZoneLighting(Long cartId, boolean leftLitZone) {
		List<Integer> slot_id = slotService.findTargetSlotNumbers(cartId);
		if (slot_id.isEmpty() && !leftLitZone) {
			log.info("LED 점등 대상 없음, 직전 구역도 없음 — 발행 생략 cartId={}", cartId);
			return;
		}

		MqttCommandPublisher publisher = commandPublisher.getIfAvailable();
		if (publisher == null) {
			log.warn("MQTT 비활성 — LED 점등을 요청하지 못했습니다. slot_id={}", slot_id);
			return;
		}
		publisher.publishLed(new LedCommand(slot_id));
		log.info(
			"LED 점등 발행 cartId={}, slot_id={}{}",
			cartId,
			slot_id,
			slot_id.isEmpty() ? " (구역 이탈 — 전체 소등)" : ""
		);
	}

	/** LED 점등 페이로드 — 카트가 하나라 cartId는 싣지 않는다. 빈 목록 = 전체 소등. */
	record LedCommand(List<Integer> slot_id) {
	}
}
