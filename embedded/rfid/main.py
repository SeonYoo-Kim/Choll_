#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
스마트 카트 메인 (RFID + MQTT + LED 통합 실행)

역할 분담:
- rfid_controller.py : MFRC522 스캔 + 카드 존재 상태머신 (하드웨어)
- led_controller.py  : WS281x 슬롯 LED 표시 + 깜빡임 (하드웨어)
- main.py            : 설정 + MQTT 송수신 + 두 컨트롤러 연결 (정책/배선)

MQTT:
- 발행: status/slot  카드 DETECTED/REMOVED 이벤트
        status/cart  하트비트 + online/offline (LWT)
- 구독: cmd/lit/led  {"slot_id": [1, 2]} -> 해당 슬롯 LED 빨강 깜빡임
        매 메시지가 깜빡임 대상을 통째로 교체하며,
        {"slot_id": []} 를 보내면 깜빡임이 중지되고 원래 색으로 복귀한다.
        깜빡이는 슬롯에서 카드가 제거되면(REMOVED) 그 슬롯만
        자동으로 깜빡임이 해제되고 초록으로 돌아간다.
        카드를 빼지 않는 한 깜빡임은 계속 유지된다.

평소에는 systemd 서비스(cart.service)로 자동 실행된다.
수동 실행이 필요하면 서비스와 GPIO가 충돌하므로 먼저 내릴 것:

    sudo systemctl stop cart
    ~/cart/.venv/bin/python -u main.py
"""

import json
import signal
import threading
import time
from datetime import datetime, timezone, timedelta

import paho.mqtt.client as mqtt

from led_controller import SlotLEDController
from rfid_controller import RFIDController


# ============================================================
# User Config
# ============================================================

MQTT_BROKER_HOST = "your-server.example.com"
MQTT_BROKER_PORT = 1883
MQTT_USERNAME = "choll"
MQTT_PASSWORD = "CHANGE_ME"
MQTT_CLIENT_ID = "rfid_publisher"

EVENT_TOPIC = "status/slot"      # 발행: 카드 DETECTED/REMOVED
HEARTBEAT_TOPIC = "status/cart"  # 발행: 하트비트 + online/offline
LED_CMD_TOPIC = "cmd/lit/led"    # 구독: LED 점등(깜빡임) 명령

HEARTBEAT_INTERVAL_SEC = 5.0
KST = timezone(timedelta(hours=9))

# BCM GPIO 번호 기준
# led_index: WS281x 데이지체인에서 이 슬롯 LED의 위치 (0부터 시작)
SLOT_CONFIG = [
    {"slot_id": 1, "cs_pin": 16, "led_index": 0},
    {"slot_id": 2, "cs_pin": 20, "led_index": 1},
    {"slot_id": 3, "cs_pin": 5,  "led_index": 2},
    {"slot_id": 4, "cs_pin": 6,  "led_index": 3},
    {"slot_id": 5, "cs_pin": 13, "led_index": 4},
]

SLOT_TO_LED = {cfg["slot_id"]: cfg["led_index"] for cfg in SLOT_CONFIG}


# ============================================================
# MQTT Client
# ============================================================

class CartMQTTClient:
    """
    카트 <-> 서버 MQTT 송수신 담당.
    - 발행: 슬롯 이벤트(EVENT_TOPIC), 하트비트/상태(HEARTBEAT_TOPIC, LWT 포함)
    - 구독: LED 점등 명령(LED_CMD_TOPIC)
      -> {"slot_id": [1, 2]} 파싱 후 on_led_command(slot_id 리스트) 콜백 호출
    """

    def __init__(self, on_led_command=None):
        self.on_led_command = on_led_command

        # paho-mqtt 1.x / 2.x 호환
        try:
            self.client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=MQTT_CLIENT_ID,
            )
        except Exception:
            self.client = mqtt.Client(client_id=MQTT_CLIENT_ID)

        # 브로커 인증 정보 (connect 이전에 설정해야 함)
        self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

        # LWT: 비정상 종료(전원 차단, 크래시 등) 시
        # 브로커가 대신 offline 상태를 retain으로 발행해준다.
        # 반드시 connect 전에 등록해야 함.
        self.client.will_set(
            HEARTBEAT_TOPIC,
            json.dumps({"status": "offline"}),
            qos=1,
            retain=True,
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        self._hb_stop = threading.Event()
        self._hb_thread = None

    # ---------------- connect ----------------

    def connect(self):
        # connect_async + loop_start:
        # 부팅 직후 네트워크가 아직 안 떠 있어도 예외로 죽지 않고,
        # 백그라운드 스레드가 연결될 때까지 계속 재시도한다.
        # 연결 전에 발행된 QoS1 이벤트는 큐에 쌓였다가 연결되면 전송됨.
        print(
            f"[MQTT] connecting to {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT} "
            f"(background retry enabled)"
        )
        self.client.connect_async(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=60)
        self.client.loop_start()

        self._start_heartbeat()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        # paho-mqtt 1.x / 2.x 콜백 시그니처 모두 호환.
        # 재연결 시에도 구독이 유지되도록 여기서 subscribe 한다.
        client.subscribe(LED_CMD_TOPIC, qos=1)

        # 연결/재연결 시마다 online 상태를 retain으로 발행해서
        # LWT가 남긴 offline 상태를 덮어쓴다.
        client.publish(
            HEARTBEAT_TOPIC,
            json.dumps({"status": "online"}),
            qos=1,
            retain=True,
        )
        print(
            f"[MQTT] on_connect: subscribed to {LED_CMD_TOPIC}, "
            f"published online status to {HEARTBEAT_TOPIC}"
        )

    # ---------------- subscribe (LED 점등 명령) ----------------

    def _on_message(self, client, userdata, msg):
        if msg.topic != LED_CMD_TOPIC:
            return

        # 기대 payload: {"slot_id": [1, 2]}  (단일 int도 허용)
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            slot_ids = payload.get("slot_id")

            if isinstance(slot_ids, int):
                slot_ids = [slot_ids]
            if not isinstance(slot_ids, list):
                raise ValueError(f"'slot_id' must be an int list, got {slot_ids!r}")

            slot_ids = [int(s) for s in slot_ids]

        except Exception as e:
            print(f"[MQTT] invalid LED command payload {msg.payload!r}: {e}")
            return

        print(f"[MQTT] LED command received: slot_id={slot_ids}")

        if self.on_led_command is not None:
            try:
                self.on_led_command(slot_ids)
            except Exception as e:
                print(f"[MQTT] on_led_command failed: {e}")

    # ---------------- heartbeat ----------------

    def _start_heartbeat(self):
        if self._hb_thread is not None and self._hb_thread.is_alive():
            return

        self._hb_stop.clear()
        self._hb_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="mqtt-heartbeat",
            daemon=True,
        )
        self._hb_thread.start()
        print(
            f"[MQTT] heartbeat started: topic={HEARTBEAT_TOPIC}, "
            f"interval={HEARTBEAT_INTERVAL_SEC}s"
        )

    def _heartbeat_loop(self):
        # 주기마다 하트비트 발행. 먼저 한 번 쏘고 나서 대기.
        while not self._hb_stop.is_set():
            payload = json.dumps({
                "timestamp": datetime.now(KST).isoformat(timespec="milliseconds")
            })

            try:
                self.client.publish(HEARTBEAT_TOPIC, payload)
            except Exception as e:
                print(f"[MQTT] heartbeat publish failed: {e}")

            self._hb_stop.wait(HEARTBEAT_INTERVAL_SEC)

    # ---------------- publish (슬롯 이벤트) ----------------

    def publish_event(self, slot_id, uid, event):
        payload = {
            "slot_id": int(slot_id),
            "uid": str(uid),
            "event": str(event),
            "timestamp": datetime.now(KST).isoformat(timespec="milliseconds"),
        }

        payload_str = json.dumps(payload, ensure_ascii=False)

        result = self.client.publish(
            EVENT_TOPIC,
            payload_str,
            qos=1,
            retain=False,
        )

        print(f"[MQTT] publish {event}: {payload_str}")

        return result

    # ---------------- close ----------------

    def close(self):
        # 하트비트 스레드 정지
        self._hb_stop.set()
        if self._hb_thread is not None:
            self._hb_thread.join(timeout=2.0)

        # 정상 종료 시에는 LWT가 발행되지 않으므로
        # offline 상태를 직접 retain으로 발행하고 나서 끊는다.
        try:
            info = self.client.publish(
                HEARTBEAT_TOPIC,
                json.dumps({"status": "offline"}),
                qos=1,
                retain=True,
            )
            try:
                info.wait_for_publish(timeout=2.0)
            except Exception:
                time.sleep(0.3)
        except Exception:
            pass

        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass


# ============================================================
# Wiring + Entry Point
# ============================================================

def main():
    # 1) LED: 시작 즉시 전체 초록 (부팅 시각 피드백)
    leds = SlotLEDController()
    print("[LED] initialized: all LEDs green")

    # 2) 서버 점등 명령 -> 슬롯 id를 LED 인덱스로 변환해서 깜빡임 적용
    def handle_led_command(slot_ids):
        indices = []
        for slot_id in slot_ids:
            idx = SLOT_TO_LED.get(slot_id)
            if idx is None:
                print(f"[APP] unknown slot_id in LED command: {slot_id}")
                continue
            indices.append(idx)
        leds.set_blink(indices)

    mqttc = CartMQTTClient(on_led_command=handle_led_command)

    # 3) RFID 이벤트 -> MQTT 발행 + LED 기본색 갱신
    def handle_rfid_event(slot_id, uid, event):
        mqttc.publish_event(slot_id, uid, event)

        idx = SLOT_TO_LED.get(slot_id)
        if idx is None:
            return
        if event == "DETECTED":
            # 깜빡이는 중이면 깜빡임 유지 (기본색만 빨강으로 기록됨)
            leds.set_detected(idx)
        elif event == "REMOVED":
            # 카드가 빠지면 기본색 초록 + 깜빡이는 중이었다면 자동 해제
            leds.set_removed(idx)
            leds.stop_blink(idx)

    rfid = RFIDController(SLOT_CONFIG, on_event=handle_rfid_event)

    # 4) 종료 시그널 -> 스캔 루프 정지
    def handle_signal(sig, frame):
        print("\n[APP] signal received, stopping...")
        rfid.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # 5) 기동
    try:
        rfid.setup()
        mqttc.connect()
        rfid.run()  # blocking

    except KeyboardInterrupt:
        pass

    finally:
        print("[APP] cleanup")
        leds.close()
        mqttc.close()
        rfid.close()


if __name__ == "__main__":
    main()
