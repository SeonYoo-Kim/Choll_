"""cmd_vel_to_wheel_rad_s()의 차동구동 변환 단위 테스트.

ROS 실행 환경·하드웨어 없이 돌아간다(순수 함수 대상).

실행::

    cd ros2_ws
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 -m pytest src/stm_serial_bridge/test/test_differential_drive.py -v
"""

import pytest

from stm_serial_bridge.differential_drive import cmd_vel_to_wheel_rad_s

WHEEL_RADIUS_M = 0.065

# ⚠️ 임시값: 좌우 바퀴 중심 간 거리는 조립 후 실측이 필요하다. 아래 테스트는 이
# 값을 기준으로 계산식의 정합성만 검증하며, 실제 로봇의 회전량을 보증하지 않는다.
WHEEL_SEPARATION_M = 0.30


def test_zero_twist_yields_zero_wheel_velocities() -> None:
    """정지: 선속도·각속도가 모두 0이면 좌우 바퀴 각속도도 0이다."""
    left, right = cmd_vel_to_wheel_rad_s(
        0.0, 0.0, WHEEL_RADIUS_M, WHEEL_SEPARATION_M
    )

    assert left == pytest.approx(0.0)
    assert right == pytest.approx(0.0)


def test_forward_only_yields_equal_positive_wheel_velocities() -> None:
    """직진: 각속도가 0이면 좌우가 같고 양수다."""
    expected = 0.2 / WHEEL_RADIUS_M

    left, right = cmd_vel_to_wheel_rad_s(
        0.2, 0.0, WHEEL_RADIUS_M, WHEEL_SEPARATION_M
    )

    assert left == pytest.approx(expected)
    assert right == pytest.approx(expected)
    assert left > 0.0
    assert left == pytest.approx(right)


def test_backward_only_yields_equal_negative_wheel_velocities() -> None:
    """후진: 각속도가 0이면 좌우가 같고 음수다."""
    expected = -0.2 / WHEEL_RADIUS_M

    left, right = cmd_vel_to_wheel_rad_s(
        -0.2, 0.0, WHEEL_RADIUS_M, WHEEL_SEPARATION_M
    )

    assert left == pytest.approx(expected)
    assert right == pytest.approx(expected)
    assert left < 0.0
    assert left == pytest.approx(right)


def test_in_place_left_turn_yields_opposite_signs_with_equal_magnitude() -> None:
    """제자리 좌회전: angular_z > 0이면 왼쪽은 음수, 오른쪽은 양수이며 절댓값이 같다."""
    expected_left = (-0.5 * WHEEL_SEPARATION_M / 2.0) / WHEEL_RADIUS_M
    expected_right = (0.5 * WHEEL_SEPARATION_M / 2.0) / WHEEL_RADIUS_M

    left, right = cmd_vel_to_wheel_rad_s(
        0.0, 0.5, WHEEL_RADIUS_M, WHEEL_SEPARATION_M
    )

    assert left == pytest.approx(expected_left)
    assert right == pytest.approx(expected_right)
    assert left < 0.0 < right
    assert abs(left) == pytest.approx(abs(right))


def test_forward_left_curve_keeps_left_slower_than_right() -> None:
    """전진 곡선 주행: 좌우 순서와 두 항의 결합 계산을 검증한다.

    ROS2 기준 angular_z > 0(반시계, 좌회전)이므로 전진 중에는 왼쪽이 더 느려야 한다.
    반환 순서가 뒤바뀌면 이 테스트가 실패한다.
    """
    expected_left = (0.2 - 0.5 * WHEEL_SEPARATION_M / 2.0) / WHEEL_RADIUS_M
    expected_right = (0.2 + 0.5 * WHEEL_SEPARATION_M / 2.0) / WHEEL_RADIUS_M

    left, right = cmd_vel_to_wheel_rad_s(
        0.2, 0.5, WHEEL_RADIUS_M, WHEEL_SEPARATION_M
    )

    assert left == pytest.approx(expected_left)
    assert right == pytest.approx(expected_right)
    # 계산식 자체가 뒤바뀌어도 통과하지 않도록 구체 수치도 함께 고정한다.
    assert left == pytest.approx(1.923076923, abs=1e-6)
    assert right == pytest.approx(4.230769231, abs=1e-6)
    assert 0.0 < left < right


@pytest.mark.parametrize("wheel_radius_m", [0.0, -0.065])
def test_non_positive_wheel_radius_raises_value_error(
    wheel_radius_m: float,
) -> None:
    """바퀴 반지름이 0 이하면 ValueError이고, 메시지에 파라미터 이름이 담긴다."""
    with pytest.raises(ValueError, match="wheel_radius_m"):
        cmd_vel_to_wheel_rad_s(0.2, 0.0, wheel_radius_m, WHEEL_SEPARATION_M)


@pytest.mark.parametrize("wheel_separation_m", [0.0, -0.30])
def test_non_positive_wheel_separation_raises_value_error(
    wheel_separation_m: float,
) -> None:
    """바퀴 간격이 0 이하면 ValueError이고, 메시지에 파라미터 이름이 담긴다."""
    with pytest.raises(ValueError, match="wheel_separation_m"):
        cmd_vel_to_wheel_rad_s(0.2, 0.0, WHEEL_RADIUS_M, wheel_separation_m)
