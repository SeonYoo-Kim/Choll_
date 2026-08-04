#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WS281x 슬롯 LED 제어 모듈 (Raspberry Pi 5)

main.py에서 import해서 사용한다:

    from led_controller import SlotLEDController

    leds = SlotLEDController()   # 생성 시 전체 LED 초록으로 초기화
    leds.set_detected(0)         # 해당 인덱스 빨강 (카드 태깅)
    leds.set_removed(0)          # 해당 인덱스 초록 (카드 제거)
    leds.clear()                 # 전체 소등

배선 확인용 셀프테스트로 단독 실행도 가능.
cart.service가 돌고 있으면 LED 출력이 충돌하므로 먼저 내릴 것:

    sudo systemctl stop cart
    ~/cart/.venv/bin/python led_controller.py
"""

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

# 이 LED 체인은 네이티브 RGB 순서로 확인됨.
# (기존 "RBG" + GREEN=(0,0,255) 조합과 전송 바이트가 완전히 동일하며,
#  색 상수를 표준 (R, G, B) 표기로 쓸 수 있도록 정규화한 것.
#  색이 이상하면 셀프테스트로 확인 후 이 값만 조정.)
LED_BYTEORDER = "GRB"

COLOR_GREEN = (0, 255, 0)  # 카드 없음 (기본 상태)
COLOR_RED = (255, 0, 0)    # 카드 태깅됨
COLOR_OFF = (0, 0, 0)


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
    슬롯 상태 표시용 WS281x LED 제어.
    - 생성 시: 전체 LED 초록 (슬롯 5개 + 여분 1개 모두)
    - set_detected(): 해당 인덱스 빨강 / set_removed(): 초록
    - clear(): 전체 소등 (앱 종료 시 호출)
    LED 쓰기 오류가 호출측(RFID 스캔 루프)을 죽이지 않도록
    예외는 내부에서 잡고 로그만 남긴다.
    """

    def __init__(self, pin=LED_PIN, count=LED_COUNT, brightness=LED_BRIGHTNESS):
        self.count = count

        self.pixels = Pi5Pixelbuf(
            pin,
            count,
            auto_write=True,
            byteorder=LED_BYTEORDER,
            brightness=brightness,
        )

        self.init_all()

    def _fill(self, color):
        try:
            self.pixels.fill(color)
        except Exception as e:
            print(f"[LED] fill failed: {e}")

    def _set(self, index, color):
        try:
            if 0 <= index < self.count:
                self.pixels[index] = color
        except Exception as e:
            print(f"[LED] write failed (index={index}): {e}")

    def init_all(self):
        """전체 LED 초록으로 초기화."""
        self._fill(COLOR_GREEN)

    def set_detected(self, index):
        self._set(index, COLOR_RED)

    def set_removed(self, index):
        self._set(index, COLOR_GREEN)

    def clear(self):
        """전체 소등."""
        self._fill(COLOR_OFF)


# ============================================================
# 단독 실행: 배선/색상 테스트
# ============================================================

def _self_test():
    # print("[LED] self test: all green -> each red once -> all blue -> off")

    leds = SlotLEDController()
    time.sleep(1.0)

    for i in range(LED_COUNT):
        leds.set_detected(i)
        time.sleep(0.4)
        leds.set_removed(i)

    # 초록/빨강에 더해 파랑까지 제대로 나오면
    # byteorder가 하드웨어와 완전히 일치한다는 뜻
    leds._fill((0, 0, 255))
    time.sleep(1.0)

    leds.clear()
    print("[LED] self test done")


if __name__ == "__main__":
    _self_test()