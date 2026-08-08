"""wheel_odometry 모듈(엔코더 count -> 포즈·속도)의 단위 테스트.

ROS 실행 환경·하드웨어 없이 돌아간다(순수 함수 대상).

실행::

    cd ros2_ws
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 -m pytest src/stm_serial_bridge/test/test_wheel_odometry.py -v
"""

import math

import pytest

from stm_serial_bridge.differential_drive import cmd_vel_to_wheel_rad_s
from stm_serial_bridge.wheel_odometry import (
    OdometryState,
    WheelGeometry,
    advance,
    encoder_delta,
    initial_state,
    normalize_angle,
    rebaseline,
    twist_from_distances,
    wheel_distances,
)

WHEEL_RADIUS_M = 0.065

# 2026-08-04 실측값. `config/stm_serial_bridge.yaml` 및 test_differential_drive.py 와
# 같은 값을 쓴다.
WHEEL_SEPARATION_M = 0.38

# 2026-08-08 실측 기준값(좌우 공통). `config/stm_serial_bridge.yaml` 의
# `counts_per_wheel_rev` 와 같은 값이어야 한다.
COUNTS_PER_WHEEL_REV = 68160.0

# 펌웨어 `motor_config.h` 의 **명목값**(CPR 380 x Gear 51 x Quadrature 4).
# 오도메트리는 이 값을 쓰지 않는다 — 아래 스케일 격차 테스트에서만 쓴다.
NOMINAL_COUNTS_PER_WHEEL_REV = 77520.0

GEOMETRY = WheelGeometry(
    wheel_radius_m=WHEEL_RADIUS_M,
    wheel_separation_m=WHEEL_SEPARATION_M,
    counts_per_wheel_rev=COUNTS_PER_WHEEL_REV,
)

WHEEL_CIRCUMFERENCE_M = 2.0 * math.pi * WHEEL_RADIUS_M

INT32_MAX = 2147483647
INT32_MIN = -2147483648


# ---------------------------------------------------------------------------
# WheelGeometry
# ---------------------------------------------------------------------------


def test_meters_per_count_matches_circumference_over_counts() -> None:
    """count 당 거리는 바퀴 원주를 1회전당 count 로 나눈 값이다."""
    expected = WHEEL_CIRCUMFERENCE_M / COUNTS_PER_WHEEL_REV

    assert GEOMETRY.meters_per_count == pytest.approx(expected)
    # 상수가 바뀌면 즉시 깨지도록 구체 수치도 고정한다 (약 6 마이크로미터).
    assert GEOMETRY.meters_per_count == pytest.approx(5.9919e-6, abs=1e-9)


def test_measured_scale_differs_from_firmware_nominal_by_about_12_percent() -> None:
    """실측 68160 과 펌웨어 명목 77520 의 스케일 격차를 실행 가능한 형태로 고정한다.

    두 값을 섞으면 거리가 약 12% 어긋난다. 이 테스트가 깨진다면 어느 한쪽 상수가
    바뀐 것이므로, 그때는 문서(serial_protocol.md "펌웨어와 ROS의 스케일 불일치")도
    함께 갱신해야 한다.
    """
    nominal = WheelGeometry(
        wheel_radius_m=WHEEL_RADIUS_M,
        wheel_separation_m=WHEEL_SEPARATION_M,
        counts_per_wheel_rev=NOMINAL_COUNTS_PER_WHEEL_REV,
    )

    ratio = nominal.meters_per_count / GEOMETRY.meters_per_count

    # 명목값으로 계산하면 같은 count 에 대해 거리가 약 12.1% 작게 나온다.
    assert ratio == pytest.approx(COUNTS_PER_WHEEL_REV / NOMINAL_COUNTS_PER_WHEEL_REV)
    assert ratio == pytest.approx(0.87926, abs=1e-4)


@pytest.mark.parametrize(
    "field",
    ["wheel_radius_m", "wheel_separation_m", "counts_per_wheel_rev"],
)
@pytest.mark.parametrize(
    "value",
    [0.0, -1.0, float("nan"), float("inf"), float("-inf")],
)
def test_invalid_geometry_raises_value_error(field: str, value: float) -> None:
    """기구·엔코더 상수가 0 이하거나 비유한이면 필드 이름을 담은 ValueError 다.

    `differential_drive` 와 달리 비유한 입력도 막는다 — 오도메트리 포즈는 누적
    상태라서 NaN 이 한 번 섞이면 이후 모든 포즈가 영구히 오염되기 때문이다.
    """
    kwargs = {
        "wheel_radius_m": WHEEL_RADIUS_M,
        "wheel_separation_m": WHEEL_SEPARATION_M,
        "counts_per_wheel_rev": COUNTS_PER_WHEEL_REV,
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match=field):
        WheelGeometry(**kwargs)


# ---------------------------------------------------------------------------
# encoder_delta — int32 래핑
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("prev_count", "curr_count", "expected"),
    [
        (0, 100, 100),
        (100, 0, -100),
        (5, 5, 0),
        (-100, 100, 200),
        (100, -100, -200),
    ],
)
def test_encoder_delta_without_wrapping(
    prev_count: int, curr_count: int, expected: int
) -> None:
    """래핑이 없는 구간에서는 단순 뺄셈과 같다."""
    assert encoder_delta(prev_count, curr_count) == expected


@pytest.mark.parametrize(
    ("prev_count", "curr_count", "expected"),
    [
        (INT32_MAX, INT32_MIN, 1),
        (INT32_MIN, INT32_MAX, -1),
        (INT32_MAX - 500, INT32_MIN + 500, 1001),
        (INT32_MIN + 500, INT32_MAX - 500, -1001),
    ],
)
def test_encoder_delta_across_int32_wrap(
    prev_count: int, curr_count: int, expected: int
) -> None:
    """int32 경계를 넘어도 실제 변화량을 돌려준다."""
    assert encoder_delta(prev_count, curr_count) == expected


def test_encoder_delta_beats_naive_subtraction_at_the_wrap() -> None:
    """래핑 지점에서 단순 뺄셈은 약 43억 count 의 가짜 델타를 만든다.

    이 테스트가 지키려는 것은 "래핑 보정이 실제로 필요하다"는 사실 자체다.
    """
    naive = INT32_MIN - INT32_MAX

    assert naive == -4294967295
    assert encoder_delta(INT32_MAX, INT32_MIN) == 1


def test_encoder_delta_at_the_ambiguous_boundary() -> None:
    """변화량이 정확히 2**31 이면 부호를 구분할 수 없어 음수 쪽을 돌려준다."""
    assert encoder_delta(0, 1 << 31) == -(1 << 31)


# ---------------------------------------------------------------------------
# wheel_distances
# ---------------------------------------------------------------------------


def test_one_full_revolution_travels_one_circumference() -> None:
    """1회전당 count 만큼 변하면 바퀴 원주만큼 이동한다."""
    counts = int(COUNTS_PER_WHEEL_REV)

    left_m, right_m = wheel_distances(counts, -counts, GEOMETRY)

    assert left_m == pytest.approx(WHEEL_CIRCUMFERENCE_M)
    assert right_m == pytest.approx(-WHEEL_CIRCUMFERENCE_M)


def test_zero_delta_travels_nothing() -> None:
    """변화량이 0이면 이동 거리도 0이다."""
    assert wheel_distances(0, 0, GEOMETRY) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# twist_from_distances
# ---------------------------------------------------------------------------


def test_twist_for_straight_motion_has_no_rotation() -> None:
    """좌우가 같은 거리를 가면 각속도는 0이고 선속도는 거리/시간이다."""
    linear_x, angular_z = twist_from_distances(0.1, 0.1, GEOMETRY, 0.1)

    assert linear_x == pytest.approx(1.0)
    assert angular_z == pytest.approx(0.0)


def test_twist_for_in_place_rotation_has_no_linear_velocity() -> None:
    """좌우가 반대로 같은 거리를 가면 선속도는 0이고 반시계가 양수다."""
    linear_x, angular_z = twist_from_distances(-0.019, 0.019, GEOMETRY, 0.1)

    assert linear_x == pytest.approx(0.0)
    # omega = (0.019 - (-0.019)) / 0.38 / 0.1 = 1.0
    assert angular_z == pytest.approx(1.0)


@pytest.mark.parametrize(
    "dt_sec",
    [0.0, -0.1, float("nan"), float("inf")],
)
def test_non_positive_or_non_finite_dt_raises_value_error(dt_sec: float) -> None:
    """dt 가 0 이하거나 비유한이면 이름을 담은 ValueError 다."""
    with pytest.raises(ValueError, match="dt_sec"):
        twist_from_distances(0.1, 0.1, GEOMETRY, dt_sec)


# ---------------------------------------------------------------------------
# advance — 포즈 적분
# ---------------------------------------------------------------------------


def test_advance_straight_keeps_heading_and_moves_along_x() -> None:
    """좌우 델타가 같으면 방위가 유지되고 x 축으로만 이동한다."""
    state = initial_state(0, 0)
    counts = int(COUNTS_PER_WHEEL_REV)

    new_state, linear_x, angular_z = advance(state, counts, counts, GEOMETRY, 1.0)

    assert new_state.x_m == pytest.approx(WHEEL_CIRCUMFERENCE_M)
    assert new_state.y_m == pytest.approx(0.0)
    assert new_state.theta_rad == pytest.approx(0.0)
    assert linear_x == pytest.approx(WHEEL_CIRCUMFERENCE_M)
    assert angular_z == pytest.approx(0.0)


def test_advance_backward_moves_along_negative_x() -> None:
    """음의 델타는 후진이다."""
    state = initial_state(0, 0)

    new_state, linear_x, _ = advance(state, -10000, -10000, GEOMETRY, 1.0)

    assert new_state.x_m < 0.0
    assert new_state.y_m == pytest.approx(0.0)
    assert new_state.theta_rad == pytest.approx(0.0)
    assert linear_x < 0.0


def test_advance_in_place_rotation_keeps_position() -> None:
    """좌우가 반대로 같은 양이면 위치는 그대로이고 방위만 바뀐다."""
    state = initial_state(0, 0)

    new_state, linear_x, angular_z = advance(state, -1000, 1000, GEOMETRY, 0.1)

    assert new_state.x_m == pytest.approx(0.0)
    assert new_state.y_m == pytest.approx(0.0)
    assert new_state.theta_rad > 0.0  # 오른쪽이 더 가면 반시계 (REP 103)
    assert linear_x == pytest.approx(0.0)
    assert angular_z > 0.0


def test_advance_respects_existing_heading() -> None:
    """방위가 +90도면 직진은 +y 방향 이동이 된다."""
    state = OdometryState(
        x_m=0.0,
        y_m=0.0,
        theta_rad=math.pi / 2.0,
        left_count=0,
        right_count=0,
    )
    counts = int(COUNTS_PER_WHEEL_REV)

    new_state, _, _ = advance(state, counts, counts, GEOMETRY, 1.0)

    assert new_state.x_m == pytest.approx(0.0, abs=1e-12)
    assert new_state.y_m == pytest.approx(WHEEL_CIRCUMFERENCE_M)
    assert new_state.theta_rad == pytest.approx(math.pi / 2.0)


def test_advance_with_zero_delta_leaves_pose_unchanged() -> None:
    """count 가 그대로면 포즈도 속도도 변하지 않는다."""
    state = OdometryState(1.0, 2.0, 0.5, 12345, 67890)

    new_state, linear_x, angular_z = advance(state, 12345, 67890, GEOMETRY, 0.1)

    assert new_state == state
    assert linear_x == pytest.approx(0.0)
    assert angular_z == pytest.approx(0.0)


def test_advance_does_not_mutate_the_input_state() -> None:
    """frozen 상태이므로 입력은 그대로 남고 새 상태가 반환된다."""
    state = initial_state(0, 0)
    snapshot = OdometryState(
        state.x_m, state.y_m, state.theta_rad, state.left_count, state.right_count
    )

    new_state, _, _ = advance(state, 5000, 7000, GEOMETRY, 0.1)

    assert state == snapshot
    assert new_state is not state


def test_advance_updates_the_count_baseline() -> None:
    """반환된 상태는 이번에 소비한 raw count 를 다음 기준으로 들고 있다."""
    state = initial_state(10, 20)

    new_state, _, _ = advance(state, 1010, 1020, GEOMETRY, 0.1)

    assert new_state.left_count == 1010
    assert new_state.right_count == 1020


def test_advance_integrates_correctly_across_the_int32_wrap() -> None:
    """int32 경계를 넘는 샘플도 같은 크기의 일반 구간과 동일한 결과를 낸다."""
    wrapped = advance(
        initial_state(INT32_MAX - 500, INT32_MAX - 500),
        INT32_MIN + 500,
        INT32_MIN + 500,
        GEOMETRY,
        0.1,
    )[0]
    plain = advance(initial_state(0, 0), 1001, 1001, GEOMETRY, 0.1)[0]

    assert wrapped.x_m == pytest.approx(plain.x_m)
    assert wrapped.y_m == pytest.approx(plain.y_m)
    assert wrapped.x_m == pytest.approx(1001 * GEOMETRY.meters_per_count)


def test_advance_normalizes_heading_after_many_turns() -> None:
    """여러 바퀴를 돌아도 방위는 (-pi, pi] 안에 머문다."""
    state = initial_state(0, 0)
    # 한 스텝이 큰 각도를 만들도록 좌우를 크게 벌린다.
    step = 20000

    for index in range(1, 21):
        state, _, _ = advance(
            state, -step * index, step * index, GEOMETRY, 0.1
        )
        assert -math.pi < state.theta_rad <= math.pi


@pytest.mark.parametrize("dt_sec", [0.0, -1.0, float("nan")])
def test_advance_propagates_dt_validation(dt_sec: float) -> None:
    """dt 검증은 twist 계산 한 곳에만 있고 advance 는 그대로 전파한다."""
    with pytest.raises(ValueError, match="dt_sec"):
        advance(initial_state(0, 0), 100, 100, GEOMETRY, dt_sec)


def test_advance_converges_to_the_analytic_arc() -> None:
    """일정한 좌우 속도로 원호를 그리면 해석해에 수렴한다.

    좌우 바퀴 속도가 일정하면 궤적은 반지름
    `R = (L/2) * (d_r + d_l) / (d_r - d_l)` 인 정확한 원이고, 원점에서 방위 0으로
    출발해 총 `theta` 만큼 돌면 끝점은 `(R sin theta, R (1 - cos theta))` 다.

    midpoint 적분의 오차는 호 길이를 현 길이 대신 쓴 것뿐이라 스텝 각도의 제곱에
    비례해 매우 작다. 이 테스트는 그 성질을 해석해와 직접 비교해 확인한다.
    """
    left_step = 1000
    right_step = 1100
    steps = 200

    meters_per_count = GEOMETRY.meters_per_count
    left_m = left_step * meters_per_count
    right_m = right_step * meters_per_count
    delta_theta = (right_m - left_m) / WHEEL_SEPARATION_M
    radius_m = (WHEEL_SEPARATION_M / 2.0) * (right_m + left_m) / (right_m - left_m)
    total_theta = steps * delta_theta

    state = initial_state(0, 0)
    for index in range(1, steps + 1):
        state, _, _ = advance(
            state, left_step * index, right_step * index, GEOMETRY, 0.1
        )

    assert radius_m == pytest.approx(3.99)
    assert state.theta_rad == pytest.approx(total_theta)
    assert state.x_m == pytest.approx(radius_m * math.sin(total_theta), abs=1e-6)
    assert state.y_m == pytest.approx(
        radius_m * (1.0 - math.cos(total_theta)), abs=1e-6
    )


# ---------------------------------------------------------------------------
# initial_state / rebaseline
# ---------------------------------------------------------------------------


def test_initial_state_starts_at_the_origin() -> None:
    """초기 상태는 원점·무회전이고 count 기준만 채워진다."""
    state = initial_state(111, 222)

    assert (state.x_m, state.y_m, state.theta_rad) == (0.0, 0.0, 0.0)
    assert (state.left_count, state.right_count) == (111, 222)


def test_rebaseline_keeps_pose_and_replaces_counts() -> None:
    """rebaseline 은 포즈를 승계하고 count 기준만 바꾼다."""
    state = OdometryState(1.0, 2.0, 0.5, 5_000_000, 5_000_000)

    rebased = rebaseline(state, 0, 0)

    assert (rebased.x_m, rebased.y_m, rebased.theta_rad) == (1.0, 2.0, 0.5)
    assert (rebased.left_count, rebased.right_count) == (0, 0)


def test_stm_reboot_without_rebaseline_teleports_the_pose() -> None:
    """재부팅으로 count 가 0이 되면 그냥 적분할 때 포즈가 순간이동한다.

    `rebaseline()` 이 왜 필요한지를 고정하는 테스트다. 이 점프는 int32 래핑 보정으로는
    걸러지지 않는다 — 래핑 보정 입장에서는 완전히 정당한 큰 델타이기 때문이다.
    """
    state = OdometryState(1.0, 2.0, 0.0, 5_000_000, 5_000_000)

    teleported, _, _ = advance(state, 0, 0, GEOMETRY, 0.1)

    # 5,000,000 count 는 약 30m 다. 실제로는 있을 수 없는 이동이다.
    assert teleported.x_m == pytest.approx(1.0 - 5_000_000 * GEOMETRY.meters_per_count)
    assert abs(teleported.x_m - state.x_m) > 25.0


def test_rebaseline_then_advance_resumes_without_a_jump() -> None:
    """rebaseline 후 이어서 적분하면 끊긴 구간만 버리고 정상 동작한다."""
    state = OdometryState(1.0, 2.0, 0.0, 5_000_000, 5_000_000)

    rebased = rebaseline(state, 0, 0)
    resumed, linear_x, _ = advance(rebased, 1000, 1000, GEOMETRY, 0.1)

    expected_step = 1000 * GEOMETRY.meters_per_count
    assert resumed.x_m == pytest.approx(1.0 + expected_step)
    assert resumed.y_m == pytest.approx(2.0)
    assert linear_x == pytest.approx(expected_step / 0.1)


# ---------------------------------------------------------------------------
# normalize_angle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("angle_rad", "expected"),
    [
        (0.0, 0.0),
        (1.0, 1.0),
        (-1.0, -1.0),
        (math.pi, math.pi),
        (2.0 * math.pi, 0.0),
        (3.0 * math.pi, math.pi),
        (-3.0 * math.pi, math.pi),
    ],
)
def test_normalize_angle(angle_rad: float, expected: float) -> None:
    """각도는 (-pi, pi] 로 되접히며 -pi 는 +pi 로 옮겨진다."""
    assert normalize_angle(angle_rad) == pytest.approx(expected)


def test_normalize_angle_keeps_the_open_lower_bound() -> None:
    """-pi 는 범위에 포함되지 않으므로 +pi 로 바뀐다."""
    assert normalize_angle(-math.pi) == pytest.approx(math.pi)


@pytest.mark.parametrize("angle_rad", [float("nan"), float("inf"), float("-inf")])
def test_normalize_angle_propagates_non_finite(angle_rad: float) -> None:
    """비유한 각도는 예외 대신 그대로 전파된다(호출자가 판단할 몫)."""
    result = normalize_angle(angle_rad)

    assert math.isnan(result) if math.isnan(angle_rad) else result == angle_rad


# ---------------------------------------------------------------------------
# differential_drive 와의 왕복 정합
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("linear_x", "angular_z"),
    [
        (0.13, 0.0),
        (-0.13, 0.0),
        (0.0, 0.6),
        (0.0, -0.6),
        (0.3, 0.6),
        (0.1, -0.25),
    ],
)
def test_round_trip_with_differential_drive(
    linear_x: float, angular_z: float
) -> None:
    """cmd_vel -> 바퀴 각속도 -> count -> 오도메트리로 원래 twist 가 복원된다.

    두 모듈의 기구학 규약(특히 REP 103 부호와 좌우 순서)이 어긋나면 이 테스트가
    잡아낸다. count 를 정수로 반올림하므로 오차가 조금 섞이지만, 1 count 가 약 6
    마이크로미터라 허용 오차 안에서 상쇄된다.
    """
    dt_sec = 0.1

    left_rad_s, right_rad_s = cmd_vel_to_wheel_rad_s(
        linear_x, angular_z, WHEEL_RADIUS_M, WHEEL_SEPARATION_M
    )
    revolutions_to_counts = COUNTS_PER_WHEEL_REV / (2.0 * math.pi)
    left_count = round(left_rad_s * dt_sec * revolutions_to_counts)
    right_count = round(right_rad_s * dt_sec * revolutions_to_counts)

    _, recovered_linear_x, recovered_angular_z = advance(
        initial_state(0, 0), left_count, right_count, GEOMETRY, dt_sec
    )

    assert recovered_linear_x == pytest.approx(linear_x, abs=1e-3)
    assert recovered_angular_z == pytest.approx(angular_z, abs=1e-3)
