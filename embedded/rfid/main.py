#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RFID 스캔 + MQTT 발행 + 슬롯 LED 표시 (단일 프로세스)

LED 제어는 led_controller.py 모듈에 분리되어 있다.
MQTT는 connect_async를 사용해 부팅 직후 네트워크가 늦게 떠도
죽지 않고 백그라운드에서 연결될 때까지 재시도한다.

평소에는 systemd 서비스(cart.service)로 자동 실행된다.
수동 실행이 필요하면 서비스와 GPIO가 충돌하므로 먼저 내릴 것:

    sudo systemctl stop cart
    ~/cart/.venv/bin/python -u main.py
"""

import time
import json
import signal
import threading
from datetime import datetime, timezone, timedelta

import spidev
import lgpio
import paho.mqtt.client as mqtt

from led_controller import SlotLEDController


# ============================================================
# User Config
# ============================================================


MQTT_BROKER_HOST = "your-server.example.com"
MQTT_BROKER_PORT = 1883
MQTT_USERNAME = "choll"
MQTT_PASSWORD = "CHANGE_ME"
MQTT_TOPIC = "status/slot"

# 하트비트 / 상태(LWT) 설정
HEARTBEAT_TOPIC = "status/cart"
HEARTBEAT_INTERVAL_SEC = 5.0
KST = timezone(timedelta(hours=9))

SPI_BUS = 0
SPI_DEVICE = 0
SPI_SPEED_HZ = 1_000_000

# BCM GPIO 번호 기준
# led_index: WS281x 데이지체인에서 이 슬롯 LED의 위치 (0부터 시작)
SLOT_CONFIG = [
    {"slot_id": 1, "cs_pin": 16, "led_index": 0},
    {"slot_id": 2, "cs_pin": 20, "led_index": 1},
    {"slot_id": 3, "cs_pin": 5,  "led_index": 2},
    {"slot_id": 4, "cs_pin": 6,  "led_index": 3},
    {"slot_id": 5, "cs_pin": 13, "led_index": 4},
]

CARD_LOST_TIMEOUT = 1.0
SCAN_INTERVAL = 0.05


# ============================================================
# MFRC522 Constants
# ============================================================

MI_OK = 0
MI_NOTAGERR = 1
MI_ERR = 2

PCD_IDLE = 0x00
PCD_AUTHENT = 0x0E
PCD_RECEIVE = 0x08
PCD_TRANSMIT = 0x04
PCD_TRANSCEIVE = 0x0C
PCD_RESETPHASE = 0x0F
PCD_CALCCRC = 0x03

PICC_REQIDL = 0x26
PICC_REQALL = 0x52
PICC_ANTICOLL = 0x93

CommandReg = 0x01
ComIEnReg = 0x02
DivIEnReg = 0x03
ComIrqReg = 0x04
DivIrqReg = 0x05
ErrorReg = 0x06
Status1Reg = 0x07
Status2Reg = 0x08
FIFODataReg = 0x09
FIFOLevelReg = 0x0A
WaterLevelReg = 0x0B
ControlReg = 0x0C
BitFramingReg = 0x0D
CollReg = 0x0E

ModeReg = 0x11
TxModeReg = 0x12
RxModeReg = 0x13
TxControlReg = 0x14
TxASKReg = 0x15
TxSelReg = 0x16
RxSelReg = 0x17
RxThresholdReg = 0x18
DemodReg = 0x19

TModeReg = 0x2A
TPrescalerReg = 0x2B
TReloadRegH = 0x2C
TReloadRegL = 0x2D

VersionReg = 0x37


# ============================================================
# GPIO Helper
# ============================================================

class GPIOManager:
    def __init__(self, output_pins):
        self.output_pins = list(output_pins)
        self.chip = None
        self.chip_num = None

        self._open_gpiochip()

    def _open_gpiochip(self):
        """
        0~5번을 순회하며 실제로 핀 claim이 되는 chip을 찾는다.
        실패 시 칩별 에러를 전부 모아서 예외 메시지로 보여준다.
        (예: 다른 프로세스가 핀을 선점 중이면 'GPIO busy'가 그대로 보임)
        """
        errors = []

        for chip_num in range(0, 6):
            try:
                h = lgpio.gpiochip_open(chip_num)

                claimed = []
                try:
                    for pin in self.output_pins:
                        lgpio.gpio_claim_output(h, pin, 1)
                        claimed.append(pin)

                    self.chip = h
                    self.chip_num = chip_num
                    return

                except Exception as e:
                    errors.append(f"chip{chip_num} claim failed: {e}")
                    for pin in claimed:
                        try:
                            lgpio.gpio_free(h, pin)
                        except Exception:
                            pass
                    lgpio.gpiochip_close(h)

            except Exception as e:
                errors.append(f"chip{chip_num} open failed: {e}")

        raise RuntimeError(
            "Failed to open suitable gpiochip: " + " | ".join(errors)
        )

    def write(self, pin, value):
        lgpio.gpio_write(self.chip, pin, int(value))

    def close(self):
        if self.chip is not None:
            for pin in self.output_pins:
                try:
                    lgpio.gpio_write(self.chip, pin, 1)
                    lgpio.gpio_free(self.chip, pin)
                except Exception:
                    pass

            try:
                lgpio.gpiochip_close(self.chip)
            except Exception:
                pass

            self.chip = None


# ============================================================
# RC522 Reader
# ============================================================

class MFRC522:
    def __init__(self, spi, gpio_mgr, cs_pin, name="rc522"):
        self.spi = spi
        self.gpio = gpio_mgr
        self.cs_pin = cs_pin
        self.name = name

        self._cs_high()
        time.sleep(0.01)

        self.init()

    def _cs_low(self):
        self.gpio.write(self.cs_pin, 0)

    def _cs_high(self):
        self.gpio.write(self.cs_pin, 1)

    def _xfer2(self, data):
        self._cs_low()
        time.sleep(0.000005)
        result = self.spi.xfer2(data)
        time.sleep(0.000005)
        self._cs_high()
        return result

    def write_reg(self, addr, val):
        self._xfer2([((addr << 1) & 0x7E), val & 0xFF])

    def read_reg(self, addr):
        result = self._xfer2([(((addr << 1) & 0x7E) | 0x80), 0])
        return result[1]

    def set_bit_mask(self, reg, mask):
        tmp = self.read_reg(reg)
        self.write_reg(reg, tmp | mask)

    def clear_bit_mask(self, reg, mask):
        tmp = self.read_reg(reg)
        self.write_reg(reg, tmp & (~mask))

    def reset(self):
        self.write_reg(CommandReg, PCD_RESETPHASE)
        time.sleep(0.05)

    def antenna_on(self):
        temp = self.read_reg(TxControlReg)
        if not (temp & 0x03):
            self.set_bit_mask(TxControlReg, 0x03)

    def antenna_off(self):
        self.clear_bit_mask(TxControlReg, 0x03)

    def init(self):
        self.reset()

        self.write_reg(TModeReg, 0x8D)
        self.write_reg(TPrescalerReg, 0x3E)
        self.write_reg(TReloadRegL, 30)
        self.write_reg(TReloadRegH, 0)

        self.write_reg(TxASKReg, 0x40)
        self.write_reg(ModeReg, 0x3D)

        self.antenna_on()

    def read_version(self):
        return self.read_reg(VersionReg)

    def to_card(self, command, send_data):
        back_data = []
        back_len = 0
        status = MI_ERR

        irq_en = 0x00
        wait_irq = 0x00

        if command == PCD_AUTHENT:
            irq_en = 0x12
            wait_irq = 0x10
        elif command == PCD_TRANSCEIVE:
            irq_en = 0x77
            wait_irq = 0x30

        self.write_reg(ComIEnReg, irq_en | 0x80)
        self.clear_bit_mask(ComIrqReg, 0x80)
        self.set_bit_mask(FIFOLevelReg, 0x80)

        self.write_reg(CommandReg, PCD_IDLE)

        for data in send_data:
            self.write_reg(FIFODataReg, data)

        self.write_reg(CommandReg, command)

        if command == PCD_TRANSCEIVE:
            self.set_bit_mask(BitFramingReg, 0x80)

        i = 2000
        while True:
            n = self.read_reg(ComIrqReg)
            i -= 1
            if not ((i != 0) and not (n & 0x01) and not (n & wait_irq)):
                break

        self.clear_bit_mask(BitFramingReg, 0x80)

        if i != 0:
            if (self.read_reg(ErrorReg) & 0x1B) == 0x00:
                status = MI_OK

                if n & irq_en & 0x01:
                    status = MI_NOTAGERR

                if command == PCD_TRANSCEIVE:
                    fifo_len = self.read_reg(FIFOLevelReg)
                    last_bits = self.read_reg(ControlReg) & 0x07

                    if last_bits != 0:
                        back_len = (fifo_len - 1) * 8 + last_bits
                    else:
                        back_len = fifo_len * 8

                    if fifo_len == 0:
                        fifo_len = 1

                    if fifo_len > 16:
                        fifo_len = 16

                    for _ in range(fifo_len):
                        back_data.append(self.read_reg(FIFODataReg))

            else:
                status = MI_ERR

        return status, back_data, back_len

    def request(self, req_mode=PICC_REQIDL):
        self.write_reg(BitFramingReg, 0x07)

        status, back_data, back_bits = self.to_card(PCD_TRANSCEIVE, [req_mode])

        if status != MI_OK or back_bits != 0x10:
            status = MI_ERR

        return status, back_bits

    def anticoll(self):
        ser_num_check = 0

        self.write_reg(BitFramingReg, 0x00)

        status, back_data, back_bits = self.to_card(
            PCD_TRANSCEIVE,
            [PICC_ANTICOLL, 0x20]
        )

        if status == MI_OK:
            if len(back_data) == 5:
                for i in range(4):
                    ser_num_check ^= back_data[i]

                if ser_num_check != back_data[4]:
                    status = MI_ERR
            else:
                status = MI_ERR

        return status, back_data

    def read_uid(self):
        """
        카드가 있으면 UID 문자열 반환.
        없으면 None 반환.
        예: '3E40F306'
        """
        status, _ = self.request(PICC_REQIDL)

        if status != MI_OK:
            return None

        status, uid_bytes = self.anticoll()

        if status != MI_OK:
            return None

        if len(uid_bytes) < 4:
            return None

        uid = "".join(f"{b:02X}" for b in uid_bytes[:4])
        return uid


# ============================================================
# MQTT Publisher
# ============================================================

class RFIDMQTTPublisher:
    def __init__(self, broker_host, broker_port, topic):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.topic = topic

        client_id = "rfid_publisher"

        # paho-mqtt 1.x / 2.x 호환
        try:
            self.client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
            )
        except Exception:
            self.client = mqtt.Client(client_id=client_id)

        # 브로커 인증 정보 (connect() 호출 이전에 설정해야 함)
        self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

        # LWT: 비정상 종료(전원 차단, 크래시 등) 시
        # 브로커가 대신 offline 상태를 retain으로 발행해준다.
        # 반드시 connect() 전에 등록해야 함.
        self.client.will_set(
            HEARTBEAT_TOPIC,
            json.dumps({"status": "offline"}),
            qos=1,
            retain=True,
        )
        self.client.on_connect = self._on_connect

        self._hb_stop = threading.Event()
        self._hb_thread = None

    def connect(self):
        # connect_async + loop_start:
        # 부팅 직후 네트워크가 아직 안 떠 있어도 예외로 죽지 않고,
        # 백그라운드 스레드가 연결될 때까지 계속 재시도한다.
        # 연결 전에 발행된 QoS1 이벤트는 큐에 쌓였다가 연결되면 전송됨.
        print(
            f"[MQTT] connecting to {self.broker_host}:{self.broker_port} "
            f"(background retry enabled)"
        )
        self.client.connect_async(self.broker_host, self.broker_port, keepalive=60)
        self.client.loop_start()

        self._start_heartbeat()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        # paho-mqtt 1.x / 2.x 콜백 시그니처 모두 호환.
        # 연결/재연결 시마다 online 상태를 retain으로 발행해서
        # LWT가 남긴 offline 상태를 덮어쓴다.
        client.publish(
            HEARTBEAT_TOPIC,
            json.dumps({"status": "online"}),
            qos=1,
            retain=True,
        )
        print(f"[MQTT] on_connect: published online status to {HEARTBEAT_TOPIC}")

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

    def publish_event(self, slot_id, uid, event):
        payload = {
            "slot_id": int(slot_id),
            "uid": str(uid),
            "event": str(event),
            "timestamp": datetime.now(KST).isoformat(timespec="milliseconds"),
        }

        payload_str = json.dumps(payload, ensure_ascii=False)

        result = self.client.publish(
            self.topic,
            payload_str,
            qos=1,
            retain=False,
        )

        print(f"[MQTT] publish {event}: {payload_str}")

        return result

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
# App
# ============================================================

class RFIDApp:
    def __init__(self):
        self.running = True

        self.spi = None
        self.gpio = None
        self.readers = []
        self.publisher = None

        self.leds = None
        self.slot_led_index = {}  # slot_id -> led index

        self.slot_states = {}

    def setup_spi(self):
        self.spi = spidev.SpiDev()
        self.spi.open(SPI_BUS, SPI_DEVICE)
        self.spi.max_speed_hz = SPI_SPEED_HZ
        self.spi.mode = 0

    def setup_gpio(self):
        cs_pins = [cfg["cs_pin"] for cfg in SLOT_CONFIG]
        self.gpio = GPIOManager(cs_pins)

        for pin in cs_pins:
            self.gpio.write(pin, 1)

    def setup_readers(self):
        for cfg in SLOT_CONFIG:
            reader = MFRC522(
                spi=self.spi,
                gpio_mgr=self.gpio,
                cs_pin=cfg["cs_pin"],
                name=cfg["slot_id"],
            )

            version = reader.read_version()

            if version in (0x00, 0xFF):
                print(
                    f"[WARN] {cfg['slot_id']} reader may not be responding. "
                    f"Check wiring, power, SPI, CS pin."
                )

            self.readers.append({
                "slot_id": cfg["slot_id"],
                "cs_pin": cfg["cs_pin"],
                "reader": reader,
            })

            self.slot_states[cfg["slot_id"]] = {
                "present_uid": None,
                "last_seen_uid": None,
                "last_seen_time": 0.0,
            }

    def setup_leds(self):
        self.slot_led_index = {
            cfg["slot_id"]: cfg["led_index"] for cfg in SLOT_CONFIG
        }

        self.leds = SlotLEDController()
        print("[LED] initialized: all LEDs green")

    def setup_mqtt(self):
        self.publisher = RFIDMQTTPublisher(
            broker_host=MQTT_BROKER_HOST,
            broker_port=MQTT_BROKER_PORT,
            topic=MQTT_TOPIC,
        )
        self.publisher.connect()

    def setup(self):
        self.setup_spi()
        self.setup_gpio()
        self.setup_readers()
        self.setup_leds()
        self.setup_mqtt()

    def handle_uid_seen(self, slot_id, uid, now):
        state = self.slot_states[slot_id]
        present_uid = state["present_uid"]

        state["last_seen_uid"] = uid
        state["last_seen_time"] = now

        # 기존에 아무 카드도 없었고 새 카드 감지
        if present_uid is None:
            state["present_uid"] = uid
            self.publisher.publish_event(slot_id, uid, "DETECTED")
            self.leds.set_detected(self.slot_led_index[slot_id])
            return

        # 같은 카드 계속 감지
        if present_uid == uid:
            return

        # 다른 카드로 바뀐 경우 (카드가 있는 상태이므로 LED는 빨강 유지)
        self.publisher.publish_event(slot_id, present_uid, "REMOVED")
        state["present_uid"] = uid
        self.publisher.publish_event(slot_id, uid, "DETECTED")
        self.leds.set_detected(self.slot_led_index[slot_id])

    def handle_uid_not_seen(self, slot_id, now):
        state = self.slot_states[slot_id]
        present_uid = state["present_uid"]

        if present_uid is None:
            return

        elapsed = now - state["last_seen_time"]

        if elapsed >= CARD_LOST_TIMEOUT:
            self.publisher.publish_event(slot_id, present_uid, "REMOVED")
            self.leds.set_removed(self.slot_led_index[slot_id])

            state["present_uid"] = None
            state["last_seen_uid"] = None
            state["last_seen_time"] = 0.0

    def loop(self):
        print("[APP] RFID scan loop started")

        while self.running:
            now = time.monotonic()

            for item in self.readers:
                slot_id = item["slot_id"]
                reader = item["reader"]

                try:
                    uid = reader.read_uid()

                    if uid is not None:
                        self.handle_uid_seen(slot_id, uid, now)
                    else:
                        self.handle_uid_not_seen(slot_id, now)

                except Exception as e:
                    print(f"[ERROR] {slot_id}: {e}")
                    self.handle_uid_not_seen(slot_id, now)

                time.sleep(0.005)

            time.sleep(SCAN_INTERVAL)

    def stop(self):
        self.running = False

    def cleanup(self):
        print("[APP] cleanup")

        if self.leds is not None:
            self.leds.clear()

        if self.publisher is not None:
            self.publisher.close()

        if self.spi is not None:
            try:
                self.spi.close()
            except Exception:
                pass

        if self.gpio is not None:
            self.gpio.close()


app = RFIDApp()


def signal_handler(sig, frame):
    print("\n[APP] signal received, stopping...")
    app.stop()


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        app.setup()
        app.loop()

    except KeyboardInterrupt:
        pass

    finally:
        app.cleanup()


if __name__ == "__main__":
    main()