"""apply_deadzone_compensation()의 단위 테스트.

ROS 실행 환경·시리얼·하드웨어 없이 돌아간다(순수 함수 대상).

실행::

    cd ros2_ws
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 -m pytest src/stm_serial_bridge/test/test_deadzone_compensator.py -v
"""

import math

import pytest

from stm_serial_bridge.deadzone_compensator import apply_deadzone_compensation

# 2026-08-07/08 실기 기준값: 바닥 데드존 PWM 10~12 = 바퀴 1.0~1.2 rad/s.
DEADZONE = 1.2
MAX_RAD_S = 8.0


def test_zero_stays_zero() -> None:
    """정지 명령은 보상해도 정지여야 한다 — 카트가 스멀스멀 움직이면 안 된다."""
    assert apply_deadzone_compensation(0.0, 0.0, DEADZONE, MAX_RAD_S) == (0.0, 0.0)


def test_disabled_when_deadzone_is_zero() -> None:
    """deadzone=0은 항등 함수다 — 기본값에서 기존 거동이 1비트도 바뀌지 않는다."""
    left, right = apply_deadzone_compensation(0.3, -1.7, 0.0, MAX_RAD_S)
    assert (left, right) == (0.3, -1.7)


def test_tiny_command_is_lifted_above_the_deadzone() -> None:
    """이 함수의 존재 이유 — 데드존 미만 명령이 실제 회전을 만드는 값이 된다."""
    left, right = apply_deadzone_compensation(0.05, 0.05, DEADZONE, MAX_RAD_S)
    assert left > DEADZONE
    assert right > DEADZONE
    # 0에 가까운 입력은 데드존 바로 위로 수렴한다(점프 폭이 최소).
    assert left == pytest.approx(DEADZONE, abs=0.06)


def test_max_command_is_unchanged() -> None:
    """상한 명령은 그대로 통과한다 — 재사상이 최고속도를 갉아먹지 않는다."""
    left, right = apply_deadzone_compensation(
        MAX_RAD_S, -MAX_RAD_S, DEADZONE, MAX_RAD_S
    )
    assert left == pytest.approx(MAX_RAD_S)
    assert right == pytest.approx(-MAX_RAD_S)


def test_midpoint_follows_the_affine_formula() -> None:
    """중간값은 deadzone + (max - deadzone) * ratio 를 따른다."""
    left, _ = apply_deadzone_compensation(4.0, 0.0, DEADZONE, MAX_RAD_S)
    expected = DEADZONE + (MAX_RAD_S - DEADZONE) * (4.0 / MAX_RAD_S)
    assert left == pytest.approx(expected)


def test_sign_is_preserved() -> None:
    """후진·좌회전이 전진·우회전으로 뒤집히면 안 된다."""
    left, right = apply_deadzone_compensation(-0.1, 0.1, DEADZONE, MAX_RAD_S)
    assert left < 0.0
    assert right > 0.0
    assert left == pytest.approx(-right)


def test_output_never_exceeds_the_limit() -> None:
    """상한을 넘겨 들어온 값도 상한 안에서 나온다(제한 방어선을 뚫지 않는다)."""
    left, right = apply_deadzone_compensation(
        99.0, -99.0, DEADZONE, MAX_RAD_S
    )
    assert abs(left) <= MAX_RAD_S
    assert abs(right) <= MAX_RAD_S


def test_epsilon_suppresses_float_residue() -> None:
    """부동소수 잔값(1e-9)에 데드존 offset이 붙지 않는다."""
    left, right = apply_deadzone_compensation(1e-9, -1e-9, DEADZONE, MAX_RAD_S)
    assert (left, right) == (0.0, 0.0)


def test_epsilon_boundary_is_inclusive() -> None:
    """epsilon과 같은 값은 정지로 본다(경계에서 진동하지 않게 고정)."""
    left, _ = apply_deadzone_compensation(
        1e-3, 0.0, DEADZONE, MAX_RAD_S, epsilon_rad_s=1e-3
    )
    assert left == 0.0


def test_monotonic_in_the_input() -> None:
    """입력이 커지면 출력도 커진다 — 제어 밴드가 뒤집히는 구간이 없어야 한다."""
    previous = 0.0
    for step in range(1, 41):
        value = MAX_RAD_S * step / 40.0
        left, _ = apply_deadzone_compensation(value, 0.0, DEADZONE, MAX_RAD_S)
        assert left > previous
        previous = left


def test_ratio_is_intentionally_not_preserved() -> None:
    """좌우 비율 보존은 이 함수의 계약이 **아니다**(limit_wheel_rad_s와 반대).

    데드존 보상의 본질적 부작용을 테스트로 못박아 둔다 — 나중에 "비율이 안 맞는다"를
    버그로 오인해 되돌리지 않도록.
    """
    raw_left, raw_right = 1.0, 2.0
    left, right = apply_deadzone_compensation(
        raw_left, raw_right, DEADZONE, MAX_RAD_S
    )
    assert right / left != pytest.approx(raw_right / raw_left)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"left_rad_s": math.nan},
        {"right_rad_s": math.inf},
        {"max_wheel_rad_s": 0.0},
        {"max_wheel_rad_s": -1.0},
        {"deadzone_wheel_rad_s": -0.1},
        {"epsilon_rad_s": -1e-6},
        # 데드존이 상한 이상이면 살아 있는 구간이 없다 -> 설정 오류로 거부.
        {"deadzone_wheel_rad_s": MAX_RAD_S},
        {"deadzone_wheel_rad_s": MAX_RAD_S + 1.0},
    ],
)
def test_invalid_arguments_raise(kwargs: dict) -> None:
    """잘못된 설정은 조용히 이상 동작하지 말고 ValueError로 드러나야 한다."""
    base = {
        "left_rad_s": 1.0,
        "right_rad_s": 1.0,
        "deadzone_wheel_rad_s": DEADZONE,
        "max_wheel_rad_s": MAX_RAD_S,
    }
    base.update(kwargs)
    with pytest.raises(ValueError):
        apply_deadzone_compensation(**base)
