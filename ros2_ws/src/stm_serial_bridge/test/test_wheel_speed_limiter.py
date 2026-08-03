"""limit_wheel_rad_s()의 비례 축소 단위 테스트.

ROS 실행 환경·시리얼·하드웨어 없이 돌아간다(순수 함수 대상).

실행::

    cd ros2_ws
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 -m pytest src/stm_serial_bridge/test/test_wheel_speed_limiter.py -v
"""

import pytest

from stm_serial_bridge.wheel_speed_limiter import limit_wheel_rad_s

MAX_RAD_S = 2.0

# 2단계 차동구동 계산의 대표값(linear.x=0.2, angular.z=0.5, r=0.065, L=0.30).
RAW_LEFT = 1.923076923
RAW_RIGHT = 4.230769231

# 위 값을 max=2.0으로 비례 축소한 결과: scale = 2.0 / 4.230769231
LIMITED_LEFT = 0.909090909
LIMITED_RIGHT = 2.0


def test_zero_stays_zero() -> None:
    """둘 다 0이면 0,0을 그대로 반환한다(0으로 나누는 경로가 없음을 함께 고정)."""
    left, right = limit_wheel_rad_s(0.0, 0.0, MAX_RAD_S)

    assert left == pytest.approx(0.0)
    assert right == pytest.approx(0.0)


def test_within_limit_is_unchanged() -> None:
    """제한 이내면 원본을 그대로 반환한다."""
    left, right = limit_wheel_rad_s(0.5, 1.5, MAX_RAD_S)

    assert left == pytest.approx(0.5)
    assert right == pytest.approx(1.5)


def test_exactly_at_limit_is_unchanged() -> None:
    """정확히 제한값이면 축소하지 않는다(경계값은 허용 범위)."""
    left, right = limit_wheel_rad_s(1.0, MAX_RAD_S, MAX_RAD_S)

    assert left == pytest.approx(1.0)
    assert right == pytest.approx(MAX_RAD_S)


def test_right_peak_is_scaled_proportionally() -> None:
    """오른쪽 절댓값이 큰 경우: 대표값이 0.909/2.000으로 비례 축소된다."""
    left, right = limit_wheel_rad_s(RAW_LEFT, RAW_RIGHT, MAX_RAD_S)

    assert left == pytest.approx(LIMITED_LEFT, abs=1e-6)
    assert right == pytest.approx(LIMITED_RIGHT)


def test_left_peak_is_scaled_proportionally() -> None:
    """왼쪽 절댓값이 큰 경우도 같은 비율로 축소된다(좌우 대칭)."""
    left, right = limit_wheel_rad_s(RAW_RIGHT, RAW_LEFT, MAX_RAD_S)

    assert left == pytest.approx(LIMITED_RIGHT)
    assert right == pytest.approx(LIMITED_LEFT, abs=1e-6)


def test_both_negative_keeps_sign_and_ratio() -> None:
    """양쪽 음수(후진)에서도 부호와 비율이 유지된다."""
    left, right = limit_wheel_rad_s(-RAW_LEFT, -RAW_RIGHT, MAX_RAD_S)

    assert left == pytest.approx(-LIMITED_LEFT, abs=1e-6)
    assert right == pytest.approx(-LIMITED_RIGHT)
    assert left < 0.0
    assert right < 0.0


def test_in_place_rotation_keeps_opposite_signs() -> None:
    """제자리 회전(좌우 부호 반대)도 비례 축소되며 절댓값이 같게 유지된다."""
    left, right = limit_wheel_rad_s(-4.0, 4.0, MAX_RAD_S)

    assert left == pytest.approx(-MAX_RAD_S)
    assert right == pytest.approx(MAX_RAD_S)
    assert left < 0.0 < right
    assert abs(left) == pytest.approx(abs(right))


def test_large_finite_values_are_scaled() -> None:
    """큰 유한값도 거부되지 않고 정상적으로 비례 축소된다."""
    left, right = limit_wheel_rad_s(1000.0, -2000.0, MAX_RAD_S)

    assert left == pytest.approx(1.0)
    assert right == pytest.approx(-MAX_RAD_S)


@pytest.mark.parametrize(
    ("raw_left", "raw_right"),
    [
        (RAW_LEFT, RAW_RIGHT),
        (-4.0, 4.0),
        (1000.0, -2000.0),
        (0.5, 1.5),
        (0.0, 0.0),
    ],
)
def test_peak_never_exceeds_max_after_limiting(
    raw_left: float, raw_right: float
) -> None:
    """제한 후 최대 절댓값은 항상 max 이하다(제한이 필요 없던 경우 포함)."""
    left, right = limit_wheel_rad_s(raw_left, raw_right, MAX_RAD_S)

    assert max(abs(left), abs(right)) <= MAX_RAD_S + 1e-9


@pytest.mark.parametrize(
    ("raw_left", "raw_right"),
    [(RAW_LEFT, RAW_RIGHT), (-4.0, 8.0), (3.0, -1.5), (1000.0, -2000.0)],
)
def test_ratio_is_preserved(raw_left: float, raw_right: float) -> None:
    """제한 전후 좌우 비율이 보존된다 — 궤적의 곡률이 바뀌지 않는다는 뜻이다.

    좌우를 각각 독립적으로 clamp하면 이 테스트가 실패한다.
    """
    left, right = limit_wheel_rad_s(raw_left, raw_right, MAX_RAD_S)

    # left/right == raw_left/raw_right  <=>  left*raw_right == right*raw_left
    assert left * raw_right == pytest.approx(right * raw_left, abs=1e-9)


@pytest.mark.parametrize("left_rad_s", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_left_raises_value_error(left_rad_s: float) -> None:
    """왼쪽 값이 유한하지 않으면 ValueError다."""
    with pytest.raises(ValueError, match="left_rad_s"):
        limit_wheel_rad_s(left_rad_s, 1.0, MAX_RAD_S)


@pytest.mark.parametrize("right_rad_s", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_right_raises_value_error(right_rad_s: float) -> None:
    """오른쪽 값이 유한하지 않으면 ValueError다."""
    with pytest.raises(ValueError, match="right_rad_s"):
        limit_wheel_rad_s(1.0, right_rad_s, MAX_RAD_S)


@pytest.mark.parametrize("max_wheel_rad_s", [float("nan"), float("inf")])
def test_non_finite_max_raises_value_error(max_wheel_rad_s: float) -> None:
    """max가 NaN/Infinity면 ValueError다.

    NaN은 `<= 0.0` 비교를 통과하고 `peak <= NaN`도 항상 False가 되므로, 유한성
    검사가 없으면 scale이 NaN이 되어 명령 전체가 망가진다.
    """
    with pytest.raises(ValueError, match="max_wheel_rad_s"):
        limit_wheel_rad_s(1.0, 2.0, max_wheel_rad_s)


@pytest.mark.parametrize("max_wheel_rad_s", [0.0, -1.0, -2.0])
def test_non_positive_max_raises_value_error(max_wheel_rad_s: float) -> None:
    """max가 0 이하면 ValueError다."""
    with pytest.raises(ValueError, match="max_wheel_rad_s"):
        limit_wheel_rad_s(1.0, 2.0, max_wheel_rad_s)
