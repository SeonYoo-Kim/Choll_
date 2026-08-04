"""build_set_wheel_vel_command()의 STM UART 명령 문자열 생성 단위 테스트.

ROS 실행 환경·시리얼 포트·하드웨어 없이 돌아간다(순수 함수 대상).

실행::

    cd ros2_ws
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 -m pytest src/stm_serial_bridge/test/test_protocol.py -v
"""

import pytest

from stm_serial_bridge.protocol import build_set_wheel_vel_command


def test_positive_values_are_formatted_with_three_decimals() -> None:
    """정상 양수: 2단계 계산 결과(1.923076923 / 4.230769231)가 3자리로 반올림된다."""
    command = build_set_wheel_vel_command(1.923076923, 4.230769231)

    assert command == "SET_WHEEL_VEL,1.923,4.231\r\n"


def test_negative_and_positive_values_round_to_three_decimals() -> None:
    """음수+양수: 제자리 회전 값(-1.153846 / 1.153846)의 3자리 반올림을 확인한다."""
    command = build_set_wheel_vel_command(-1.153846, 1.153846)

    assert command == "SET_WHEEL_VEL,-1.154,1.154\r\n"


def test_zero_values_are_formatted_as_three_decimal_zeros() -> None:
    """0 값: 정지 명령도 `0`이 아니라 `0.000`으로 출력된다."""
    command = build_set_wheel_vel_command(0.0, 0.0)

    assert command == "SET_WHEEL_VEL,0.000,0.000\r\n"


def test_short_decimal_values_are_padded_to_three_decimals() -> None:
    """자릿수 일관성: 정수·짧은 소수도 항상 세 자리로 채워진다."""
    command = build_set_wheel_vel_command(2.0, -3.5)

    assert command == "SET_WHEEL_VEL,2.000,-3.500\r\n"


def test_command_is_terminated_with_a_single_crlf() -> None:
    """종단: 정확히 CRLF 하나로 끝나고 LF가 중복되지 않는다."""
    command = build_set_wheel_vel_command(1.0, 2.0)

    assert command.endswith("\r\n")
    assert not command.endswith("\n\n")
    assert not command.endswith("\r\r\n")
    # CRLF는 줄 끝에 딱 한 번만 등장해야 한다(중간에 개행이 섞이면 프레이밍이 깨진다).
    assert command.count("\r") == 1
    assert command.count("\n") == 1
    assert command == "SET_WHEEL_VEL,1.000,2.000\r\n"


def test_nan_left_value_is_rejected() -> None:
    """왼쪽 NaN 거부: 예외 메시지에 left_rad_s가 담긴다."""
    with pytest.raises(ValueError, match="left_rad_s"):
        build_set_wheel_vel_command(float("nan"), 1.0)


def test_nan_right_value_is_rejected() -> None:
    """오른쪽 NaN 거부: 예외 메시지에 right_rad_s가 담긴다."""
    with pytest.raises(ValueError, match="right_rad_s"):
        build_set_wheel_vel_command(1.0, float("nan"))


def test_positive_infinity_left_value_is_rejected() -> None:
    """왼쪽 +Infinity 거부."""
    with pytest.raises(ValueError, match="left_rad_s"):
        build_set_wheel_vel_command(float("inf"), 1.0)


def test_negative_infinity_right_value_is_rejected() -> None:
    """오른쪽 -Infinity 거부."""
    with pytest.raises(ValueError, match="right_rad_s"):
        build_set_wheel_vel_command(1.0, float("-inf"))


def test_large_finite_values_are_not_rejected() -> None:
    """큰 유한값은 거부하지 않는다 — clamp는 이후 안전 제한 단계의 책임이다."""
    command = build_set_wheel_vel_command(1000.0, -1000.0)

    assert command == "SET_WHEEL_VEL,1000.000,-1000.000\r\n"
