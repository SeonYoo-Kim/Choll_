"""parse_packet()의 STM32 수신 줄 분류·파싱 단위 테스트.

ROS 실행 환경·시리얼·하드웨어 없이 돌아간다(순수 함수 대상).

실행::

    cd ros2_ws
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 -m pytest src/stm_serial_bridge/test/test_packet_parser.py -v
"""

import pytest

from stm_serial_bridge.packet_parser import (
    ErrorPacket,
    FaultPacket,
    PacketKind,
    PiGainsPacket,
    StallCause,
    StatusPacket,
    parse_packet,
)

# 프로토콜 문서의 예시 줄 (embedded/motor/docs/serial_protocol.md STATUS Packet 절).
DOC_STATUS_LINE = "STATUS,2.00,1.95,2.00,1.97,36,37,15231,15188"


# ---------------------------------------------------------------------------
# STATUS — 정상
# ---------------------------------------------------------------------------


def test_status_from_protocol_doc_example() -> None:
    """문서 예시 줄이 그대로 파싱된다."""
    packet = parse_packet(DOC_STATUS_LINE)

    assert packet.kind is PacketKind.STATUS
    assert packet.payload == StatusPacket(
        left_target_rad_s=2.00,
        left_actual_rad_s=1.95,
        right_target_rad_s=2.00,
        right_actual_rad_s=1.97,
        left_pwm=36,
        right_pwm=37,
        left_encoder_total=15231,
        right_encoder_total=15188,
    )


def test_status_field_order_is_lt_la_rt_ra() -> None:
    """★ 필드 순서가 LT,LA,RT,RA(좌 목표/좌 실제/우 목표/우 실제)임을 고정한다.

    `target_L,target_R,actual_L,actual_R`로 잘못 읽으면 이 테스트가 실패한다.
    8개 값을 모두 다르게 주어 자리 바뀜을 반드시 잡아낸다.
    """
    packet = parse_packet("STATUS,1.0,2.0,3.0,4.0,5,6,7,8")

    status = packet.payload
    assert isinstance(status, StatusPacket)
    assert status.left_target_rad_s == pytest.approx(1.0)
    assert status.left_actual_rad_s == pytest.approx(2.0)
    assert status.right_target_rad_s == pytest.approx(3.0)
    assert status.right_actual_rad_s == pytest.approx(4.0)
    assert status.left_pwm == 5
    assert status.right_pwm == 6
    assert status.left_encoder_total == 7
    assert status.right_encoder_total == 8


def test_status_accepts_crlf_terminated_line() -> None:
    """CRLF 종단이 남아 있어도 파싱된다(호출자가 벗기지 않아도 됨)."""
    packet = parse_packet(DOC_STATUS_LINE + "\r\n")

    assert packet.kind is PacketKind.STATUS
    assert packet.raw == DOC_STATUS_LINE


def test_status_accepts_negative_values() -> None:
    """후진·역회전 상황의 음수 값이 정상 처리된다."""
    packet = parse_packet("STATUS,-2.00,-1.95,-2.00,-1.97,-36,-37,-15231,-15188")

    status = packet.payload
    assert isinstance(status, StatusPacket)
    assert status.left_target_rad_s == pytest.approx(-2.00)
    assert status.left_pwm == -36
    assert status.right_pwm == -37
    assert status.left_encoder_total == -15231
    assert status.right_encoder_total == -15188


def test_status_accepts_all_zero_stop_frame() -> None:
    """정지 상태(전부 0) 프레임도 정상 파싱된다."""
    packet = parse_packet("STATUS,0.00,0.00,0.00,0.00,0,0,0,0")

    status = packet.payload
    assert isinstance(status, StatusPacket)
    assert status.left_target_rad_s == pytest.approx(0.0)
    assert status.left_pwm == 0
    assert status.right_encoder_total == 0


def test_status_accepts_documented_extreme_values() -> None:
    """문서의 최악 길이 예시(버퍼 계산 근거) 값이 파싱된다.

    PWM ±99, 엔코더 int32 최솟값까지 다룰 수 있어야 한다.
    """
    packet = parse_packet(
        "STATUS,-999.99,-999.99,-999.99,-999.99,-99,-99,-2147483648,-2147483648"
    )

    status = packet.payload
    assert isinstance(status, StatusPacket)
    assert status.left_pwm == -99
    assert status.left_encoder_total == -2147483648
    assert status.right_encoder_total == -2147483648


def test_status_accepts_int32_max_encoder() -> None:
    """엔코더 int32 최댓값도 파싱된다(오버플로 직전 경계)."""
    packet = parse_packet("STATUS,0.0,0.0,0.0,0.0,0,0,2147483647,2147483647")

    status = packet.payload
    assert isinstance(status, StatusPacket)
    assert status.left_encoder_total == 2147483647


# ---------------------------------------------------------------------------
# STATUS — 와이어 자료형 범위 (LPWM/RPWM: int16_t, LE/RE: int32_t)
#
# 검사 대상은 **와이어 자료형** 범위뿐이다. 모터의 실제 PWM 범위(-99~99,
# `MOTOR_PWM_MAX`)는 검사하지 않는다 — 펌웨어가 그 상한을 올려도 파서가 정상 패킷을
# 거부해서는 안 되기 때문이다.
# ---------------------------------------------------------------------------


def _status_line_with_pwm(left_pwm: str) -> str:
    """LPWM 자리에 임의 문자열을 넣은 STATUS 줄을 만든다."""
    return f"STATUS,1.0,2.0,3.0,4.0,{left_pwm},6,7,8"


def _status_line_with_encoder(left_encoder: str) -> str:
    """LE 자리에 임의 문자열을 넣은 STATUS 줄을 만든다."""
    return f"STATUS,1.0,2.0,3.0,4.0,5,6,{left_encoder},8"


@pytest.mark.parametrize("pwm", [-32768, 32767])
def test_pwm_int16_boundary_values_are_accepted(pwm: int) -> None:
    """int16_t 경계값(-32768 / 32767)은 성공한다."""
    packet = parse_packet(_status_line_with_pwm(str(pwm)))

    assert packet.kind is PacketKind.STATUS
    status = packet.payload
    assert isinstance(status, StatusPacket)
    assert status.left_pwm == pwm


@pytest.mark.parametrize("pwm", [-32769, 32768])
def test_pwm_outside_int16_is_malformed(pwm: int) -> None:
    """int16_t 범위를 벗어난 PWM(-32769 / 32768)은 MALFORMED다."""
    packet = parse_packet(_status_line_with_pwm(str(pwm)))

    assert packet.kind is PacketKind.MALFORMED
    assert packet.token == "STATUS"
    assert "LPWM" in packet.reason
    assert "int16_t out of range" in packet.reason
    assert packet.payload is None


@pytest.mark.parametrize("encoder", [-2147483648, 2147483647])
def test_encoder_int32_boundary_values_are_accepted(encoder: int) -> None:
    """int32_t 경계값(-2147483648 / 2147483647)은 성공한다."""
    packet = parse_packet(_status_line_with_encoder(str(encoder)))

    assert packet.kind is PacketKind.STATUS
    status = packet.payload
    assert isinstance(status, StatusPacket)
    assert status.left_encoder_total == encoder


@pytest.mark.parametrize("encoder", [-2147483649, 2147483648])
def test_encoder_outside_int32_is_malformed(encoder: int) -> None:
    """int32_t 범위를 벗어난 엔코더(-2147483649 / 2147483648)는 MALFORMED다."""
    packet = parse_packet(_status_line_with_encoder(str(encoder)))

    assert packet.kind is PacketKind.MALFORMED
    assert packet.token == "STATUS"
    assert "LE" in packet.reason
    assert "int32_t out of range" in packet.reason
    assert packet.payload is None


def test_range_check_applies_to_right_side_fields_too() -> None:
    """RPWM/RE에도 같은 범위 검사가 적용된다(왼쪽만 검사하는 실수 방지)."""
    right_pwm = parse_packet("STATUS,1.0,2.0,3.0,4.0,5,32768,7,8")
    assert right_pwm.kind is PacketKind.MALFORMED
    assert "RPWM" in right_pwm.reason
    assert "int16_t out of range" in right_pwm.reason

    right_encoder = parse_packet("STATUS,1.0,2.0,3.0,4.0,5,6,7,2147483648")
    assert right_encoder.kind is PacketKind.MALFORMED
    assert "RE" in right_encoder.reason
    assert "int32_t out of range" in right_encoder.reason


def test_pwm_range_is_int16_not_motor_pwm_max() -> None:
    """★ 모터 실동작 범위(-99~99)를 검사하지 않는다는 정책을 고정한다.

    펌웨어가 `MOTOR_PWM_MAX`를 올렸을 때 파서가 정상 패킷을 거부하면 안 되므로,
    100·1000처럼 현재는 나오지 않는 값도 int16_t 안이면 성공해야 한다.
    """
    for pwm in (100, -100, 1000, -1000, 30000):
        packet = parse_packet(_status_line_with_pwm(str(pwm)))

        assert packet.kind is PacketKind.STATUS, pwm
        status = packet.payload
        assert isinstance(status, StatusPacket)
        assert status.left_pwm == pwm


def test_encoder_range_is_int32_not_int16() -> None:
    """엔코더는 int32_t이므로 int16_t를 넘는 값(예: 15231, 100000)도 정상이다."""
    for encoder in (15231, 100000, -100000):
        packet = parse_packet(_status_line_with_encoder(str(encoder)))

        assert packet.kind is PacketKind.STATUS, encoder
        status = packet.payload
        assert isinstance(status, StatusPacket)
        assert status.left_encoder_total == encoder


def test_status_payload_is_immutable() -> None:
    """StatusPacket은 frozen dataclass다 — 수신값이 나중에 조용히 바뀌지 않는다."""
    packet = parse_packet(DOC_STATUS_LINE)

    with pytest.raises(Exception):  # noqa: B017, PT011 - FrozenInstanceError
        packet.payload.left_pwm = 0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# STATUS — 형식 오류 (MALFORMED)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "STATUS",
        "STATUS,1.0",
        "STATUS,1.0,2.0,3.0,4.0,5,6,7",  # 8개 (1개 부족)
        "STATUS,1.0,2.0,3.0,4.0,5,6,7,8,9",  # 10개 (1개 초과)
    ],
)
def test_status_with_wrong_field_count_is_malformed(line: str) -> None:
    """필드 개수가 9가 아니면 MALFORMED이고 이유에 field count가 담긴다."""
    packet = parse_packet(line)

    assert packet.kind is PacketKind.MALFORMED
    assert packet.token == "STATUS"
    assert "field count" in packet.reason
    assert packet.payload is None


@pytest.mark.parametrize(
    ("line", "field_name"),
    [
        ("STATUS,abc,2.0,3.0,4.0,5,6,7,8", "LT"),
        ("STATUS,1.0,,3.0,4.0,5,6,7,8", "LA"),
        ("STATUS,1.0,2.0,x,4.0,5,6,7,8", "RT"),
        ("STATUS,1.0,2.0,3.0,--4,5,6,7,8", "RA"),
    ],
)
def test_status_with_invalid_float_is_malformed(line: str, field_name: str) -> None:
    """실수 필드를 숫자로 바꿀 수 없으면 MALFORMED이고 어느 필드인지 알려준다."""
    packet = parse_packet(line)

    assert packet.kind is PacketKind.MALFORMED
    assert packet.token == "STATUS"
    assert field_name in packet.reason
    assert "invalid number" in packet.reason


@pytest.mark.parametrize(
    ("line", "field_name"),
    [
        ("STATUS,1.0,2.0,3.0,4.0,abc,6,7,8", "LPWM"),
        ("STATUS,1.0,2.0,3.0,4.0,5,,7,8", "RPWM"),
        ("STATUS,1.0,2.0,3.0,4.0,5,6,1.5,8", "LE"),  # 실수 형식 정수 필드
        ("STATUS,1.0,2.0,3.0,4.0,5,6,7,36.5", "RE"),
    ],
)
def test_status_with_invalid_integer_is_malformed(line: str, field_name: str) -> None:
    """정수 필드(PWM/엔코더)에 실수·문자가 오면 MALFORMED다.

    STM은 이 필드를 `%d`/`%ld`로 보내므로 소수점이 보이면 프레이밍이 깨진 것이다.
    """
    packet = parse_packet(line)

    assert packet.kind is PacketKind.MALFORMED
    assert packet.token == "STATUS"
    assert field_name in packet.reason
    assert "invalid integer" in packet.reason


@pytest.mark.parametrize(
    "value", ["nan", "NaN", "inf", "-inf", "Infinity", "-Infinity"]
)
def test_status_with_non_finite_float_is_malformed(value: str) -> None:
    """NaN/Infinity는 거부한다 — float()이 정상 파싱해 버리므로 명시적 검사가 필요하다."""
    packet = parse_packet(f"STATUS,{value},2.0,3.0,4.0,5,6,7,8")

    assert packet.kind is PacketKind.MALFORMED
    assert packet.token == "STATUS"
    assert "not finite" in packet.reason


def test_status_non_finite_in_each_float_field_is_rejected() -> None:
    """네 개의 실수 필드 전부에서 NaN이 거부된다(한 자리만 검사하는 실수 방지)."""
    for index, field_name in enumerate(("LT", "LA", "RT", "RA")):
        fields = ["1.0", "2.0", "3.0", "4.0"]
        fields[index] = "nan"
        line = "STATUS," + ",".join(fields) + ",5,6,7,8"

        packet = parse_packet(line)

        assert packet.kind is PacketKind.MALFORMED, field_name
        assert field_name in packet.reason
        assert "not finite" in packet.reason


# ---------------------------------------------------------------------------
# FAULT / FAULT_CLEARED
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cause_text", "expected"),
    [
        ("LEFT", StallCause.LEFT),
        ("RIGHT", StallCause.RIGHT),
        ("BOTH", StallCause.BOTH),
    ],
)
def test_fault_stall_causes(cause_text: str, expected: StallCause) -> None:
    """FAULT,STALL,<LEFT|RIGHT|BOTH> 세 원인이 모두 분류된다."""
    packet = parse_packet(f"FAULT,STALL,{cause_text}")

    assert packet.kind is PacketKind.FAULT
    assert packet.payload == FaultPacket(cause=expected)


def test_fault_with_unknown_cause_is_malformed() -> None:
    """정의되지 않은 원인은 MALFORMED다(조용히 무시하지 않는다)."""
    packet = parse_packet("FAULT,STALL,SIDEWAYS")

    assert packet.kind is PacketKind.MALFORMED
    assert packet.token == "FAULT"
    assert "unknown stall cause" in packet.reason


def test_fault_with_unknown_subsystem_is_malformed() -> None:
    """STALL 외의 subsystem은 아직 정의되지 않았으므로 MALFORMED다."""
    packet = parse_packet("FAULT,OVERHEAT,LEFT")

    assert packet.kind is PacketKind.MALFORMED
    assert packet.token == "FAULT"
    assert "unknown subsystem" in packet.reason


@pytest.mark.parametrize("line", ["FAULT", "FAULT,STALL", "FAULT,STALL,LEFT,EXTRA"])
def test_fault_with_wrong_field_count_is_malformed(line: str) -> None:
    """FAULT 필드 개수가 3이 아니면 MALFORMED다."""
    packet = parse_packet(line)

    assert packet.kind is PacketKind.MALFORMED
    assert packet.token == "FAULT"
    assert "field count" in packet.reason


def test_fault_cleared_stall() -> None:
    """FAULT_CLEARED,STALL은 내용이 없는 분류다(payload None)."""
    packet = parse_packet("FAULT_CLEARED,STALL")

    assert packet.kind is PacketKind.FAULT_CLEARED
    assert packet.payload is None
    assert packet.raw == "FAULT_CLEARED,STALL"


@pytest.mark.parametrize(
    "line", ["FAULT_CLEARED", "FAULT_CLEARED,STALL,LEFT", "FAULT_CLEARED,OVERHEAT"]
)
def test_fault_cleared_malformed(line: str) -> None:
    """FAULT_CLEARED 형식이 어긋나면 MALFORMED다."""
    packet = parse_packet(line)

    assert packet.kind is PacketKind.MALFORMED
    assert packet.token == "FAULT_CLEARED"


def test_fault_and_fault_cleared_tokens_are_not_confused() -> None:
    """`FAULT`와 `FAULT_CLEARED`는 접두사가 겹치지만 서로 다른 분류로 처리된다."""
    assert parse_packet("FAULT,STALL,LEFT").kind is PacketKind.FAULT
    assert parse_packet("FAULT_CLEARED,STALL").kind is PacketKind.FAULT_CLEARED


# ---------------------------------------------------------------------------
# PI_GAINS
# ---------------------------------------------------------------------------


def test_pi_gains_ack() -> None:
    """PI_GAINS,<kp>,<ki>가 파싱된다(문서 예시: 소수점 4자리)."""
    packet = parse_packet("PI_GAINS,0.5000,0.0000")

    assert packet.kind is PacketKind.PI_GAINS
    assert packet.payload == PiGainsPacket(kp=0.5, ki=0.0)


@pytest.mark.parametrize("line", ["PI_GAINS", "PI_GAINS,0.5", "PI_GAINS,0.5,0.0,0.1"])
def test_pi_gains_wrong_field_count_is_malformed(line: str) -> None:
    """PI_GAINS 필드 개수가 3이 아니면 MALFORMED다."""
    packet = parse_packet(line)

    assert packet.kind is PacketKind.MALFORMED
    assert packet.token == "PI_GAINS"
    assert "field count" in packet.reason


@pytest.mark.parametrize("line", ["PI_GAINS,abc,0.0", "PI_GAINS,0.5,nan"])
def test_pi_gains_invalid_number_is_malformed(line: str) -> None:
    """PI_GAINS의 숫자 오류·NaN도 MALFORMED다."""
    packet = parse_packet(line)

    assert packet.kind is PacketKind.MALFORMED
    assert packet.token == "PI_GAINS"


# ---------------------------------------------------------------------------
# STALL_RESET / ERROR
# ---------------------------------------------------------------------------


def test_stall_reset_ack() -> None:
    """STALL_RESET,OK은 내용이 없는 분류다(payload None)."""
    packet = parse_packet("STALL_RESET,OK")

    assert packet.kind is PacketKind.STALL_RESET_ACK
    assert packet.payload is None


@pytest.mark.parametrize("line", ["STALL_RESET", "STALL_RESET,FAIL", "STALL_RESET,OK,X"])
def test_stall_reset_malformed(line: str) -> None:
    """STALL_RESET,OK 외의 형식은 MALFORMED다(실패는 ERROR 줄로 온다)."""
    packet = parse_packet(line)

    assert packet.kind is PacketKind.MALFORMED
    assert packet.token == "STALL_RESET"


@pytest.mark.parametrize(
    ("line", "command", "reason"),
    [
        ("ERROR,SET_PI_GAINS,INVALID_FORMAT", "SET_PI_GAINS", "INVALID_FORMAT"),
        ("ERROR,SET_PI_GAINS,OUT_OF_RANGE", "SET_PI_GAINS", "OUT_OF_RANGE"),
        ("ERROR,RESET_STALL,ESTOP_ACTIVE", "RESET_STALL", "ESTOP_ACTIVE"),
        ("ERROR,RESET_STALL,LATCHED_SAFE_ACTIVE", "RESET_STALL", "LATCHED_SAFE_ACTIVE"),
        ("ERROR,RESET_STALL,NO_STALL", "RESET_STALL", "NO_STALL"),
    ],
)
def test_error_responses(line: str, command: str, reason: str) -> None:
    """문서에 정의된 ERROR 응답 5종이 command/reason으로 분해된다."""
    packet = parse_packet(line)

    assert packet.kind is PacketKind.ERROR
    assert packet.payload == ErrorPacket(command=command, reason=reason)


def test_error_accepts_unknown_command_and_reason() -> None:
    """모르는 command/reason도 ERROR로 분류한다 — 펌웨어가 새 사유를 추가할 수 있다."""
    packet = parse_packet("ERROR,FUTURE_COMMAND,FUTURE_REASON")

    assert packet.kind is PacketKind.ERROR
    assert packet.payload == ErrorPacket(
        command="FUTURE_COMMAND", reason="FUTURE_REASON"
    )


@pytest.mark.parametrize(
    "line", ["ERROR", "ERROR,SET_PI_GAINS", "ERROR,SET_PI_GAINS,A,B"]
)
def test_error_wrong_field_count_is_malformed(line: str) -> None:
    """ERROR 필드 개수가 3이 아니면 MALFORMED다."""
    packet = parse_packet(line)

    assert packet.kind is PacketKind.MALFORMED
    assert packet.token == "ERROR"
    assert "field count" in packet.reason


@pytest.mark.parametrize("line", ["ERROR,,INVALID_FORMAT", "ERROR,SET_PI_GAINS,"])
def test_error_with_empty_field_is_malformed(line: str) -> None:
    """command나 reason이 비어 있으면 MALFORMED다."""
    packet = parse_packet(line)

    assert packet.kind is PacketKind.MALFORMED
    assert packet.token == "ERROR"
    assert "empty command or reason" in packet.reason


# ---------------------------------------------------------------------------
# BLANK / UNKNOWN / 호출 규약
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("line", ["", "   ", "\r\n", "\n", "\t", "  \r\n  "])
def test_blank_lines(line: str) -> None:
    """빈 줄·공백뿐인 줄은 BLANK다(오류가 아니다)."""
    packet = parse_packet(line)

    assert packet.kind is PacketKind.BLANK
    assert packet.payload is None
    assert packet.raw == ""


@pytest.mark.parametrize(
    "line",
    [
        "PONG",
        "SET_WHEEL_VEL,1.0,2.0",  # PC->STM 명령이 되돌아온 경우(에코 등)
        "Booting...",
        "STATUSX,1,2",
        "0",
    ],
)
def test_unknown_tokens(line: str) -> None:
    """모르는 토큰은 UNKNOWN이며 받은 토큰을 그대로 알려준다."""
    packet = parse_packet(line)

    assert packet.kind is PacketKind.UNKNOWN
    assert packet.payload is None
    assert packet.token == line.strip().split(",")[0]


@pytest.mark.parametrize(
    "line",
    [
        "status,1.0,2.0,3.0,4.0,5,6,7,8",
        "Status,1.0,2.0,3.0,4.0,5,6,7,8",
        "fault,STALL,LEFT",
        "pi_gains,0.5,0.0",
    ],
)
def test_lowercase_tokens_are_unknown_not_malformed(line: str) -> None:
    """소문자·혼합 대소문자 토큰은 UNKNOWN이다 — **MALFORMED가 아니다.**

    토큰 비교는 대소문자를 구분하므로 이런 줄은 "모르는 줄"로 넘어간다. 이는
    프레이밍 오류 판정이 아니며, 소비자는 오류로 집계하지 않아야 한다. STM은 항상
    대문자 토큰만 보내므로(`status_reporter.c`의 리터럴) 실제로는 발생하지 않는다.
    """
    packet = parse_packet(line)

    assert packet.kind is PacketKind.UNKNOWN
    assert packet.kind is not PacketKind.MALFORMED
    assert packet.reason == ""  # 오류 사유가 붙지 않는다
    assert packet.payload is None


def test_unknown_is_distinguishable_from_malformed() -> None:
    """★ "STATUS 파싱 실패"와 "애초에 STATUS가 아닌 줄"이 구분된다.

    전자는 통신/펌웨어 이상 신호이고 후자는 정상 상황이므로 소비자가 다르게 다뤄야 한다.
    """
    malformed = parse_packet("STATUS,1.0,2.0")
    unknown = parse_packet("SOME_NEW_MESSAGE,1.0,2.0")

    assert malformed.kind is PacketKind.MALFORMED
    assert unknown.kind is PacketKind.UNKNOWN
    assert malformed.kind is not unknown.kind


def test_raw_is_preserved_for_logging() -> None:
    """raw에는 공백·CRLF만 제거한 원본이 남아 로그로 쓸 수 있다."""
    packet = parse_packet("  ERROR,RESET_STALL,NO_STALL  \r\n")

    assert packet.raw == "ERROR,RESET_STALL,NO_STALL"


def test_parse_packet_never_raises_for_str_input() -> None:
    """어떤 str 입력에도 예외를 던지지 않는다 — 수신 루프가 한 줄 때문에 죽으면 안 된다."""
    weird_lines = [
        "",
        ",",
        ",,,,,,,,",
        "STATUS,,,,,,,,",
        "\x00\x01",
        "STATUS," + "9" * 500,
        "가나다",
        "-",
        "STATUS,1e999,2.0,3.0,4.0,5,6,7,8",  # float 오버플로 -> inf
    ]

    for line in weird_lines:
        packet = parse_packet(line)
        assert isinstance(packet.kind, PacketKind), line


def test_float_overflow_literal_is_rejected_as_non_finite() -> None:
    """`1e999`는 float()에서 inf가 되므로 유한성 검사에 걸려 MALFORMED다."""
    packet = parse_packet("STATUS,1e999,2.0,3.0,4.0,5,6,7,8")

    assert packet.kind is PacketKind.MALFORMED
    assert "not finite" in packet.reason


@pytest.mark.parametrize("line", [b"STATUS,1,2", 123, None, ["STATUS"], 1.5])
def test_non_str_input_raises_type_error(line: object) -> None:
    """str이 아닌 입력은 TypeError다(bytes를 그대로 넘기는 실수 포함).

    이건 데이터 오류가 아니라 호출 규약 위반이므로 조용히 넘기지 않는다.
    """
    with pytest.raises(TypeError, match="must be str"):
        parse_packet(line)  # type: ignore[arg-type]
