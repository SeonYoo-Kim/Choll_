"""STM32 모터 제어 보드용 USB Serial 수동 테스트 도구.

Windows 콘솔에서 W/A/S/D/Space 키로 SET_WHEEL_VEL 명령을 20Hz(기본값)로
반복 전송하는 동시에, STM32가 UART Protocol v1(motor/docs/serial_protocol.md)에
따라 보내는 STATUS Packet을 수신해 콘솔에 표시한다. X/E 키는 SET_WHEEL_VEL의
좌우 속도 계산(MotionState)을 거치지 않고 실제 프로토콜의 STOP/ESTOP 명령
문자열을 즉시 1회 전송한다(실기 안전 테스트용). G 키는 blocking input() 없이
Kp/Ki를 순서대로 입력받아 SET_PI_GAINS 명령을 1회 전송하는 non-blocking
입력 모드로 진입한다(PI_GAINS/ERROR 응답 파싱 포함, --log 사용 시 CSV에도 기록).
'['/']' 키는 G 입력 모드 없이 Kp만 ±0.05 즉시 증감해 SET_PI_GAINS를 보낸다(Ki는
유지, 실기 튜닝 중 빠른 반복 조정용). ROS2 Serial Bridge로 발전시킬 것을 고려해
시리얼 연결, 명령 문자열 생성,
STATUS Packet 파싱, 반복 전송, 키 입력 처리, 안전 정지 로직을 각각의
클래스/함수로 분리했다.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import msvcrt  # Windows 전용 non-blocking 키 입력. GUI/추가 의존성 없이 표준 라이브러리로 처리.
import serial
from serial import SerialException

DEFAULT_BAUDRATE = 115200
DEFAULT_RATE_HZ = 20.0
DEFAULT_SPEED_RAD_S = 1.0
SERIAL_TIMEOUT_S = 1.0

STOP_REPEAT_COUNT = 5
STOP_REPEAT_INTERVAL_S = 0.02

# 키 -> 동작 라벨. 값은 MotionState.set_action()이 이해하는 동작명이다.
KEY_ACTIONS = {
    "w": "FORWARD",
    "s": "BACKWARD",
    "a": "TURN_LEFT",
    "d": "TURN_RIGHT",
    " ": "STOP",
}

# 키 -> 프로토콜 명령 이름. KEY_ACTIONS와 달리 MotionState의 좌우 속도 계산을
# 거치지 않고, run()에서 build_stop_command()/build_estop_command()로 즉시
# 1회 전송한다. w/a/s/d/Space/q와 겹치지 않는 키만 사용한다.
PROTOCOL_COMMAND_KEYS = {
    "x": "STOP",
    "e": "ESTOP",
}

QUIT_KEYS = {"q"}

# G: non-blocking Gain(Kp/Ki) 입력 모드 진입 키. w/a/s/d/space/x/e/q와 겹치지 않는다.
GAIN_INPUT_TRIGGER_KEY = "g"

# Gain 입력 모드에서 버퍼에 누적을 허용하는 문자(부호/소수점 포함). 범위/부호 검증은
# 클라이언트에서 하지 않고 STM Motor_SetPiGains()의 응답(ERROR,SET_PI_GAINS,OUT_OF_RANGE
# 등)에 맡긴다 - motor/docs/serial_protocol.md SET_PI_GAINS 절 참고.
GAIN_INPUT_ALLOWED_CHARS = "0123456789.-"

# '[' / ']': G 입력 모드 없이 Kp만 빠르게 증감시키는 단축키. w/a/s/d/space/x/e/g/q와
# 겹치지 않는다.
GAIN_KP_DECREASE_KEY = "["
GAIN_KP_INCREASE_KEY = "]"
GAIN_KP_STEP = 0.05

# motor_config.h의 MOTOR_PI_KP_MIN/MAX와 동일한 값이다(motor/docs/serial_protocol.md
# SET_PI_GAINS 절 참고). STM 코드를 여기서 import할 수 없어 상수를 그대로 복제한다 -
# STM 쪽 값이 바뀌면 이 두 상수도 함께 갱신해야 한다. '['/']' 단축키가 STM에 보내기
# 전에 이 범위로 clamp해, 이미 한계값에 있을 때 계속 눌러도 무의미한 OUT_OF_RANGE
# 응답이 반복되지 않게 한다.
MOTOR_PI_KP_MIN = 0.0
MOTOR_PI_KP_MAX = 50.0


class SerialConnection:
    """STM32 Virtual COM Port 연결을 관리한다.

    ROS2 Serial Bridge 노드에서도 그대로 재사용할 수 있도록 pyserial을
    직접 감싸는 얇은 래퍼로 유지한다.
    """

    def __init__(self, port: str, baudrate: int = DEFAULT_BAUDRATE, timeout: float = SERIAL_TIMEOUT_S):
        self._port = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._ser: serial.Serial | None = None

    def open(self) -> None:
        try:
            self._ser = serial.Serial(port=self._port, baudrate=self._baudrate, timeout=self._timeout)
        except SerialException as exc:
            raise ConnectionError(
                f"시리얼 포트 '{self._port}'를 열 수 없습니다 "
                f"(다른 프로그램이 점유 중이거나 포트 번호가 잘못되었을 수 있습니다): {exc}"
            ) from exc

    def write(self, data: bytes) -> None:
        if self._ser is None or not self._ser.is_open:
            raise ConnectionError("시리얼 포트가 열려 있지 않습니다.")
        try:
            self._ser.write(data)
        except SerialException as exc:
            raise ConnectionError(f"시리얼 전송 중 연결이 끊어졌습니다: {exc}") from exc

    def read_available(self) -> bytes:
        """현재까지 도착한 바이트를 블로킹 없이 모두 읽어 반환한다(없으면 b"")."""
        if self._ser is None or not self._ser.is_open:
            raise ConnectionError("시리얼 포트가 열려 있지 않습니다.")
        try:
            waiting = self._ser.in_waiting
            if waiting <= 0:
                return b""
            return self._ser.read(waiting)
        except SerialException as exc:
            raise ConnectionError(f"시리얼 수신 중 연결이 끊어졌습니다: {exc}") from exc

    def close(self) -> None:
        if self._ser is not None and self._ser.is_open:
            self._ser.close()

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open


def build_wheel_vel_command(left_rad_s: float, right_rad_s: float) -> str:
    """STM32 CommandParser가 기대하는 SET_WHEEL_VEL 명령 문자열(CRLF 포함) 생성"""
    return f"SET_WHEEL_VEL,{left_rad_s:.3f},{right_rad_s:.3f}\r\n"


def build_stop_command() -> str:
    """STM32 CommandParser가 기대하는 STOP 명령 문자열(CRLF 포함) 생성.

    SET_WHEEL_VEL,0,0과 달리 StopController의 Operational Stop을 유발한다
    (motor/docs/serial_protocol.md 참고).
    """
    return "STOP\r\n"


def build_estop_command() -> str:
    """STM32 CommandParser가 기대하는 ESTOP 명령 문자열(CRLF 포함) 생성.

    StopController의 Emergency Stop을 유발하며, STM이 재부팅되기 전까지
    소프트웨어로는 해제되지 않는다(motor/docs/serial_protocol.md 참고).
    """
    return "ESTOP\r\n"


def build_set_pi_gains_command(kp: float, ki: float) -> str:
    """STM32 CommandParser가 기대하는 SET_PI_GAINS 명령 문자열(CRLF 포함) 생성.

    범위(MOTOR_PI_KP/KI_MIN/MAX) 검증은 하지 않는다 - STM Motor_SetPiGains()가
    검증하고 ERROR,SET_PI_GAINS,<reason>으로 응답한다(motor/docs/serial_protocol.md 참고).
    """
    return f"SET_PI_GAINS,{kp:.4f},{ki:.4f}\r\n"


STATUS_PACKET_TOKEN = "STATUS"
STATUS_PACKET_FIELD_COUNT = 9  # "STATUS" + LT,LA,RT,RA,LPWM,RPWM,LE,RE


@dataclass
class StatusPacket:
    """STM32 -> PC STATUS Packet 한 건 (motor/docs/serial_protocol.md Protocol v1).

    필드 이름/순서는 문서의 LT,LA,RT,RA,LPWM,RPWM,LE,RE와 그대로 대응한다.
    """

    left_target: float
    left_actual: float
    right_target: float
    right_actual: float
    left_pwm: int
    right_pwm: int
    left_encoder: int
    right_encoder: int


def parse_status_packet(line: str) -> StatusPacket | None:
    """STATUS Packet 한 줄을 파싱한다. 형식이 맞지 않으면 None을 반환한다.

    ROS2 Serial Bridge 등 다른 소비자도 그대로 재사용할 수 있도록 콘솔 출력과
    분리된 순수 파싱 함수로 둔다.
    """
    fields = line.strip().split(",")
    if len(fields) != STATUS_PACKET_FIELD_COUNT or fields[0] != STATUS_PACKET_TOKEN:
        return None

    try:
        return StatusPacket(
            left_target=float(fields[1]),
            left_actual=float(fields[2]),
            right_target=float(fields[3]),
            right_actual=float(fields[4]),
            left_pwm=int(fields[5]),
            right_pwm=int(fields[6]),
            left_encoder=int(fields[7]),
            right_encoder=int(fields[8]),
        )
    except ValueError:
        return None


PI_GAINS_ACK_TOKEN = "PI_GAINS"
PI_GAINS_ACK_FIELD_COUNT = 3  # "PI_GAINS" + kp + ki

PI_GAINS_ERROR_TOKEN = "ERROR"
PI_GAINS_ERROR_COMMAND_FIELD = "SET_PI_GAINS"
PI_GAINS_ERROR_FIELD_COUNT = 3  # "ERROR" + "SET_PI_GAINS" + reason


@dataclass
class PiGainsAck:
    """STM32 -> PC PI_GAINS Ack 한 건 (motor/docs/serial_protocol.md SET_PI_GAINS 절)."""

    kp: float
    ki: float


def parse_pi_gains_ack(line: str) -> PiGainsAck | None:
    """PI_GAINS,<kp>,<ki> 한 줄을 파싱한다. 형식이 맞지 않으면 None을 반환한다."""
    fields = line.strip().split(",")
    if len(fields) != PI_GAINS_ACK_FIELD_COUNT or fields[0] != PI_GAINS_ACK_TOKEN:
        return None

    try:
        return PiGainsAck(kp=float(fields[1]), ki=float(fields[2]))
    except ValueError:
        return None


def parse_pi_gains_error(line: str) -> str | None:
    """ERROR,SET_PI_GAINS,<reason> 한 줄을 파싱해 reason을 반환한다.

    형식이 맞지 않거나 다른 명령에 대한 ERROR면 None을 반환한다(SET_PI_GAINS
    외 명령은 아직 ERROR 응답이 없다 - motor/docs/serial_protocol.md 참고).
    """
    fields = line.strip().split(",")
    if len(fields) != PI_GAINS_ERROR_FIELD_COUNT:
        return None
    if (fields[0] != PI_GAINS_ERROR_TOKEN) or (fields[1] != PI_GAINS_ERROR_COMMAND_FIELD):
        return None
    return fields[2]


class StatusReceiver:
    """수신 바이트를 줄 단위로 조립해 최신 STATUS Packet을 보관한다(non-blocking).

    STATUS Packet 외에 SET_PI_GAINS에 대한 PI_GAINS/ERROR 응답도 같은 스트림에
    섞여 도착하므로 이 클래스가 함께 파싱해 콜백으로 분기한다(줄 형식으로
    구분되므로 파싱 자체는 서로 독립적이다).

    on_packet이 주어지면 화면 갱신 주기(20Hz)와 무관하게, 파싱에 성공한
    STATUS Packet마다(수신되는 대로) 콜백을 호출한다 - CSV 로깅용.
    on_pi_gains_ack/on_pi_gains_error도 마찬가지로 해당 응답 줄이 도착할 때마다
    호출된다.
    """

    def __init__(
        self,
        on_packet: Callable[[StatusPacket], None] | None = None,
        on_pi_gains_ack: Callable[[float, float], None] | None = None,
        on_pi_gains_error: Callable[[str], None] | None = None,
    ) -> None:
        self._buffer = ""
        self._latest: StatusPacket | None = None
        self._on_packet = on_packet
        self._on_pi_gains_ack = on_pi_gains_ack
        self._on_pi_gains_error = on_pi_gains_error

    def feed(self, data: bytes) -> None:
        if not data:
            return

        self._buffer += data.decode("ascii", errors="ignore")
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)

            packet = parse_status_packet(line)
            if packet is not None:
                self._latest = packet
                if self._on_packet is not None:
                    self._on_packet(packet)
                continue

            ack = parse_pi_gains_ack(line)
            if ack is not None:
                if self._on_pi_gains_ack is not None:
                    self._on_pi_gains_ack(ack.kp, ack.ki)
                continue

            reason = parse_pi_gains_error(line)
            if reason is not None:
                if self._on_pi_gains_error is not None:
                    self._on_pi_gains_error(reason)
                continue

    @property
    def latest(self) -> StatusPacket | None:
        return self._latest


class MotionState:
    """현재 목표 동작(라벨 + 좌우 rad/s)을 스레드 안전하게 보관한다."""

    def __init__(self, speed_rad_s: float):
        self._speed = speed_rad_s
        self._lock = threading.Lock()
        self.label = "STOP"
        self.left = 0.0
        self.right = 0.0

    def set_action(self, action: str) -> None:
        with self._lock:
            if action == "FORWARD":
                self.left, self.right = self._speed, self._speed
            elif action == "BACKWARD":
                self.left, self.right = -self._speed, -self._speed
            elif action == "TURN_LEFT":
                self.left, self.right = -self._speed, self._speed
            elif action == "TURN_RIGHT":
                self.left, self.right = self._speed, -self._speed
            elif action == "STOP":
                self.left, self.right = 0.0, 0.0
            else:
                return
            self.label = action

    def force_zero(self, label: str) -> None:
        """좌우 속도를 즉시 0으로 강제하고 임의의 라벨을 지정한다.

        set_action()은 정해진 동작명(FORWARD 등)만 받지만, 이 메서드는
        STOP/ESTOP 프로토콜 명령 전송 직후 호출되어 "Operational Stop"/
        "Emergency Stop"처럼 Space의 "STOP" 라벨과 구분되는 임의의 라벨을
        표시할 수 있게 한다. ESTOP 이후 STM은 재부팅 전까지 재활성화되지
        않지만, Python Tool이 화면에 이전 속도값을 계속 표시하지 않도록
        하기 위한 것으로, 실제 모터 정지는 STM 쪽 StopController가 보장한다.
        """
        with self._lock:
            self.left, self.right = 0.0, 0.0
            self.label = label

    def snapshot(self) -> tuple[str, float, float]:
        with self._lock:
            return self.label, self.left, self.right


GAIN_INPUT_STAGE_INACTIVE = "INACTIVE"
GAIN_INPUT_STAGE_KP = "ENTER_KP"
GAIN_INPUT_STAGE_KI = "ENTER_KI"


class GainInputState:
    """G 키로 진입하는 non-blocking Kp/Ki 입력 상태 (state machine).

    blocking input()과 달리 msvcrt는 키를 한 글자씩 폴링하므로, 여러 tick에 걸쳐
    들어오는 숫자 문자를 이 클래스가 buffer에 누적한다. run()의 메인 루프(20Hz
    전송, STATUS 수신, 화면 갱신)는 이 상태와 무관하게 계속 돌며 run()에서 매 tick
    단일 스레드로만 호출되므로 락이 필요 없다(MotionState와 달리 스레드 안전 불필요).
    """

    def __init__(self) -> None:
        self.stage: str = GAIN_INPUT_STAGE_INACTIVE
        self.buffer: str = ""
        self._kp_value: float | None = None

    @property
    def active(self) -> bool:
        return self.stage != GAIN_INPUT_STAGE_INACTIVE

    def start(self) -> None:
        self.stage = GAIN_INPUT_STAGE_KP
        self.buffer = ""
        self._kp_value = None

    def cancel(self) -> None:
        self.stage = GAIN_INPUT_STAGE_INACTIVE
        self.buffer = ""
        self._kp_value = None

    def handle_char(self, raw: str) -> tuple[float, float] | None:
        """입력 모드 중 키 문자 하나를 처리한다.

        Kp/Ki 입력이 모두 끝나 전송할 준비가 되면 (kp, ki)를 반환하고 자신은
        INACTIVE로 돌아간다(호출자가 이 튜플로 SET_PI_GAINS를 전송). 그 외에는
        항상 None을 반환한다. Enter 시점에 buffer가 올바른 float으로 파싱되지
        않으면(형식 오류) 조용히 무시하고 buffer를 유지해 사용자가 계속
        수정(Backspace)할 수 있게 한다 - blocking하지 않으면서도 실수를 STM까지
        보내지 않기 위함이다.
        """
        if raw in ("\x08", "\x7f"):  # Backspace (터미널에 따라 0x7f로 오는 경우 포함)
            self.buffer = self.buffer[:-1]
            return None

        if raw == "\r":  # Enter: 현재 필드 확정
            try:
                value = float(self.buffer)
            except ValueError:
                return None

            if self.stage == GAIN_INPUT_STAGE_KP:
                self._kp_value = value
                self.stage = GAIN_INPUT_STAGE_KI
                self.buffer = ""
                return None

            if self.stage == GAIN_INPUT_STAGE_KI:
                kp = self._kp_value
                ki = value
                self.cancel()
                if kp is None:
                    return None
                return (kp, ki)

            return None

        if raw in GAIN_INPUT_ALLOWED_CHARS:
            self.buffer += raw

        return None


class PiGainsState:
    """SET_PI_GAINS 요청/응답 상태를 보관한다(run() 메인 루프 단일 스레드 전용).

    화면 표시(Applied/Pending/Error)와 CSV 로깅(요구사항: ACK 수신 이후 STATUS
    행부터 적용된 Kp/Ki 기록)이 이 상태를 공유해서 읽는다. applied_kp/ki는 이
    세션에서 ACK를 한 번도 받지 못했으면 None(STM의 실제 현재값은 이전 세션에서
    바뀌었을 수 있어 Python Tool이 알 방법이 없다 - 0.0f로 가정하지 않는다).
    """

    def __init__(self) -> None:
        self.applied_kp: float | None = None
        self.applied_ki: float | None = None
        self.pending_kp: float | None = None  # 전송했지만 ACK/ERROR 응답을 기다리는 중인 값
        self.pending_ki: float | None = None
        self.last_error_reason: str | None = None

    def mark_pending(self, kp: float, ki: float) -> None:
        self.pending_kp = kp
        self.pending_ki = ki
        self.last_error_reason = None

    def apply_ack(self, kp: float, ki: float) -> None:
        self.applied_kp = kp
        self.applied_ki = ki
        self.pending_kp = None
        self.pending_ki = None
        self.last_error_reason = None

    def apply_error(self, reason: str) -> None:
        self.pending_kp = None
        self.pending_ki = None
        self.last_error_reason = reason

    def best_known_kp(self) -> float:
        """'['/']' 증감의 기준이 되는 현재 Kp.

        아직 ACK를 못 받았어도 전송은 이미 해둔 값(pending_kp)이 있으면 그것을
        우선한다 - 그래야 ACK가 오기 전에 '['/']'를 연속으로 눌러도 매번 같은
        base에서 다시 계산하지 않고 계속 누적된다. 이 세션에서 SET_PI_GAINS를
        한 번도 보낸 적이 없으면(둘 다 None) STM 기본값(motor_config.c, 0.0f)을
        가정한다 - CSV 기록과 달리 이 값은 과거 기록이 아니라 다음에 보낼 명령을
        만들기 위한 시작점이므로, 문서화된 기본값을 기준으로 삼는 것이 합리적이다.
        """
        if self.pending_kp is not None:
            return self.pending_kp
        if self.applied_kp is not None:
            return self.applied_kp
        return 0.0

    def best_known_ki(self) -> float:
        """'['/']' 전송 시 Ki를 그대로 유지하기 위해 함께 실어 보낼 현재 Ki.

        best_known_kp()와 동일한 우선순위(pending > applied > 0.0 기본값)를 쓴다.
        """
        if self.pending_ki is not None:
            return self.pending_ki
        if self.applied_ki is not None:
            return self.applied_ki
        return 0.0


@dataclass
class KeyEvent:
    quit_requested: bool = False
    action: str | None = None
    protocol_command: str | None = None  # "STOP" 또는 "ESTOP": MotionState를 거치지 않고 즉시 전송
    start_gain_input: bool = False  # "G": GainInputState.start() 트리거
    kp_nudge: float | None = None  # "["/"]": +-GAIN_KP_STEP. Ki는 유지한 채 Kp만 즉시 재전송


class KeyboardReader:
    """Windows msvcrt 기반 non-blocking 키 입력 폴링.

    w/a/s/d/Space/q(단일 ASCII 문자, 별도 prefix 없음)와 동일한 방식으로
    x/e/g도 처리한다. 방향키 등 확장 키만 0x00/0xE0 prefix 바이트가 먼저
    오는데, 이 도구는 그런 키를 다루지 않으므로 msvcrt.getwch() 한 번
    호출로 항상 충분하다(기존 구현과 동일).
    """

    @staticmethod
    def _read_key() -> str | None:
        """키 입력이 있으면 대소문자 변환 없이 원본 문자 한 글자, 없으면 None."""
        if not msvcrt.kbhit():
            return None
        return msvcrt.getwch()

    @staticmethod
    def poll() -> KeyEvent:
        """일반(WASD 등) 모드 전용: 키를 알려진 동작으로 해석한다."""
        raw = KeyboardReader._read_key()
        if raw is None:
            return KeyEvent()

        key = raw.lower()

        if key in QUIT_KEYS:
            return KeyEvent(quit_requested=True)

        if key in PROTOCOL_COMMAND_KEYS:
            return KeyEvent(protocol_command=PROTOCOL_COMMAND_KEYS[key])

        if key in KEY_ACTIONS:
            return KeyEvent(action=KEY_ACTIONS[key])

        if key == GAIN_INPUT_TRIGGER_KEY:
            return KeyEvent(start_gain_input=True)

        if key == GAIN_KP_INCREASE_KEY:
            return KeyEvent(kp_nudge=GAIN_KP_STEP)

        if key == GAIN_KP_DECREASE_KEY:
            return KeyEvent(kp_nudge=-GAIN_KP_STEP)

        return KeyEvent()

    @staticmethod
    def read_raw() -> str | None:
        """Gain 입력 모드 전용: 동작 해석 없이 원본 문자 한 글자를 그대로 반환한다.

        poll()과 달리 소문자로 바꾸지 않는다 - GainInputState가 필요하면 직접
        처리한다(숫자/부호/소수점은 대소문자가 없어 무관).
        """
        return KeyboardReader._read_key()


def _enable_windows_ansi() -> None:
    """cmd.exe 콘솔에서 ANSI 커서 이동 이스케이프 시퀀스를 사용할 수 있도록 활성화한다.

    실패해도(예: 리다이렉트된 출력) 무시하고 진행한다 - 이 경우 StatusDisplay가
    화면을 제자리에서 갱신하지 못하고 줄이 흘러내리는 정도로 저하될 뿐이다.
    """
    try:
        enable_virtual_terminal_processing = 0x0004
        std_output_handle = -11
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(std_output_handle)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | enable_virtual_terminal_processing)
    except OSError:
        pass


class StatusDisplay:
    """Command 상태 + 최신 STATUS Packet을 고정된 블록으로 콘솔에 표시한다.

    매번 새 줄에 print하는 대신 ANSI 이스케이프로 커서를 블록 시작 위치로
    되돌려 같은 자리에 덮어쓴다. 블록 줄 수가 항상 동일해야 커서 이동이
    어긋나지 않으므로, STATUS Packet을 아직 못 받았을 때도 자리만 "--"로
    비워 줄 수를 맞춘다.
    """

    def __init__(self) -> None:
        self._printed_once = False

    def render(self, motion_label: str, motion_left: float, motion_right: float,
               packet: StatusPacket | None, gain_input: GainInputState, pi_gains: PiGainsState) -> None:
        lines = self._build_lines(motion_label, motion_left, motion_right, packet, gain_input, pi_gains)

        if self._printed_once:
            sys.stdout.write(f"\x1b[{len(lines)}A")
        for line in lines:
            sys.stdout.write("\x1b[2K" + line + "\n")
        sys.stdout.flush()
        self._printed_once = True

    @staticmethod
    def _build_lines(motion_label: str, motion_left: float, motion_right: float,
                      packet: StatusPacket | None, gain_input: GainInputState,
                      pi_gains: PiGainsState) -> list[str]:
        if packet is None:
            lt = la = rt = ra = err_l = err_r = lpwm = rpwm = le = re = "--"
        else:
            lt, rt = f"{packet.left_target:.2f}", f"{packet.right_target:.2f}"
            la, ra = f"{packet.left_actual:.2f}", f"{packet.right_actual:.2f}"
            # Error = Target - Actual. Python Tool에서만 계산하는 표시 전용 값이며 STM에는 없다.
            err_l = f"{packet.left_target - packet.left_actual:+.2f}"
            err_r = f"{packet.right_target - packet.right_actual:+.2f}"
            lpwm, rpwm = str(packet.left_pwm), str(packet.right_pwm)
            le, re = str(packet.left_encoder), str(packet.right_encoder)

        applied_kp = f"{pi_gains.applied_kp:.4f}" if pi_gains.applied_kp is not None else "--"
        applied_ki = f"{pi_gains.applied_ki:.4f}" if pi_gains.applied_ki is not None else "--"

        if gain_input.stage == GAIN_INPUT_STAGE_KP:
            gain_status_line = f"  Input Kp: {gain_input.buffer}_ (Enter로 확정, E:ESTOP+취소)"
        elif gain_input.stage == GAIN_INPUT_STAGE_KI:
            gain_status_line = f"  Input Ki: {gain_input.buffer}_ (Enter로 전송, E:ESTOP+취소)"
        elif pi_gains.pending_kp is not None:
            gain_status_line = f"  Pending : Kp={pi_gains.pending_kp:.4f} Ki={pi_gains.pending_ki:.4f} (응답 대기)"
        elif pi_gains.last_error_reason is not None:
            gain_status_line = f"  Error   : {pi_gains.last_error_reason}"
        else:
            gain_status_line = "  (G:Kp/Ki 직접 입력  [/]:Kp ±0.05)"

        separator = "-" * 50
        return [
            f"Command     {motion_label:10s} L={motion_left:+.2f} R={motion_right:+.2f}",
            separator,
            "Target",
            f"  L : {lt}",
            f"  R : {rt}",
            "",
            "Actual",
            f"  L : {la}",
            f"  R : {ra}",
            "",
            "Error",
            f"  L : {err_l}",
            f"  R : {err_r}",
            "",
            "PWM",
            f"  L : {lpwm}",
            f"  R : {rpwm}",
            "",
            "Encoder",
            f"  L : {le}",
            f"  R : {re}",
            "",
            "PI Gains",
            f"  Applied : Kp={applied_kp} Ki={applied_ki}",
            gain_status_line,
            separator,
        ]


class StatusLogger:
    """STATUS Packet을 CSV로 기록한다(Kp/Ki 튜닝용). 콘솔 UI와 독립적으로 동작한다.

    timestamp는 로깅 시작 시점부터의 경과 초(모노토닉)이며, 벽시계 시각이 아니다.
    Error는 STM이 보내지 않는 값으로, 여기서 Target - Actual로 계산해 추가한다.
    kp/ki는 이 STATUS 행 시점에 PC가 마지막으로 ACK 받은 적용값이다(PiGainsState
    참고) - SET_PI_GAINS ACK를 아직 한 번도 못 받았으면 빈 문자열로 남긴다(STM의
    실제 값을 모르는 채로 0.0f 등을 임의로 채우지 않는다).
    """

    CSV_HEADER = [
        "timestamp",
        "left_target", "left_actual", "left_error", "left_pwm",
        "right_target", "right_actual", "right_error", "right_pwm",
        "kp", "ki",
    ]

    def __init__(self, path: Path) -> None:
        self._start = time.monotonic()
        self._file = path.open("w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._writer.writerow(self.CSV_HEADER)

    def log(self, packet: StatusPacket, kp: float | None, ki: float | None) -> None:
        elapsed_s = time.monotonic() - self._start
        left_error = packet.left_target - packet.left_actual
        right_error = packet.right_target - packet.right_actual
        kp_str = f"{kp:.4f}" if kp is not None else ""
        ki_str = f"{ki:.4f}" if ki is not None else ""
        self._writer.writerow([
            f"{elapsed_s:.3f}",
            f"{packet.left_target:.4f}", f"{packet.left_actual:.4f}", f"{left_error:.4f}", packet.left_pwm,
            f"{packet.right_target:.4f}", f"{packet.right_actual:.4f}", f"{right_error:.4f}", packet.right_pwm,
            kp_str, ki_str,
        ])
        self._file.flush()

    def close(self) -> None:
        self._file.close()


def make_log_path() -> Path:
    """logs/날짜_시간.csv 경로를 만들고 logs/ 폴더가 없으면 생성한다.

    스크립트 파일 위치 기준 상대경로를 사용해, 실행 시 현재 작업 디렉터리와
    무관하게 항상 tools/motor_serial_test/logs/ 아래에 저장되도록 한다.
    """
    logs_dir = Path(__file__).resolve().parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    filename = time.strftime("%Y%m%d_%H%M%S") + ".csv"
    return logs_dir / filename


def safe_stop(conn: SerialConnection, repeat: int = STOP_REPEAT_COUNT, interval: float = STOP_REPEAT_INTERVAL_S) -> None:
    """정지 명령을 여러 번 전송해 통신 유실 시에도 모터가 확실히 멈추도록 한다."""
    stop_cmd = build_wheel_vel_command(0.0, 0.0).encode("ascii")
    for _ in range(repeat):
        try:
            conn.write(stop_cmd)
        except ConnectionError:
            break
        time.sleep(interval)


def run(conn: SerialConnection, state: MotionState, rate_hz: float, logger: StatusLogger | None = None) -> None:
    """20Hz(기본) 주기로 현재 목표 명령을 전송하며 키 입력을 처리하는 메인 루프.

    blocking input() 대신 msvcrt.kbhit()로 폴링하므로 키 입력 대기 중에도
    전송 주기가 유지된다. 매 반복마다 도착한 STATUS Packet도 함께 읽어
    조립하고, 명령 전송 시점에 맞춰 화면을 갱신한다.

    X/E(STOP/ESTOP)는 20Hz 주기를 기다리지 않고 이 자리에서 즉시 1회
    전송한다 — SET_WHEEL_VEL과 달리 반복 전송에 기대지 않는 명시적 정지
    명령이므로, 키를 누른 시점에 바로 나가는 것이 실기 안전 테스트 취지에
    맞는다.

    logger가 주어지면(--log) STATUS Packet이 수신될 때마다(화면 갱신 주기와
    무관하게) CSV에 한 줄씩 기록한다.

    G 키를 누르면 gain_input이 활성화되어, 이후 키 입력은 KeyboardReader.poll()
    (W/A/S/D 등 동작 해석) 대신 KeyboardReader.read_raw()로 읽어 Kp/Ki 숫자
    입력으로 취급한다(blocking 없이, 다른 루프 처리는 그대로 계속됨). Kp/Ki를
    모두 입력하면 SET_PI_GAINS를 1회 전송한다. E는 입력 모드 중에도 예외적으로
    즉시 ESTOP + 입력 취소로 처리한다(요구사항: Gain 입력 중에도 E 사용 가능).
    Ctrl+C는 msvcrt와 무관하게 항상 KeyboardInterrupt로 올라오므로 별도 처리가
    필요 없다.

    '['/']'는 gain_input 모드에 들어가지 않고(즉 G와 별개로 언제든) Kp만
    ±GAIN_KP_STEP 즉시 증감시켜 SET_PI_GAINS를 1회 전송한다. Ki는
    PiGainsState.best_known_ki()로 현재 값을 그대로 실어 보낸다. STM 응답
    처리(PI_GAINS/ERROR)는 G 입력과 동일한 pi_gains(mark_pending/apply_ack/
    apply_error) 경로를 그대로 공유한다.
    """
    period_s = 1.0 / rate_hz
    next_send = time.monotonic()

    gain_input = GainInputState()
    pi_gains = PiGainsState()

    def handle_status_packet(packet: StatusPacket) -> None:
        if logger is not None:
            logger.log(packet, pi_gains.applied_kp, pi_gains.applied_ki)

    receiver = StatusReceiver(
        on_packet=handle_status_packet,
        on_pi_gains_ack=pi_gains.apply_ack,
        on_pi_gains_error=pi_gains.apply_error,
    )
    display = StatusDisplay()

    while True:
        if gain_input.active:
            raw = KeyboardReader.read_raw()
            if raw is not None:
                if raw.lower() == "e":
                    conn.write(build_estop_command().encode("ascii"))
                    state.force_zero("Emergency Stop")
                    gain_input.cancel()
                else:
                    result = gain_input.handle_char(raw)
                    if result is not None:
                        kp, ki = result
                        conn.write(build_set_pi_gains_command(kp, ki).encode("ascii"))
                        pi_gains.mark_pending(kp, ki)
        else:
            event = KeyboardReader.poll()

            if event.quit_requested:
                return

            if event.start_gain_input:
                gain_input.start()
            elif event.protocol_command == "STOP":
                conn.write(build_stop_command().encode("ascii"))
                state.force_zero("Operational Stop")
            elif event.protocol_command == "ESTOP":
                conn.write(build_estop_command().encode("ascii"))
                state.force_zero("Emergency Stop")
            elif event.action is not None:
                state.set_action(event.action)
            elif event.kp_nudge is not None:
                new_kp = pi_gains.best_known_kp() + event.kp_nudge
                new_kp = min(max(new_kp, MOTOR_PI_KP_MIN), MOTOR_PI_KP_MAX)
                new_ki = pi_gains.best_known_ki()  # Ki는 그대로 유지, Kp만 바뀐다
                conn.write(build_set_pi_gains_command(new_kp, new_ki).encode("ascii"))
                pi_gains.mark_pending(new_kp, new_ki)

        receiver.feed(conn.read_available())

        now = time.monotonic()
        if now >= next_send:
            label, left, right = state.snapshot()
            conn.write(build_wheel_vel_command(left, right).encode("ascii"))

            display.render(label, left, right, receiver.latest, gain_input, pi_gains)

            next_send += period_s
            if next_send < now:
                # 루프가 밀렸을 경우(다른 처리 지연 등) 기준 시각을 현재로 재정렬
                next_send = now + period_s

        time.sleep(0.001)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="STM32 모터 제어 보드용 SET_WHEEL_VEL 수동 테스트 도구 (Windows 전용)"
    )
    parser.add_argument("--port", required=True, help="STM32 Virtual COM Port (예: COM6)")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUDRATE, help=f"Baud rate (기본 {DEFAULT_BAUDRATE})")
    parser.add_argument("--rate", type=float, default=DEFAULT_RATE_HZ, help=f"명령 전송 주기 Hz (기본 {DEFAULT_RATE_HZ})")
    parser.add_argument(
        "--speed", type=float, default=DEFAULT_SPEED_RAD_S, help=f"목표 각속도 rad/s (기본 {DEFAULT_SPEED_RAD_S})"
    )
    parser.add_argument(
        "--log", action="store_true", help="STATUS Packet을 CSV로 기록 (logs/날짜_시간.csv, PI 튜닝용)"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if sys.platform != "win32":
        print("[ERROR] 이 도구는 Windows(msvcrt) 전용입니다.", file=sys.stderr)
        return 1

    _enable_windows_ansi()

    args = parse_args(argv)

    conn = SerialConnection(port=args.port, baudrate=args.baud)
    try:
        conn.open()
    except ConnectionError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"연결됨: {args.port} @ {args.baud}bps, {args.rate:.0f}Hz, speed={args.speed:.2f} rad/s")
    print("W:전진 S:후진 A:좌회전 D:우회전 Space:정지(SET_WHEEL_VEL,0,0) Q/Ctrl+C:종료")
    print("X:STOP 명령 전송  E:ESTOP 명령 전송(재부팅 전까지 해제 안 됨, 실기 안전 테스트용)")
    print("G:Kp/Ki 입력 모드(Enter로 필드 확정, Backspace로 수정, SET_PI_GAINS 1회 전송,")
    print("  입력 중에도 E는 즉시 ESTOP+취소로 동작)")
    print("[:Kp -0.05  ]:Kp +0.05  (Ki 유지, 즉시 SET_PI_GAINS 전송, G 없이 바로 사용 가능)")

    state = MotionState(speed_rad_s=args.speed)
    exit_code = 0

    logger: StatusLogger | None = None
    if args.log:
        log_path = make_log_path()
        logger = StatusLogger(log_path)
        print(f"Logging: {log_path}")

    try:
        run(conn, state, rate_hz=args.rate, logger=logger)
    except KeyboardInterrupt:
        pass
    except ConnectionError as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        print("\n종료 중: 정지 명령 전송...")
        safe_stop(conn)
        conn.close()
        if logger is not None:
            logger.close()
        print("포트를 닫았습니다.")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
