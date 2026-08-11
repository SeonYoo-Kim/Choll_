"""nav_logic 순수 함수 단위 테스트 (ROS 불필요)."""

import math

import pytest

from choll_nav.nav_logic import (
    compute_approach_point,
    heading_between,
    make_goal_pose_2d,
    orientation_is_unset,
    should_send_goal,
    yaw_to_quaternion,
)

IDENTITY = (0.0, 0.0, 0.0, 1.0)
ALL_ZERO = (0.0, 0.0, 0.0, 0.0)


class TestYawToQuaternion:
    """yaw_to_quaternion 검증."""

    def test_zero_yaw_is_identity(self) -> None:
        """Yaw 0은 항등 쿼터니언."""
        assert yaw_to_quaternion(0.0) == pytest.approx(IDENTITY)

    def test_quarter_turn(self) -> None:
        """Yaw 90°는 z=sin(45°), w=cos(45°)."""
        x, y, z, w = yaw_to_quaternion(math.pi / 2)
        assert (x, y) == (0.0, 0.0)
        assert z == pytest.approx(math.sin(math.pi / 4))
        assert w == pytest.approx(math.cos(math.pi / 4))

    def test_negative_yaw_roundtrip(self) -> None:
        """음수 yaw도 atan2 복원으로 왕복 일치."""
        yaw = -2.2
        x, y, z, w = yaw_to_quaternion(yaw)
        recovered = 2.0 * math.atan2(z, w)
        assert recovered == pytest.approx(yaw)


class TestHeadingBetween:
    """heading_between 4사분면 검증."""

    @pytest.mark.parametrize(
        ("to_x", "to_y", "expected"),
        [
            (1.0, 0.0, 0.0),
            (0.0, 1.0, math.pi / 2),
            (-1.0, 0.0, math.pi),
            (0.0, -1.0, -math.pi / 2),
        ],
    )
    def test_quadrants(self, to_x: float, to_y: float, expected: float) -> None:
        """축 방향 4개가 기대 각도와 일치."""
        assert heading_between(0.0, 0.0, to_x, to_y) == pytest.approx(expected)

    def test_coincident_points(self) -> None:
        """같은 점이면 atan2(0,0)=0 (예외 없음)."""
        assert heading_between(1.0, 1.0, 1.0, 1.0) == 0.0


class TestOrientationIsUnset:
    """orientation_is_unset 판정 검증."""

    def test_all_zero_is_unset(self) -> None:
        """메시지 기본값(전부 0)은 미지정."""
        assert orientation_is_unset(*ALL_ZERO) is True

    def test_identity_is_unset(self) -> None:
        """항등 회전도 미지정으로 본다."""
        assert orientation_is_unset(*IDENTITY) is True

    def test_explicit_rotation_is_set(self) -> None:
        """90° 회전은 지정된 방향."""
        quat = yaw_to_quaternion(math.pi / 2)
        assert orientation_is_unset(*quat) is False

    def test_near_identity_within_eps(self) -> None:
        """Eps 이내의 근사 항등은 미지정."""
        assert orientation_is_unset(1e-8, -1e-8, 1e-8, 1.0 - 1e-8) is True


class TestComputeApproachPoint:
    """compute_approach_point 검증."""

    def test_straight_ahead(self) -> None:
        """2m 전방 목표, 유지 1m → 1m 지점."""
        assert compute_approach_point(0.0, 0.0, 2.0, 0.0, 1.0) == pytest.approx(
            (1.0, 0.0)
        )

    def test_zero_distance_returns_target(self) -> None:
        """Approach 0이면 목표 그대로."""
        assert compute_approach_point(0.0, 0.0, 2.0, 3.0, 0.0) == (2.0, 3.0)

    def test_diagonal(self) -> None:
        """대각 방향에서도 목표 앞 1m."""
        gx, gy = compute_approach_point(0.0, 0.0, 3.0, 4.0, 1.0)
        # 목표까지 5m, 방향 (0.6, 0.8) → 4m 지점 = (2.4, 3.2)
        assert (gx, gy) == pytest.approx((2.4, 3.2))

    def test_inside_standoff_returns_robot(self) -> None:
        """목표가 유지 거리 안쪽이면 로봇 위치 반환 (전진 금지)."""
        assert compute_approach_point(1.0, 1.0, 1.3, 1.0, 1.0) == (1.0, 1.0)

    def test_robot_equals_target(self) -> None:
        """로봇=목표면 목표 그대로 (0 나눗셈 없음)."""
        assert compute_approach_point(2.0, 2.0, 2.0, 2.0, 1.0) == (2.0, 2.0)


class TestShouldSendGoal:
    """should_send_goal 스로틀 검증."""

    def test_first_goal_always_sent(self) -> None:
        """기록이 없으면 무조건 전송."""
        assert should_send_goal((1.0, 1.0), 0.0, None, None, False, 1.0, 0.3)

    def test_interval_applies_even_when_idle(self) -> None:
        """상태 무관 최소 간격 — 응답 대기 창 버스트·플래핑 방지."""
        assert not should_send_goal(
            (5.0, 5.0), 0.1, (1.0, 1.0), 0.0, False, 1.0, 0.3
        )

    def test_failure_state_resend_after_interval(self) -> None:
        """실패/유휴 상태에서 간격만 지나면 같은 지점 재지시 허용."""
        assert should_send_goal(
            (1.0, 1.0), 1.5, (1.0, 1.0), 0.0, False, 1.0, 0.3
        )

    def test_after_success_same_spot_blocked(self) -> None:
        """성공 직후 같은 지점(이동 미달)은 간격이 지나도 차단 — 플래핑 방지."""
        assert not should_send_goal(
            (1.0, 1.0),
            5.0,
            (1.0, 1.0),
            0.0,
            False,
            1.0,
            0.3,
            after_success=True,
        )

    def test_after_success_moved_target_sent(self) -> None:
        """성공 후라도 목표가 충분히 이동했으면 전송."""
        assert should_send_goal(
            (2.0, 1.0),
            5.0,
            (1.0, 1.0),
            0.0,
            False,
            1.0,
            0.3,
            after_success=True,
        )

    def test_navigating_too_soon(self) -> None:
        """주행 중 + 충분히 이동했지만 간격 미달 → 차단."""
        assert not should_send_goal(
            (2.0, 1.0), 0.5, (1.0, 1.0), 0.0, True, 1.0, 0.3
        )

    def test_navigating_too_close(self) -> None:
        """주행 중 + 간격 충분하지만 이동 거리 미달 → 차단."""
        assert not should_send_goal(
            (1.1, 1.0), 5.0, (1.0, 1.0), 0.0, True, 1.0, 0.3
        )

    def test_navigating_both_conditions_met(self) -> None:
        """주행 중 + 간격·이동 모두 충족 → 전송."""
        assert should_send_goal(
            (2.0, 1.0), 2.0, (1.0, 1.0), 0.0, True, 1.0, 0.3
        )

    def test_exact_boundaries_pass(self) -> None:
        """경계값(정확히 간격·거리 일치)은 전송."""
        assert should_send_goal(
            (1.3, 1.0), 1.0, (1.0, 1.0), 0.0, True, 1.0, 0.3
        )


class TestMakeGoalPose2d:
    """make_goal_pose_2d 합성 검증."""

    def test_explicit_orientation_kept(self) -> None:
        """명시된 방향은 auto_orient가 켜져 있어도 유지."""
        quat_in = yaw_to_quaternion(1.0)
        _, _, quat = make_goal_pose_2d(
            (0.0, 0.0), (2.0, 0.0), quat_in, 0.0, True
        )
        assert quat == quat_in

    def test_auto_orient_uses_raw_target(self) -> None:
        """Approach 오프셋이 있어도 방향은 원시 목표 기준."""
        gx, gy, quat = make_goal_pose_2d(
            (0.0, 0.0), (0.0, 2.0), ALL_ZERO, 1.0, True
        )
        assert (gx, gy) == pytest.approx((0.0, 1.0))
        yaw = 2.0 * math.atan2(quat[2], quat[3])
        assert yaw == pytest.approx(math.pi / 2)

    def test_auto_orient_off_keeps_input(self) -> None:
        """auto_orient 꺼짐 → 미지정 방향도 그대로."""
        _, _, quat = make_goal_pose_2d(
            (0.0, 0.0), (2.0, 0.0), ALL_ZERO, 0.0, False
        )
        assert quat == ALL_ZERO

    def test_unknown_robot_skips_approach(self) -> None:
        """로봇 위치 미확보 → approach 무시, 원시 좌표 사용."""
        gx, gy, quat = make_goal_pose_2d(
            None, (2.0, 3.0), ALL_ZERO, 1.0, True
        )
        assert (gx, gy) == (2.0, 3.0)
        assert quat == IDENTITY

    def test_unknown_robot_explicit_orientation(self) -> None:
        """로봇 위치 미확보라도 명시된 방향은 유지."""
        quat_in = yaw_to_quaternion(-0.5)
        _, _, quat = make_goal_pose_2d(None, (2.0, 3.0), quat_in, 1.0, True)
        assert quat == quat_in
