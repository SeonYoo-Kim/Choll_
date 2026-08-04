"""STM32 → PC 수신 줄 파싱 — 완성된 한 줄을 타입별로 분류하는 순수 모듈.

책임 분리(8a 기준):

- `SerialLink`      : 포트 I/O와 raw bytes read/write만
- Line Decoder(8b)  : 부분 수신 bytes를 완성된 줄로 조립
- **Packet Parser(이 모듈)** : 완성된 **한 줄**을 타입별로 파싱

따라서 이 모듈에는 pyserial·수신 버퍼·`rclpy`·ROS 메시지가 없다. 입력은 `str` 한 줄,
출력은 `ParsedPacket` 하나뿐이며 전역 상태를 두지 않는다. 하드웨어 없이 pytest로
검증할 수 있다.

STM은 같은 스트림에 STATUS 외의 줄도 섞어 보낸다(프로토콜 정본:
embedded/motor/docs/serial_protocol.md, 송신부: `Application/Communication/status_reporter.c`).
그래서 "STATUS 파싱 실패"와 "애초에 STATUS가 아닌 줄"을 반드시 구분해야 한다 —
전자는 통신/펌웨어 이상 신호이고 후자는 정상 동작이다. `PacketKind`가 그 구분을 담당한다.

파싱 대상 줄 형식::

    STATUS,<LT>,<LA>,<RT>,<RA>,<LPWM>,<RPWM>,<LE>,<RE>
    FAULT,STALL,<LEFT|RIGHT|BOTH>
    FAULT_CLEARED,STALL
    PI_GAINS,<kp>,<ki>
    STALL_RESET,OK
    ERROR,<command>,<reason>

⚠️ STATUS 필드 순서는 **좌우가 아니라 좌(목표/실제) → 우(목표/실제) 교차**다:
`LT, LA, RT, RA`. `target_L, target_R, actual_L, actual_R`가 아니다.

`PI_GAINS`/`STALL_RESET`/`ERROR` 계열은 분류·파싱만 하고, ROS 토픽으로 발행하지 않는다
(로그 처리 대상). 상태 토픽 발행은 8c의 책임이다.
"""

import math
from dataclasses import dataclass
from enum import Enum

# --- 줄 첫 필드(토큰) ---
TOKEN_STATUS = "STATUS"
TOKEN_FAULT = "FAULT"
TOKEN_FAULT_CLEARED = "FAULT_CLEARED"
TOKEN_PI_GAINS = "PI_GAINS"
TOKEN_STALL_RESET = "STALL_RESET"
TOKEN_ERROR = "ERROR"

# --- 필드 개수 (토큰 포함) ---
STATUS_FIELD_COUNT = 9  # STATUS + LT,LA,RT,RA,LPWM,RPWM,LE,RE
FAULT_FIELD_COUNT = 3  # FAULT + STALL + cause
FAULT_CLEARED_FIELD_COUNT = 2  # FAULT_CLEARED + STALL
PI_GAINS_FIELD_COUNT = 3  # PI_GAINS + kp + ki
STALL_RESET_FIELD_COUNT = 2  # STALL_RESET + OK
ERROR_FIELD_COUNT = 3  # ERROR + command + reason

# `FAULT,STALL,...` / `FAULT_CLEARED,STALL` 의 두 번째 필드.
SUBSYSTEM_STALL = "STALL"
# `STALL_RESET,OK` 의 두 번째 필드. 실패는 `ERROR,RESET_STALL,<reason>`으로 오므로
# 프로토콜상 OK 외의 값은 정의되어 있지 않다.
STALL_RESET_OK = "OK"

# --- 와이어 자료형 범위 (프로토콜 정본의 STATUS Packet 필드 표) ---
# ⚠️ 이 값들은 **와이어 자료형**의 범위이지 모터의 실제 동작 범위가 아니다.
# 예를 들어 LPWM/RPWM은 현재 펌웨어에서 사실상 -99~99(`MOTOR_PWM_MAX`)만 나오지만,
# 그 상한을 여기서 검사하면 펌웨어가 `MOTOR_PWM_MAX`를 올렸을 때 파서가 정상 패킷을
# 거부하게 된다. 따라서 int16_t/int32_t로 표현 자체가 불가능한 값만 걸러낸다 —
# 그런 값이 보이면 숫자가 아니라 프레이밍이 깨진 것이다.
INT16_MIN = -32768
INT16_MAX = 32767
INT32_MIN = -2147483648
INT32_MAX = 2147483647

TYPE_NAME_INT16 = "int16_t"
TYPE_NAME_INT32 = "int32_t"


class PacketKind(str, Enum):
    """수신 줄의 분류.

    `MALFORMED`와 `UNKNOWN`을 나눈 것이 핵심이다:

    - `MALFORMED`: 알려진 토큰으로 시작했지만 필드 수/숫자 형식/자료형 범위가 어긋난 줄.
      프레이밍 깨짐이나 펌웨어 변경 신호이므로 **오류로 다뤄야 한다.**
    - `UNKNOWN`: 토큰 자체를 모르는 줄. 펌웨어에 새 메시지가 추가됐거나 부팅 메시지
      같은 것이므로, 조용히 무시해도 되는 정상 상황이다.

    토큰 비교는 대소문자를 구분하므로 `status,...`(소문자)는 `UNKNOWN`이 된다.
    **이것은 "프레이밍 오류"로 판정하는 것이 아니다** — 단지 모르는 줄로 넘긴다는 뜻이며,
    소비자는 `UNKNOWN`을 오류로 집계하지 않는다. STM은 항상 대문자 토큰만 보내므로
    (`status_reporter.c`의 리터럴) 실제로는 발생하지 않는 경우다.
    """

    STATUS = "status"
    FAULT = "fault"
    FAULT_CLEARED = "fault_cleared"
    PI_GAINS = "pi_gains"
    STALL_RESET_ACK = "stall_reset_ack"
    ERROR = "error"
    BLANK = "blank"
    UNKNOWN = "unknown"
    MALFORMED = "malformed"


class StallCause(str, Enum):
    """`FAULT,STALL,<cause>`의 원인. 좌/우 중 어느 바퀴가 막혔는지 구분한다."""

    LEFT = "LEFT"
    RIGHT = "RIGHT"
    BOTH = "BOTH"


@dataclass(frozen=True)
class StatusPacket:
    """STATUS 한 건. 필드 순서는 와이어 순서(`LT,LA,RT,RA,LPWM,RPWM,LE,RE`)와 같다.

    Attributes:
        left_target_rad_s: LT — 왼쪽 목표 각속도 (rad/s).
        left_actual_rad_s: LA — 왼쪽 엔코더 실측 각속도 (rad/s).
        right_target_rad_s: RT — 오른쪽 목표 각속도 (rad/s).
        right_actual_rad_s: RA — 오른쪽 엔코더 실측 각속도 (rad/s).
        left_pwm: LPWM — 왼쪽 PWM. **부호 있는 정수**(양수=전진 채널, 음수=후진 채널).
            와이어 자료형은 `int16_t`이며 파서는 그 범위만 검사한다. 현재 펌웨어에서
            실제로 나오는 값은 `-99~99`지만 그 상한은 검사하지 않는다.
        right_pwm: RPWM — 오른쪽 PWM. 부호 규칙·범위 규칙 동일.
        left_encoder_total: LE — 왼쪽 누적 엔코더 카운트. 와이어 자료형 `int32_t`.
        right_encoder_total: RE — 오른쪽 누적 엔코더 카운트. 와이어 자료형 `int32_t`.
    """

    left_target_rad_s: float
    left_actual_rad_s: float
    right_target_rad_s: float
    right_actual_rad_s: float
    left_pwm: int
    right_pwm: int
    left_encoder_total: int
    right_encoder_total: int


@dataclass(frozen=True)
class FaultPacket:
    """`FAULT,STALL,<cause>` — Stall Fault 확정 알림.

    Attributes:
        cause: 막힌 바퀴(LEFT/RIGHT/BOTH).
    """

    cause: StallCause


@dataclass(frozen=True)
class PiGainsPacket:
    """`PI_GAINS,<kp>,<ki>` — `SET_PI_GAINS` 적용 확인 응답.

    Attributes:
        kp: 실제로 적용된 Proportional 게인.
        ki: 실제로 적용된 Integral 게인.
    """

    kp: float
    ki: float


@dataclass(frozen=True)
class ErrorPacket:
    """`ERROR,<command>,<reason>` — 명령 거부 응답.

    Attributes:
        command: 거부된 명령 이름 (예: `SET_PI_GAINS`, `RESET_STALL`).
        reason: 거부 사유 (예: `OUT_OF_RANGE`, `ESTOP_ACTIVE`).
    """

    command: str
    reason: str


# ParsedPacket.payload에 들어갈 수 있는 타입.
Payload = StatusPacket | FaultPacket | PiGainsPacket | ErrorPacket | None


@dataclass(frozen=True)
class ParsedPacket:
    """`parse_packet()`의 결과. 분류 결과와 (있으면) 해석된 내용을 함께 담는다.

    Attributes:
        kind: 줄의 분류.
        raw: 양쪽 공백/CRLF를 제거한 원본 줄. 로그로 남길 때 쓴다.
        payload: 해석된 내용. `kind`에 따라 타입이 정해지며, 내용이 없는 분류
            (`FAULT_CLEARED`/`STALL_RESET_ACK`/`BLANK`/`UNKNOWN`/`MALFORMED`)에서는 None.
        token: 줄의 첫 필드. `UNKNOWN`/`MALFORMED`에서 무엇을 받았는지 알려준다.
        reason: `MALFORMED`인 이유. 그 외에는 빈 문자열.
    """

    kind: PacketKind
    raw: str
    payload: Payload = None
    token: str = ""
    reason: str = ""


def _malformed(raw: str, token: str, reason: str) -> ParsedPacket:
    """Build a MALFORMED result.

    Args:
        raw: 정리된 원본 줄.
        token: 줄의 첫 필드.
        reason: 어긋난 이유.

    Returns:
        `kind=MALFORMED`인 결과.
    """
    return ParsedPacket(
        kind=PacketKind.MALFORMED, raw=raw, token=token, reason=reason
    )


def _parse_finite_float(text: str, field_name: str) -> float:
    """Parse a float and reject NaN/Infinity.

    NaN/Infinity를 그대로 통과시키면 이후 제어·발행 계산이 조용히 오염된다.
    `float()`은 `"nan"`/`"inf"`를 정상 파싱하므로 유한성 검사가 반드시 필요하다.

    Args:
        text: 숫자 문자열.
        field_name: 오류 메시지에 쓸 필드 이름.

    Returns:
        파싱된 유한 실수.

    Raises:
        ValueError: 숫자로 변환할 수 없거나 유한하지 않을 때.
    """
    try:
        value = float(text)
    except ValueError as error:
        raise ValueError(f"{field_name}: invalid number {text!r}") from error
    if not math.isfinite(value):
        raise ValueError(f"{field_name}: value is not finite ({text!r})")
    return value


def _parse_int(
    text: str,
    field_name: str,
    *,
    minimum: int,
    maximum: int,
    type_name: str,
) -> int:
    """Parse a signed integer and check it fits the wire type.

    PWM과 엔코더 누적값은 부호 있는 정수다. `"36.5"`처럼 실수 형식이면 거부한다 —
    STM은 이 필드를 `%d`/`%ld`로 보내므로 소수점이 보이면 프레이밍이 깨진 것이다.

    범위 검사는 **와이어 자료형**(`int16_t`/`int32_t`) 기준이다. 모터의 실제 동작
    범위(`MOTOR_PWM_MAX` 등)는 검사하지 않는다 — 펌웨어가 그 상한을 올려도 파서가
    정상 패킷을 거부하지 않아야 한다.

    Args:
        text: 정수 문자열.
        field_name: 오류 메시지에 쓸 필드 이름.
        minimum: 허용 최솟값(포함).
        maximum: 허용 최댓값(포함).
        type_name: 오류 메시지에 쓸 와이어 자료형 이름.

    Returns:
        파싱된 정수.

    Raises:
        ValueError: 정수로 변환할 수 없거나 자료형 범위를 벗어날 때.
    """
    try:
        value = int(text)
    except ValueError as error:
        raise ValueError(f"{field_name}: invalid integer {text!r}") from error
    if value < minimum or value > maximum:
        raise ValueError(
            f"{field_name}: {type_name} out of range ({value}, "
            f"allowed {minimum}..{maximum})"
        )
    return value


def _parse_status(raw: str, fields: list[str]) -> ParsedPacket:
    """Parse a STATUS line into a StatusPacket.

    Args:
        raw: 정리된 원본 줄.
        fields: 콤마로 분리된 필드(첫 요소는 토큰).

    Returns:
        `kind=STATUS`인 결과, 또는 형식이 어긋나면 `kind=MALFORMED`.
    """
    if len(fields) != STATUS_FIELD_COUNT:
        return _malformed(
            raw,
            TOKEN_STATUS,
            f"field count {len(fields)} != {STATUS_FIELD_COUNT}",
        )

    try:
        # 와이어 순서 그대로: LT, LA, RT, RA, LPWM, RPWM, LE, RE
        status = StatusPacket(
            left_target_rad_s=_parse_finite_float(fields[1], "LT"),
            left_actual_rad_s=_parse_finite_float(fields[2], "LA"),
            right_target_rad_s=_parse_finite_float(fields[3], "RT"),
            right_actual_rad_s=_parse_finite_float(fields[4], "RA"),
            left_pwm=_parse_int(
                fields[5],
                "LPWM",
                minimum=INT16_MIN,
                maximum=INT16_MAX,
                type_name=TYPE_NAME_INT16,
            ),
            right_pwm=_parse_int(
                fields[6],
                "RPWM",
                minimum=INT16_MIN,
                maximum=INT16_MAX,
                type_name=TYPE_NAME_INT16,
            ),
            left_encoder_total=_parse_int(
                fields[7],
                "LE",
                minimum=INT32_MIN,
                maximum=INT32_MAX,
                type_name=TYPE_NAME_INT32,
            ),
            right_encoder_total=_parse_int(
                fields[8],
                "RE",
                minimum=INT32_MIN,
                maximum=INT32_MAX,
                type_name=TYPE_NAME_INT32,
            ),
        )
    except ValueError as error:
        return _malformed(raw, TOKEN_STATUS, str(error))

    return ParsedPacket(kind=PacketKind.STATUS, raw=raw, payload=status)


def _parse_fault(raw: str, fields: list[str]) -> ParsedPacket:
    """Parse a `FAULT,STALL,<cause>` line.

    Args:
        raw: 정리된 원본 줄.
        fields: 콤마로 분리된 필드.

    Returns:
        `kind=FAULT`인 결과, 또는 `kind=MALFORMED`.
    """
    if len(fields) != FAULT_FIELD_COUNT:
        return _malformed(
            raw, TOKEN_FAULT, f"field count {len(fields)} != {FAULT_FIELD_COUNT}"
        )
    if fields[1] != SUBSYSTEM_STALL:
        return _malformed(raw, TOKEN_FAULT, f"unknown subsystem {fields[1]!r}")
    try:
        cause = StallCause(fields[2])
    except ValueError:
        return _malformed(raw, TOKEN_FAULT, f"unknown stall cause {fields[2]!r}")

    return ParsedPacket(
        kind=PacketKind.FAULT, raw=raw, payload=FaultPacket(cause=cause)
    )


def _parse_fault_cleared(raw: str, fields: list[str]) -> ParsedPacket:
    """Parse a `FAULT_CLEARED,STALL` line.

    Args:
        raw: 정리된 원본 줄.
        fields: 콤마로 분리된 필드.

    Returns:
        `kind=FAULT_CLEARED`인 결과, 또는 `kind=MALFORMED`. 내용이 없어 payload는 None.
    """
    if len(fields) != FAULT_CLEARED_FIELD_COUNT:
        return _malformed(
            raw,
            TOKEN_FAULT_CLEARED,
            f"field count {len(fields)} != {FAULT_CLEARED_FIELD_COUNT}",
        )
    if fields[1] != SUBSYSTEM_STALL:
        return _malformed(
            raw, TOKEN_FAULT_CLEARED, f"unknown subsystem {fields[1]!r}"
        )
    return ParsedPacket(kind=PacketKind.FAULT_CLEARED, raw=raw)


def _parse_pi_gains(raw: str, fields: list[str]) -> ParsedPacket:
    """Parse a `PI_GAINS,<kp>,<ki>` line.

    Args:
        raw: 정리된 원본 줄.
        fields: 콤마로 분리된 필드.

    Returns:
        `kind=PI_GAINS`인 결과, 또는 `kind=MALFORMED`.
    """
    if len(fields) != PI_GAINS_FIELD_COUNT:
        return _malformed(
            raw,
            TOKEN_PI_GAINS,
            f"field count {len(fields)} != {PI_GAINS_FIELD_COUNT}",
        )
    try:
        gains = PiGainsPacket(
            kp=_parse_finite_float(fields[1], "kp"),
            ki=_parse_finite_float(fields[2], "ki"),
        )
    except ValueError as error:
        return _malformed(raw, TOKEN_PI_GAINS, str(error))

    return ParsedPacket(kind=PacketKind.PI_GAINS, raw=raw, payload=gains)


def _parse_stall_reset(raw: str, fields: list[str]) -> ParsedPacket:
    """Parse a `STALL_RESET,OK` line.

    Args:
        raw: 정리된 원본 줄.
        fields: 콤마로 분리된 필드.

    Returns:
        `kind=STALL_RESET_ACK`인 결과, 또는 `kind=MALFORMED`. payload는 None.
    """
    if len(fields) != STALL_RESET_FIELD_COUNT:
        return _malformed(
            raw,
            TOKEN_STALL_RESET,
            f"field count {len(fields)} != {STALL_RESET_FIELD_COUNT}",
        )
    if fields[1] != STALL_RESET_OK:
        return _malformed(raw, TOKEN_STALL_RESET, f"unexpected result {fields[1]!r}")
    return ParsedPacket(kind=PacketKind.STALL_RESET_ACK, raw=raw)


def _parse_error(raw: str, fields: list[str]) -> ParsedPacket:
    """Parse an `ERROR,<command>,<reason>` line.

    Args:
        raw: 정리된 원본 줄.
        fields: 콤마로 분리된 필드.

    Returns:
        `kind=ERROR`인 결과, 또는 `kind=MALFORMED`.
    """
    if len(fields) != ERROR_FIELD_COUNT:
        return _malformed(
            raw, TOKEN_ERROR, f"field count {len(fields)} != {ERROR_FIELD_COUNT}"
        )
    if not fields[1] or not fields[2]:
        return _malformed(raw, TOKEN_ERROR, "empty command or reason")

    return ParsedPacket(
        kind=PacketKind.ERROR,
        raw=raw,
        payload=ErrorPacket(command=fields[1], reason=fields[2]),
    )


def parse_packet(line: str) -> ParsedPacket:
    """Classify and parse one complete line received from the STM32.

    줄 조립은 하지 않는다 — 호출자(8b의 Line Decoder)가 완성된 한 줄을 넘겨야 한다.
    양쪽 공백과 CRLF는 여기서 제거하므로 종단 문자가 남아 있어도 된다.

    어떤 입력에도 예외를 던지지 않는다. 실패는 `PacketKind.MALFORMED`(알려진 토큰인데
    필드 수·숫자 형식·자료형 범위가 어긋남) 또는 `PacketKind.UNKNOWN`(모르는 토큰)으로
    표현된다 — 수신 루프가 한 줄 때문에 죽지 않게 하기 위함이다. 두 분류의 의미 차이는
    `PacketKind` docstring 참고(소문자 토큰이 `UNKNOWN`인 것은 오류 판정이 아니다).

    Args:
        line: STM32에서 받은 한 줄. CRLF 종단을 포함해도 된다.

    Returns:
        분류 결과와 해석된 내용을 담은 `ParsedPacket`.

    Raises:
        TypeError: `line`이 str이 아닐 때. 호출 규약 위반이므로 조용히 넘기지 않는다.
    """
    if not isinstance(line, str):
        raise TypeError(f"line must be str, got {type(line).__name__}")

    raw = line.strip()
    if not raw:
        return ParsedPacket(kind=PacketKind.BLANK, raw=raw)

    fields = raw.split(",")
    token = fields[0]

    if token == TOKEN_STATUS:
        return _parse_status(raw, fields)
    if token == TOKEN_FAULT:
        return _parse_fault(raw, fields)
    if token == TOKEN_FAULT_CLEARED:
        return _parse_fault_cleared(raw, fields)
    if token == TOKEN_PI_GAINS:
        return _parse_pi_gains(raw, fields)
    if token == TOKEN_STALL_RESET:
        return _parse_stall_reset(raw, fields)
    if token == TOKEN_ERROR:
        return _parse_error(raw, fields)

    return ParsedPacket(kind=PacketKind.UNKNOWN, raw=raw, token=token)
