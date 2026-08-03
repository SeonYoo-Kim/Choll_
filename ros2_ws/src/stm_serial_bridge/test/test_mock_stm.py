"""mock_stm 의 순수 함수 테스트 — 하드웨어·ROS 없이 돌아간다.

가장 중요한 것은 **왕복 테스트**다: `build_status_line()` 이 만든 줄을 브리지의 실제
파서(`parse_packet()`)가 STATUS 로 읽어내고 값이 그대로 복원되어야 한다. 이게 깨지면
mock 이 펌웨어 형식을 벗어난 것이므로, 펌웨어가 아니라 mock 을 고쳐야 한다.

실행::

    cd ros2_ws
    python3 -m pytest src/stm_serial_bridge/test/test_mock_stm.py -v
"""

import math

import pytest

from stm_serial_bridge.mock_stm import (
    DEFAULT_COUNTS_PER_WHEEL_REV,
    advance_encoder,
    build_status_line,
    parse_set_wheel_vel,
    wrap_int32,
)
from stm_serial_bridge.packet_parser import PacketKind, parse_packet

_INT32_MIN = -2147483648
_INT32_MAX = 2147483647


# ---------------------------------------------------------------------------
# build_status_line: 펌웨어 형식과 일치하는가
# ---------------------------------------------------------------------------


def test_status_line_matches_the_firmware_format() -> None:
    """펌웨어 snprintf 형식과 같은 문자열을 만든다."""
    line = build_status_line(1.0, 2.0, 3.0, 4.0, 5, 6, 7, 8)
    assert line == "STATUS,1.00,2.00,3.00,4.00,5,6,7,8\r\n"


def test_status_line_always_ends_with_crlf() -> None:
    """줄 끝은 항상 CRLF 다 (펌웨어와 동일)."""
    line = build_status_line(0.0, 0.0, 0.0, 0.0, 0, 0, 0, 0)
    assert line.endswith("\r\n")
    assert line.count("\r\n") == 1


def test_status_line_uses_two_decimals() -> None:
    """실수 필드는 소수 2자리로 고정한다."""
    line = build_status_line(1.239, -0.001, 0.0, 0.0, 0, 0, 0, 0)
    assert line.startswith("STATUS,1.24,-0.00,0.00,0.00,")


def test_status_line_keeps_negative_values() -> None:
    """음수 PWM·엔코더(후진)도 그대로 실린다."""
    line = build_status_line(-1.5, -1.5, -2.5, -2.5, -100, -200, -1234, -5678)
    assert line == "STATUS,-1.50,-1.50,-2.50,-2.50,-100,-200,-1234,-5678\r\n"


# ---------------------------------------------------------------------------
# ★ 왕복: build_status_line -> parse_packet
# ---------------------------------------------------------------------------


def test_round_trip_through_the_real_parser() -> None:
    """mock 이 만든 줄을 브리지의 실제 파서가 STATUS 로 읽고 값이 복원된다."""
    line = build_status_line(1.25, -2.50, 3.75, -4.00, 120, -240, 111111, -222222)
    parsed = parse_packet(line.rstrip("\r\n"))

    assert parsed.kind is PacketKind.STATUS
    status = parsed.payload
    assert status is not None
    assert status.left_target_rad_s == pytest.approx(1.25)
    assert status.left_actual_rad_s == pytest.approx(-2.50)
    assert status.right_target_rad_s == pytest.approx(3.75)
    assert status.right_actual_rad_s == pytest.approx(-4.00)
    assert status.left_pwm == 120
    assert status.right_pwm == -240
    assert status.left_encoder_total == 111111
    assert status.right_encoder_total == -222222


def test_round_trip_at_encoder_int32_limits() -> None:
    """int32 경계값도 파서가 받아들인다."""
    for encoder in (_INT32_MIN, _INT32_MAX):
        line = build_status_line(0.0, 0.0, 0.0, 0.0, 0, 0, encoder, encoder)
        parsed = parse_packet(line.rstrip("\r\n"))
        assert parsed.kind is PacketKind.STATUS
        assert parsed.payload is not None
        assert parsed.payload.left_encoder_total == encoder


def test_round_trip_preserves_left_right_field_order() -> None:
    """와이어 순서가 LT,LA,RT,RA 임을 왕복으로 고정한다."""
    # 좌 target=10, 좌 actual=20, 우 target=30, 우 actual=40
    line = build_status_line(10.0, 20.0, 30.0, 40.0, 0, 0, 0, 0)
    assert line.startswith("STATUS,10.00,20.00,30.00,40.00,")

    status = parse_packet(line.rstrip("\r\n")).payload
    assert status is not None
    assert status.left_target_rad_s == pytest.approx(10.0)
    assert status.left_actual_rad_s == pytest.approx(20.0)
    assert status.right_target_rad_s == pytest.approx(30.0)
    assert status.right_actual_rad_s == pytest.approx(40.0)


# ---------------------------------------------------------------------------
# wrap_int32
# ---------------------------------------------------------------------------


def test_wrap_int32_is_identity_inside_the_range() -> None:
    """범위 안에서는 값을 바꾸지 않는다."""
    for value in (_INT32_MIN, -1, 0, 1, _INT32_MAX):
        assert wrap_int32(value) == value


def test_wrap_int32_wraps_above_the_maximum() -> None:
    """최댓값을 넘으면 최솟값으로 돈다."""
    assert wrap_int32(_INT32_MAX + 1) == _INT32_MIN
    assert wrap_int32(_INT32_MAX + 2) == _INT32_MIN + 1


def test_wrap_int32_wraps_below_the_minimum() -> None:
    """최솟값 아래로 가면 최댓값으로 돈다."""
    assert wrap_int32(_INT32_MIN - 1) == _INT32_MAX


# ---------------------------------------------------------------------------
# advance_encoder
# ---------------------------------------------------------------------------


def test_advance_encoder_one_full_revolution() -> None:
    """2*pi rad/s 로 1초 = 정확히 1회전만큼 count 가 증가한다."""
    advanced = advance_encoder(0, 2.0 * math.pi, 1.0, 1000.0)
    assert advanced == 1000


def test_advance_encoder_uses_the_nominal_counts_per_rev_by_default() -> None:
    """기본 counts/rev 는 펌웨어 명목값(380 x 51 x 4 = 77520)이다."""
    assert DEFAULT_COUNTS_PER_WHEEL_REV == pytest.approx(77520.0)
    advanced = advance_encoder(0, 2.0 * math.pi, 1.0)
    assert advanced == 77520


def test_advance_encoder_goes_backwards_for_negative_speed() -> None:
    """음수 각속도면 count 가 감소한다."""
    advanced = advance_encoder(0, -2.0 * math.pi, 1.0, 1000.0)
    assert advanced == -1000


def test_advance_encoder_is_unchanged_for_zero_speed() -> None:
    """정지 상태면 count 가 그대로다."""
    assert advance_encoder(4321, 0.0, 1.0) == 4321


@pytest.mark.parametrize("dt_sec", [0.0, -0.1])
def test_advance_encoder_ignores_nonpositive_dt(dt_sec: float) -> None:
    """dt 가 0 이하면 전진시키지 않는다."""
    assert advance_encoder(500, 10.0, dt_sec) == 500


def test_advance_encoder_accumulates_across_calls() -> None:
    """반복 호출하면 누적된다."""
    count = 0
    for _ in range(4):
        count = advance_encoder(count, 2.0 * math.pi, 1.0, 1000.0)
    assert count == 4000


def test_advance_encoder_wraps_at_int32() -> None:
    """누적이 int32 를 넘으면 래핑한다."""
    advanced = advance_encoder(_INT32_MAX, 2.0 * math.pi, 1.0, 1000.0)
    assert _INT32_MIN <= advanced <= _INT32_MAX


@pytest.mark.parametrize("counts_per_rev", [0.0, -1.0])
def test_advance_encoder_rejects_nonpositive_counts_per_rev(
    counts_per_rev: float,
) -> None:
    """counts/rev 가 0 이하면 ValueError 다."""
    with pytest.raises(ValueError, match="counts_per_wheel_rev must be positive"):
        advance_encoder(0, 1.0, 1.0, counts_per_rev)


# ---------------------------------------------------------------------------
# parse_set_wheel_vel
# ---------------------------------------------------------------------------


def test_parse_set_wheel_vel_reads_both_wheels() -> None:
    """브리지가 보내는 형식을 그대로 읽는다."""
    assert parse_set_wheel_vel("SET_WHEEL_VEL,1.500,-2.250") == (1.5, -2.25)


def test_parse_set_wheel_vel_tolerates_crlf() -> None:
    """CRLF 가 남아 있어도 읽는다."""
    assert parse_set_wheel_vel("SET_WHEEL_VEL,0.000,0.000\r\n") == (0.0, 0.0)


@pytest.mark.parametrize(
    "line",
    [
        "",
        "STATUS,1.00,2.00,3.00,4.00,5,6,7,8",
        "STOP",
        "set_wheel_vel,1.0,2.0",
        "SET_WHEEL_VEL",
        "SET_WHEEL_VEL,1.0",
        "SET_WHEEL_VEL,1.0,2.0,3.0",
        "SET_WHEEL_VEL,abc,2.0",
    ],
)
def test_parse_set_wheel_vel_returns_none_for_other_lines(line: str) -> None:
    """SET_WHEEL_VEL 이 아니거나 형식이 어긋나면 None 이다."""
    assert parse_set_wheel_vel(line) is None


def test_parse_set_wheel_vel_never_raises_for_str() -> None:
    """어떤 문자열이 와도 예외를 던지지 않는다."""
    for line in ("SET_WHEEL_VEL,,", "SET_WHEEL_VEL,nan,1.0", "\x00\x01"):
        parse_set_wheel_vel(line)
