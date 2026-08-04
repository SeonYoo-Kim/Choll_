#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MFRC522 RFID 스캔 모듈 (Raspberry Pi 5, SPI 공유 + 수동 CS)

여러 리더를 SPI 버스 하나에 물리고 GPIO로 CS를 전환하며 폴링한다.
슬롯별 카드 존재 상태머신을 돌리다가 변화가 있을 때만 콜백으로 알린다.
MQTT나 LED는 전혀 모른다 — 그 연결은 main.py의 몫.

사용 예:

    from rfid_controller import RFIDController

    def on_event(slot_id, uid, event):   # event: "DETECTED" | "REMOVED"
        print(slot_id, uid, event)

    rfid = RFIDController(
        slot_config=[{"slot_id": 1, "cs_pin": 16}, ...],
        on_event=on_event,
    )
    rfid.setup()
    rfid.run()      # blocking. 시그널 핸들러 등에서 rfid.stop()으로 종료
    rfid.close()
"""

import time

import spidev
import lgpio


# ============================================================
# RFID Config
# ============================================================

SPI_BUS = 0
SPI_DEVICE = 0
SPI_SPEED_HZ = 1_000_000

CARD_LOST_TIMEOUT = 1.0   # 이 시간 동안 안 보이면 REMOVED로 판정 (초)
SCAN_INTERVAL = 0.05      # 전체 슬롯 1회 순회 후 대기 (초)


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
# RC522 Reader (단일 리더 저수준 드라이버)
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
        카드가 있으면 UID 문자열 반환. 없으면 None.
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
# RFID Controller (다중 슬롯 스캔 + 상태머신)
# ============================================================

class RFIDController:
    """
    slot_config의 각 슬롯을 순회 폴링하며 카드 존재 상태를 추적한다.
    상태가 바뀔 때만 on_event(slot_id, uid, event) 콜백을 호출한다.
      - "DETECTED": 카드가 새로 감지됨 (다른 카드로 교체된 경우 포함)
      - "REMOVED" : 카드가 card_lost_timeout 동안 안 보임
    콜백에서 예외가 나도 스캔 루프는 죽지 않는다.
    """

    def __init__(
        self,
        slot_config,
        on_event=None,
        card_lost_timeout=CARD_LOST_TIMEOUT,
        scan_interval=SCAN_INTERVAL,
    ):
        # slot_config: [{"slot_id": 1, "cs_pin": 16}, ...] (여분 키는 무시)
        self.slot_config = list(slot_config)
        self.on_event = on_event
        self.card_lost_timeout = card_lost_timeout
        self.scan_interval = scan_interval

        self.running = True

        self.spi = None
        self.gpio = None
        self.readers = []
        self.slot_states = {}

    # ---------------- setup ----------------

    def setup(self):
        self._setup_spi()
        self._setup_gpio()
        self._setup_readers()

    def _setup_spi(self):
        self.spi = spidev.SpiDev()
        self.spi.open(SPI_BUS, SPI_DEVICE)
        self.spi.max_speed_hz = SPI_SPEED_HZ
        self.spi.mode = 0

    def _setup_gpio(self):
        cs_pins = [cfg["cs_pin"] for cfg in self.slot_config]
        self.gpio = GPIOManager(cs_pins)

        for pin in cs_pins:
            self.gpio.write(pin, 1)

    def _setup_readers(self):
        for cfg in self.slot_config:
            reader = MFRC522(
                spi=self.spi,
                gpio_mgr=self.gpio,
                cs_pin=cfg["cs_pin"],
                name=cfg["slot_id"],
            )

            version = reader.read_version()

            if version in (0x00, 0xFF):
                print(
                    f"[WARN] slot {cfg['slot_id']} reader may not be responding. "
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

    # ---------------- event emit ----------------

    def _emit(self, slot_id, uid, event):
        if self.on_event is None:
            return
        try:
            self.on_event(slot_id, uid, event)
        except Exception as e:
            print(f"[RFID] on_event callback failed: {e}")

    # ---------------- state machine ----------------

    def _handle_uid_seen(self, slot_id, uid, now):
        state = self.slot_states[slot_id]
        present_uid = state["present_uid"]

        state["last_seen_uid"] = uid
        state["last_seen_time"] = now

        # 기존에 아무 카드도 없었고 새 카드 감지
        if present_uid is None:
            state["present_uid"] = uid
            self._emit(slot_id, uid, "DETECTED")
            return

        # 같은 카드 계속 감지
        if present_uid == uid:
            return

        # 다른 카드로 바뀐 경우
        self._emit(slot_id, present_uid, "REMOVED")
        state["present_uid"] = uid
        self._emit(slot_id, uid, "DETECTED")

    def _handle_uid_not_seen(self, slot_id, now):
        state = self.slot_states[slot_id]
        present_uid = state["present_uid"]

        if present_uid is None:
            return

        elapsed = now - state["last_seen_time"]

        if elapsed >= self.card_lost_timeout:
            self._emit(slot_id, present_uid, "REMOVED")

            state["present_uid"] = None
            state["last_seen_uid"] = None
            state["last_seen_time"] = 0.0

    # ---------------- run / stop / close ----------------

    def run(self):
        """blocking 스캔 루프. stop() 호출 시 반환."""
        print("[RFID] scan loop started")

        while self.running:
            now = time.monotonic()

            for item in self.readers:
                slot_id = item["slot_id"]
                reader = item["reader"]

                try:
                    uid = reader.read_uid()

                    if uid is not None:
                        self._handle_uid_seen(slot_id, uid, now)
                    else:
                        self._handle_uid_not_seen(slot_id, now)

                except Exception as e:
                    print(f"[RFID] slot {slot_id} error: {e}")
                    self._handle_uid_not_seen(slot_id, now)

                time.sleep(0.005)

            time.sleep(self.scan_interval)

    def stop(self):
        self.running = False

    def close(self):
        if self.spi is not None:
            try:
                self.spi.close()
            except Exception:
                pass
            self.spi = None

        if self.gpio is not None:
            self.gpio.close()
            self.gpio = None
