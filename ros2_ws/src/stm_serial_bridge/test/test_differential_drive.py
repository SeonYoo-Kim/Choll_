"""differential_drive 모듈(변환 + 필요 상한 계산)의 단위 테스트.

ROS 실행 환경·하드웨어 없이 돌아간다(순수 함수 대상).

실행::

    cd ros2_ws
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 -m pytest src/stm_serial_bridge/test/test_differential_drive.py -v
"""

import math

import pytest

from stm_serial_bridge.differential_drive import (
    cmd_vel_to_wheel_rad_s,
    required_max_wheel_rad_s,
)

WHEEL_RADIUS_M = 0.065

# 2026-08-04 실측값 (좌우 구동 바퀴 트레드 중심선 간 거리 38cm).
# `config/stm_serial_bridge.yaml` 과 같은 값을 쓴다 — 한쪽만 바꾸면 아래 회귀값이
# 깨져 불일치를 즉시 잡을 수 있다.
WHEEL_SEPARATION_M = 0.38

# 상위 주행 스택(Nav2 `controller_server`)의 속도 봉투.
# 정본: embedded/Lidar/src/choll_nav2/config/nav2_params.yaml (`max_vel_x`/`max_vel_theta`)
# ⚠️ 그 파일은 아직 develop에 머지되지 않은 브랜치에 있고, 해당 값에도 `TODO-팀확인`
#    표기가 붙어 있다. 아래 상수는 "현재 문서화된 값"이며 확정값이 아니다.
NAV2_MAX_LINEAR_MPS = 0.3
NAV2_MAX_ANGULAR_RPS = 0.6

# 브리지 기본 상한 (config/stm_serial_bridge.yaml). 벤치 안전용 잠정값.
BENCH_MAX_WHEEL_RAD_S = 1.0

# slow / nav2 프로파일의 상한 (config/speed_profile_*.yaml).
SLOW_MAX_WHEEL_RAD_S = 2.0
NAV2_PROFILE_MAX_WHEEL_RAD_S = 6.4


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
    # (L=0.38 기준. L=0.30 placeholder 였을 때는 1.923077 / 4.230769 였다.)
    assert left == pytest.approx(1.615384615, abs=1e-6)
    assert right == pytest.approx(4.538461538, abs=1e-6)
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


# ---------------------------------------------------------------------------
# required_max_wheel_rad_s: 속도 봉투 -> 필요한 max_wheel_rad_s
# ---------------------------------------------------------------------------


def test_required_max_for_straight_only() -> None:
    """직진만: 필요 상한은 v / r 이다 (회전 성분이 없다)."""
    expected = NAV2_MAX_LINEAR_MPS / WHEEL_RADIUS_M

    required = required_max_wheel_rad_s(
        NAV2_MAX_LINEAR_MPS, 0.0, WHEEL_RADIUS_M, WHEEL_SEPARATION_M
    )

    assert required == pytest.approx(expected)
    assert required == pytest.approx(4.615384615, abs=1e-6)


def test_required_max_for_in_place_rotation_only() -> None:
    """제자리 회전만: 필요 상한은 ω·L/2 / r 이다 (직진 성분이 없다)."""
    expected = (NAV2_MAX_ANGULAR_RPS * WHEEL_SEPARATION_M / 2.0) / WHEEL_RADIUS_M

    required = required_max_wheel_rad_s(
        0.0, NAV2_MAX_ANGULAR_RPS, WHEEL_RADIUS_M, WHEEL_SEPARATION_M
    )

    assert required == pytest.approx(expected)
    assert required == pytest.approx(1.753846154, abs=1e-6)


def test_slow_profile_covers_the_in_place_rotation_envelope() -> None:
    """`slow`(2.0)가 제자리 회전 봉투 전체를 무축소로 수용한다 — 그 프로파일의 근거.

    L 이 커지면 회전 요구량이 늘어나므로 언젠가 이 관계가 깨진다(L>0.433). 그때
    `speed_profile_slow.yaml` 의 설명과 값을 재검토해야 하므로 여기서 고정한다.
    """
    required_for_rotation = required_max_wheel_rad_s(
        0.0, NAV2_MAX_ANGULAR_RPS, WHEEL_RADIUS_M, WHEEL_SEPARATION_M
    )

    assert required_for_rotation <= SLOW_MAX_WHEEL_RAD_S


def test_required_max_for_worst_case_is_about_six_point_four() -> None:
    """★ 직진+회전 최악 조건: Nav2 봉투 전체를 수용하려면 약 6.369 rad/s가 필요하다.

    이 값이 브리지 기본 상한(1.0)을 크게 넘는다는 사실이 프로파일 도입의 근거다.
    회귀 고정값이므로 기구학 상수가 바뀌면 여기서 먼저 깨진다.

    ⚠️ L=0.30 placeholder 였을 때 이 값은 6.0 이었다. 2026-08-04 실측(0.38)으로
    6.369 가 되었고, 그래서 `nav2` 프로파일 상한을 6.0 -> 6.4 로 올렸다.
    """
    expected = (
        NAV2_MAX_LINEAR_MPS + NAV2_MAX_ANGULAR_RPS * WHEEL_SEPARATION_M / 2.0
    ) / WHEEL_RADIUS_M

    required = required_max_wheel_rad_s(
        NAV2_MAX_LINEAR_MPS,
        NAV2_MAX_ANGULAR_RPS,
        WHEEL_RADIUS_M,
        WHEEL_SEPARATION_M,
    )

    assert required == pytest.approx(expected)
    assert required == pytest.approx(6.369230769, abs=1e-6)


def test_nav2_profile_covers_the_full_envelope() -> None:
    """★ `nav2` 프로파일(6.4)이 봉투 전체를 무축소로 수용한다.

    L 을 바꾸면 요구량이 움직이므로 이 관계가 깨질 수 있다 — 그때 프로파일 값을 함께
    올려야 한다는 사실을 테스트로 고정한다. L=0.30 시절의 6.0 은 지금 기준으로
    **부족**하다(6.369 > 6.0).
    """
    required = required_max_wheel_rad_s(
        NAV2_MAX_LINEAR_MPS,
        NAV2_MAX_ANGULAR_RPS,
        WHEEL_RADIUS_M,
        WHEEL_SEPARATION_M,
    )

    assert required <= NAV2_PROFILE_MAX_WHEEL_RAD_S
    # 옛 값 6.0 이 왜 부족한지도 함께 고정한다(되돌리기 방지).
    assert required > 6.0


def test_required_max_exceeds_the_bench_cap() -> None:
    """벤치 기본 상한(1.0)은 Nav2 봉투를 수용하지 못한다 — 이 모듈의 존재 이유.

    이 관계가 뒤집히면(상한이 봉투를 덮으면) 프로파일 오버레이가 더는 필요하지 않다는
    뜻이므로, 그때 설계를 다시 봐야 한다.
    """
    required = required_max_wheel_rad_s(
        NAV2_MAX_LINEAR_MPS,
        NAV2_MAX_ANGULAR_RPS,
        WHEEL_RADIUS_M,
        WHEEL_SEPARATION_M,
    )

    assert required > BENCH_MAX_WHEEL_RAD_S


@pytest.mark.parametrize("angular_sign", [1.0, -1.0])
def test_required_max_ignores_angular_sign(angular_sign: float) -> None:
    """각속도 부호는 봉투 크기와 무관하다 — 좌회전·우회전 요구량이 같다."""
    required = required_max_wheel_rad_s(
        NAV2_MAX_LINEAR_MPS,
        angular_sign * NAV2_MAX_ANGULAR_RPS,
        WHEEL_RADIUS_M,
        WHEEL_SEPARATION_M,
    )

    assert required == pytest.approx(6.369230769, abs=1e-6)


@pytest.mark.parametrize("linear_sign", [1.0, -1.0])
def test_required_max_ignores_linear_sign(linear_sign: float) -> None:
    """선속도 부호도 무관하다 — 후진 봉투가 같으면 요구량도 같다."""
    required = required_max_wheel_rad_s(
        linear_sign * NAV2_MAX_LINEAR_MPS,
        NAV2_MAX_ANGULAR_RPS,
        WHEEL_RADIUS_M,
        WHEEL_SEPARATION_M,
    )

    assert required == pytest.approx(6.369230769, abs=1e-6)


def test_required_max_for_zero_envelope_is_zero() -> None:
    """봉투가 (0, 0)이면 필요 상한도 0이다."""
    required = required_max_wheel_rad_s(
        0.0, 0.0, WHEEL_RADIUS_M, WHEEL_SEPARATION_M
    )

    assert required == pytest.approx(0.0)


def test_required_max_agrees_with_the_conversion_at_the_envelope_corner() -> None:
    """두 함수가 어긋나지 않게 고정한다.

    `required_max_wheel_rad_s()`는 `cmd_vel_to_wheel_rad_s()`를 재사용하므로, 봉투
    꼭짓점에서 실제 변환 결과의 절댓값 최대와 정확히 같아야 한다. 한쪽만 바뀌면 실패한다.
    """
    left, right = cmd_vel_to_wheel_rad_s(
        NAV2_MAX_LINEAR_MPS,
        NAV2_MAX_ANGULAR_RPS,
        WHEEL_RADIUS_M,
        WHEEL_SEPARATION_M,
    )

    required = required_max_wheel_rad_s(
        NAV2_MAX_LINEAR_MPS,
        NAV2_MAX_ANGULAR_RPS,
        WHEEL_RADIUS_M,
        WHEEL_SEPARATION_M,
    )

    assert required == pytest.approx(max(abs(left), abs(right)))


@pytest.mark.parametrize("wheel_radius_m", [0.0, -0.065])
def test_required_max_rejects_non_positive_wheel_radius(
    wheel_radius_m: float,
) -> None:
    """바퀴 반지름이 0 이하면 ValueError를 그대로 전달한다(검증 중복 없음)."""
    with pytest.raises(ValueError, match="wheel_radius_m"):
        required_max_wheel_rad_s(
            NAV2_MAX_LINEAR_MPS,
            NAV2_MAX_ANGULAR_RPS,
            wheel_radius_m,
            WHEEL_SEPARATION_M,
        )


@pytest.mark.parametrize("wheel_separation_m", [0.0, -0.30])
def test_required_max_rejects_non_positive_wheel_separation(
    wheel_separation_m: float,
) -> None:
    """바퀴 간격이 0 이하면 ValueError를 그대로 전달한다(검증 중복 없음)."""
    with pytest.raises(ValueError, match="wheel_separation_m"):
        required_max_wheel_rad_s(
            NAV2_MAX_LINEAR_MPS,
            NAV2_MAX_ANGULAR_RPS,
            WHEEL_RADIUS_M,
            wheel_separation_m,
        )


@pytest.mark.parametrize(
    ("max_linear_mps", "max_angular_rps"),
    [
        (float("nan"), 0.6),
        (0.3, float("nan")),
        (float("inf"), 0.6),
        (0.3, float("inf")),
    ],
)
def test_required_max_propagates_non_finite_envelope(
    max_linear_mps: float,
    max_angular_rps: float,
) -> None:
    """속도 인자의 유한성은 검사하지 않는다 — `cmd_vel_to_wheel_rad_s()`와 같은 규칙.

    0.0을 초기값으로 두고 max()를 누적하면 `nan > 0.0`이 False라 NaN이 조용히 0.0으로
    삼켜진다. 그 함정에 빠지지 않았음을 고정한다.
    """
    required = required_max_wheel_rad_s(
        max_linear_mps, max_angular_rps, WHEEL_RADIUS_M, WHEEL_SEPARATION_M
    )

    assert not math.isfinite(required)
