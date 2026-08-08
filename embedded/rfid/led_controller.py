#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS281x 슬롯 LED 제어 모듈 (Raspberry Pi 5)

표시 모델:
- 기본색(base): RFID 상태에 따른 슬롯별 색 (카드 없음=초록, 있음=빨강)
- 깜빡임(blink): 서버 점등 명령으로 지정된 인덱스는 빨강<->꺼짐을 반복
  깜빡임이 표시 우선권을 가지며, 해제되면 그 시점의 기본색으로 복귀한다.

세 스레드(RFID 스캔, MQTT 수신, 내부 blink 스레드)가 동시에 LED를
만질 수 있으므로 모든 픽셀 쓰기는 내부 lock으로 직렬화된다.

사용 예:

    from led_controller import SlotLEDController

    leds = SlotLEDController()   # 생성 시 전체 초록 + blink 스레드 시작
    leds.set_detected(0)         # 인덱스 0 기본색을 빨강으로 (카드 태깅)
    leds.set_removed(0)          # 인덱스 0 기본색을 초록으로 (카드 제거)
    leds.set_blink([1, 3])       # 인덱스 1, 3 빨강 깜빡임 (기존 깜빡임은 교체)
    leds.set_blink([])           # 깜빡임 전체 중지 -> 기본색 복귀
    leds.stop_blink(1)           # 인덱스 1만 깜빡임 해제 -> 기본색 복귀
    leds.close()                 # blink 스레드 정지 + 전체 소등 (종료 시)

배선/색상 확인용 셀프테스트로 단독 실행도 가능.
cart.service가 돌고 있으면 LED 출력이 충돌하므로 먼저 내릴 것:

    sudo systemctl stop cart
    ~/cart/.venv/bin/python led_controller.py
"""

import threading
import time

import board
import adafruit_pixelbuf
from adafruit_raspberry_pi5_neopixel_write import neopixel_write


# ============================================================
# LED Config
# ============================================================

LED_PIN = board.D18    # WS281x DIN 연결 핀
LED_COUNT = 6          # 체인에 연결된 LED 총 개수 (슬롯 5개 + 여분 1개)
LED_BRIGHTNESS = 0.1

# WS2812B 표준 채널 순서 (셀프테스트 3색으로 확인).
# 색이 이상하면 셀프테스트를 돌려 확인 후 이 값만 조정.
LED_BYTEORDER = "GRB"

COLOR_GREEN = (0, 255, 0)  # 카드 없음 (기본 상태)
COLOR_RED = (255, 0, 0)    # 카드 태깅됨 / 깜빡임 점등색
COLOR_OFF = (0, 0, 0)

BLINK_INTERVAL_SEC = 0.5   # 깜빡임 반전 주기


# ============================================================
# Pi 5 PixelBuf
# ============================================================

class Pi5Pixelbuf(adafruit_pixelbuf.PixelBuf):
    def __init__(self, pin, size, **kwargs):
        self._pin = pin
        super().__init__(size=size, **kwargs)

    def _transmit(self, buf):
        neopixel_write(self._pin, buf)


# ============================================================
# Slot LED Controller
# ============================================================

class SlotLEDController:
    """
    슬롯 상태 표시용 WS281x LED 제어 (thread-safe).
    LED 쓰기 오류가 호출측을 죽이지 않도록 예외는 내부에서 잡고 로그만 남긴다.
    """

    def __init__(self, pin=LED_PIN, count=LED_COUNT, brightness=LED_BRIGHTNESS):
        self.count = count
        self._lock = threading.RLock()

        self.pixels = Pi5Pixelbuf(
            pin,
            count,
            auto_write=True,
            byteorder=LED_BYTEORDER,
            brightness=brightness,
        )

        # 표시 상태
        self._base = [COLOR_GREEN] * count  # 인덱스별 기본색
        self._blink = set()                 # 깜빡이는 중인 인덱스 집합
        self._blink_on = False              # 현재 깜빡임 위상 (켜짐/꺼짐)

        with self._lock:
            self._fill_raw(COLOR_GREEN)

        self._stop_event = threading.Event()
        self._blink_thread = threading.Thread(
            target=self._blink_loop,
            name="led-blink",
            daemon=True,
        )
        self._blink_thread.start()

    # ---------------- 내부 픽셀 쓰기 (호출측이 lock 보유) ----------------

    def _fill_raw(self, color):
        try:
            self.pixels.fill(color)
        except Exception as e:
            print(f"[LED] fill failed: {e}")

    def _set_raw(self, index, color):
        try:
            self.pixels[index] = color
        except Exception as e:
            print(f"[LED] write failed (index={index}): {e}")

    # ---------------- 기본색 (RFID 상태) ----------------

    def set_detected(self, index):
        """카드 태깅: 기본색을 빨강으로."""
        self._set_base(index, COLOR_RED)

    def set_removed(self, index):
        """카드 제거: 기본색을 초록으로."""
        self._set_base(index, COLOR_GREEN)

    def _set_base(self, index, color):
        if not (0 <= index < self.count):
            return

        with self._lock:
            self._base[index] = color
            # 깜빡이는 중인 인덱스는 blink가 표시를 소유한다.
            # 기본색은 기록만 해두고, 깜빡임 해제 시 복귀에 사용된다.
            if index not in self._blink:
                self._set_raw(index, color)

    # ---------------- 깜빡임 (서버 점등 명령) ----------------

    def set_blink(self, indices):
        """
        깜빡일 인덱스 집합을 통째로 교체한다.
        - 새로 지정된 인덱스는 즉시 켜진(빨강) 상태로 시작
        - 목록에서 빠진 인덱스는 기본색으로 복귀
        - 빈 리스트를 주면 깜빡임 전체 중지
        """
        new = {i for i in indices if 0 <= i < self.count}

        with self._lock:
            stopped = self._blink - new
            self._blink = new

            for idx in stopped:
                self._set_raw(idx, self._base[idx])

            self._blink_on = True
            for idx in new:
                self._set_raw(idx, COLOR_RED)

    def stop_blink(self, index):
        """
        특정 인덱스만 깜빡임 해제. 깜빡이는 중이었다면 기본색으로 복귀,
        아니었다면 아무 일도 하지 않는다.
        """
        if not (0 <= index < self.count):
            return

        with self._lock:
            if index in self._blink:
                self._blink.discard(index)
                self._set_raw(index, self._base[index])

    def _blink_loop(self):
        while not self._stop_event.wait(BLINK_INTERVAL_SEC):
            with self._lock:
                if not self._blink:
                    continue

                self._blink_on = not self._blink_on
                color = COLOR_RED if self._blink_on else COLOR_OFF

                for idx in self._blink:
                    self._set_raw(idx, color)

    # ---------------- 종료 ----------------

    def clear(self):
        """깜빡임 중지 + 전체 소등."""
        with self._lock:
            self._blink.clear()
            self._fill_raw(COLOR_OFF)

    def close(self):
        """blink 스레드 정지 후 소등. 앱 종료 시 호출."""
        self._stop_event.set()
        self._blink_thread.join(timeout=2.0)
        self.clear()


# ============================================================
# 단독 실행: 배선/색상/깜빡임 테스트
# ============================================================

def _self_test():
    print(
        "[LED] self test: all green -> red march -> all blue "
        "-> blink all 3s -> back to green -> off"
    )

    leds = SlotLEDController()
    time.sleep(1.0)

    # 빨강 행진
    for i in range(LED_COUNT):
        leds.set_detected(i)
        time.sleep(0.4)
        leds.set_removed(i)

    # 초록/빨강에 더해 파랑까지 제 색으로 나오면
    # byteorder가 하드웨어와 완전히 일치한다는 뜻
    with leds._lock:
        leds._fill_raw((0, 0, 255))
    time.sleep(1.0)

    # 깜빡임 3초 -> 해제 시 기본색(초록) 복귀 확인
    leds.set_blink(range(LED_COUNT))
    time.sleep(3.0)
    leds.set_blink([])
    time.sleep(1.0)

    leds.close()
    print("[LED] self test done")


if __name__ == "__main__":
    _self_test()
