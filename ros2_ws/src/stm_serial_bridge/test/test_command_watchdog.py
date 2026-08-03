"""select_wheel_command()의 cmd_vel timeout 판단 단위 테스트.

ROS 실행 환경·시리얼·하드웨어 없이 돌아간다. 시각을 인자로 넣으므로 실제 대기 없이
경계 조건을 결정적으로 검증한다.

실행::

    cd ros2_ws
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 -m pytest src/stm_serial_bridge/test/test_command_watchdog.py -v
"""

import pytest

from stm_serial_bridge.command_watchdog import (
    STATE_ACTIVE,
    STATE_TIMED_OUT,
    STATE_WAITING,
    select_wheel_command,
)

TIMEOUT_SEC = 0.5
LAST_TIME_SEC = 10.0

# 0이 아닌 최신 목표값. timeout 상태에서 이 값이 새어 나오지 않는지 확인하는 데 쓴다.
LEFT_RAD_S = 1.0
RIGHT_RAD_S = 2.0


def test_never_received_cmd_vel_yields_zero_and_waiting() -> None:
    """한 번도 /cmd_vel을 받지 않았으면 0,0 + waiting이다."""
    left, right, state = select_wheel_command(
        now_sec=LAST_TIME_SEC,
        last_cmd_vel_time_sec=None,
        cmd_vel_timeout_sec=TIMEOUT_SEC,
        latest_left_rad_s=LEFT_RAD_S,
        latest_right_rad_s=RIGHT_RAD_S,
    )

    assert left == pytest.approx(0.0)
    assert right == pytest.approx(0.0)
    assert state == STATE_WAITING


def test_fresh_cmd_vel_yields_latest_target_and_active() -> None:
    """timeout 이내면 최신 목표값 + active이다."""
    left, right, state = select_wheel_command(
        now_sec=LAST_TIME_SEC + 0.4,
        last_cmd_vel_time_sec=LAST_TIME_SEC,
        cmd_vel_timeout_sec=TIMEOUT_SEC,
        latest_left_rad_s=LEFT_RAD_S,
        latest_right_rad_s=RIGHT_RAD_S,
    )

    assert left == pytest.approx(LEFT_RAD_S)
    assert right == pytest.approx(RIGHT_RAD_S)
    assert state == STATE_ACTIVE


def test_just_below_timeout_stays_active() -> None:
    """경과 0.499초(timeout 0.5초)는 아직 active다."""
    left, right, state = select_wheel_command(
        now_sec=LAST_TIME_SEC + 0.499,
        last_cmd_vel_time_sec=LAST_TIME_SEC,
        cmd_vel_timeout_sec=TIMEOUT_SEC,
        latest_left_rad_s=LEFT_RAD_S,
        latest_right_rad_s=RIGHT_RAD_S,
    )

    assert state == STATE_ACTIVE
    assert left == pytest.approx(LEFT_RAD_S)
    assert right == pytest.approx(RIGHT_RAD_S)


def test_exactly_at_timeout_boundary_is_timed_out() -> None:
    """경과가 정확히 timeout과 같으면 timed_out이다(경계값은 정지 쪽으로 판정)."""
    left, right, state = select_wheel_command(
        now_sec=LAST_TIME_SEC + TIMEOUT_SEC,
        last_cmd_vel_time_sec=LAST_TIME_SEC,
        cmd_vel_timeout_sec=TIMEOUT_SEC,
        latest_left_rad_s=LEFT_RAD_S,
        latest_right_rad_s=RIGHT_RAD_S,
    )

    assert left == pytest.approx(0.0)
    assert right == pytest.approx(0.0)
    assert state == STATE_TIMED_OUT


@pytest.mark.parametrize("elapsed_sec", [0.501, 1.0, 60.0])
def test_beyond_timeout_is_timed_out(elapsed_sec: float) -> None:
    """timeout을 넘기면 0,0 + timed_out이다."""
    left, right, state = select_wheel_command(
        now_sec=LAST_TIME_SEC + elapsed_sec,
        last_cmd_vel_time_sec=LAST_TIME_SEC,
        cmd_vel_timeout_sec=TIMEOUT_SEC,
        latest_left_rad_s=LEFT_RAD_S,
        latest_right_rad_s=RIGHT_RAD_S,
    )

    assert left == pytest.approx(0.0)
    assert right == pytest.approx(0.0)
    assert state == STATE_TIMED_OUT


def test_timed_out_never_leaks_the_latest_nonzero_target() -> None:
    """timeout 상태에서는 최신 목표값이 아무리 커도 0,0만 반환한다(안전 핵심)."""
    left, right, state = select_wheel_command(
        now_sec=LAST_TIME_SEC + 10.0,
        last_cmd_vel_time_sec=LAST_TIME_SEC,
        cmd_vel_timeout_sec=TIMEOUT_SEC,
        latest_left_rad_s=999.0,
        latest_right_rad_s=-999.0,
    )

    assert left == pytest.approx(0.0)
    assert right == pytest.approx(0.0)
    assert state == STATE_TIMED_OUT


def test_large_finite_target_is_not_clamped_while_active() -> None:
    """active 상태에서 큰 유한값은 clamp되지 않는다 — 제한은 이후 단계의 책임이다."""
    left, right, state = select_wheel_command(
        now_sec=LAST_TIME_SEC,
        last_cmd_vel_time_sec=LAST_TIME_SEC,
        cmd_vel_timeout_sec=TIMEOUT_SEC,
        latest_left_rad_s=1000.0,
        latest_right_rad_s=-1000.0,
    )

    assert state == STATE_ACTIVE
    assert left == pytest.approx(1000.0)
    assert right == pytest.approx(-1000.0)


@pytest.mark.parametrize("cmd_vel_timeout_sec", [0.0, -0.5, -1.0])
def test_non_positive_timeout_raises_value_error(cmd_vel_timeout_sec: float) -> None:
    """timeout이 0 이하면 ValueError다."""
    with pytest.raises(ValueError, match="cmd_vel_timeout_sec"):
        select_wheel_command(
            now_sec=LAST_TIME_SEC,
            last_cmd_vel_time_sec=LAST_TIME_SEC,
            cmd_vel_timeout_sec=cmd_vel_timeout_sec,
            latest_left_rad_s=LEFT_RAD_S,
            latest_right_rad_s=RIGHT_RAD_S,
        )


@pytest.mark.parametrize("cmd_vel_timeout_sec", [float("nan"), float("inf")])
def test_non_finite_timeout_raises_value_error(cmd_vel_timeout_sec: float) -> None:
    """timeout이 NaN/Infinity면 ValueError다.

    NaN은 `<= 0.0` 비교를 통과해 버리므로(NaN 비교는 항상 False) 별도 유한성 검사가
    없으면 "영원히 active"가 되어 안전 정지가 동작하지 않는다.
    """
    with pytest.raises(ValueError, match="cmd_vel_timeout_sec"):
        select_wheel_command(
            now_sec=LAST_TIME_SEC,
            last_cmd_vel_time_sec=LAST_TIME_SEC,
            cmd_vel_timeout_sec=cmd_vel_timeout_sec,
            latest_left_rad_s=LEFT_RAD_S,
            latest_right_rad_s=RIGHT_RAD_S,
        )


@pytest.mark.parametrize("now_sec", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_now_raises_value_error(now_sec: float) -> None:
    """now_sec이 유한하지 않으면 ValueError다."""
    with pytest.raises(ValueError, match="now_sec"):
        select_wheel_command(
            now_sec=now_sec,
            last_cmd_vel_time_sec=LAST_TIME_SEC,
            cmd_vel_timeout_sec=TIMEOUT_SEC,
            latest_left_rad_s=LEFT_RAD_S,
            latest_right_rad_s=RIGHT_RAD_S,
        )


@pytest.mark.parametrize(
    "last_cmd_vel_time_sec", [float("nan"), float("inf"), float("-inf")]
)
def test_non_finite_last_time_raises_value_error(
    last_cmd_vel_time_sec: float,
) -> None:
    """last_cmd_vel_time_sec가 None이 아닌데 유한하지 않으면 ValueError다."""
    with pytest.raises(ValueError, match="last_cmd_vel_time_sec"):
        select_wheel_command(
            now_sec=LAST_TIME_SEC,
            last_cmd_vel_time_sec=last_cmd_vel_time_sec,
            cmd_vel_timeout_sec=TIMEOUT_SEC,
            latest_left_rad_s=LEFT_RAD_S,
            latest_right_rad_s=RIGHT_RAD_S,
        )


@pytest.mark.parametrize("latest_left_rad_s", [float("nan"), float("inf")])
def test_non_finite_latest_left_raises_value_error(latest_left_rad_s: float) -> None:
    """최신 왼쪽 목표값이 유한하지 않으면 ValueError다."""
    with pytest.raises(ValueError, match="latest_left_rad_s"):
        select_wheel_command(
            now_sec=LAST_TIME_SEC,
            last_cmd_vel_time_sec=LAST_TIME_SEC,
            cmd_vel_timeout_sec=TIMEOUT_SEC,
            latest_left_rad_s=latest_left_rad_s,
            latest_right_rad_s=RIGHT_RAD_S,
        )


@pytest.mark.parametrize("latest_right_rad_s", [float("nan"), float("-inf")])
def test_non_finite_latest_right_raises_value_error(
    latest_right_rad_s: float,
) -> None:
    """최신 오른쪽 목표값이 유한하지 않으면 ValueError다."""
    with pytest.raises(ValueError, match="latest_right_rad_s"):
        select_wheel_command(
            now_sec=LAST_TIME_SEC,
            last_cmd_vel_time_sec=LAST_TIME_SEC,
            cmd_vel_timeout_sec=TIMEOUT_SEC,
            latest_left_rad_s=LEFT_RAD_S,
            latest_right_rad_s=latest_right_rad_s,
        )


def test_non_finite_latest_target_raises_even_while_waiting() -> None:
    """waiting 상태에서도 최신 목표값 유한성을 검사한다(입력 검증은 상태와 무관).

    노드는 NaN을 최신 상태에 저장하지 않도록 콜백에서 걸러내지만, 이 함수 자체의
    계약을 상태에 따라 달라지지 않게 고정해 둔다.
    """
    with pytest.raises(ValueError, match="latest_left_rad_s"):
        select_wheel_command(
            now_sec=LAST_TIME_SEC,
            last_cmd_vel_time_sec=None,
            cmd_vel_timeout_sec=TIMEOUT_SEC,
            latest_left_rad_s=float("nan"),
            latest_right_rad_s=RIGHT_RAD_S,
        )


def test_state_constants_are_the_documented_strings() -> None:
    """상태 문자열이 계약대로 고정되어 있다(로그·문서와 어긋나면 실패)."""
    assert STATE_WAITING == "waiting"
    assert STATE_ACTIVE == "active"
    assert STATE_TIMED_OUT == "timed_out"
