"""Unit tests for the differential-drive math in motor_node (no ROS required)."""

import importlib
import math

import pytest

motor_node = importlib.import_module("motor_node")
cmd_vel_to_wheel_rpms = motor_node.cmd_vel_to_wheel_rpms

R = 0.065  # 바퀴 반지름 (m) — 실제 하드웨어 값
L = 0.30  # 바퀴 간 거리 (m) — 조립 전 가정값 (로직 검증에는 영향 없음)


def mps_to_rpm(v: float) -> float:
    return v / (2 * math.pi * R) * 60


class TestStraightLine:
    def test_forward_gives_equal_positive_rpms(self):
        left, right = cmd_vel_to_wheel_rpms(0.5, 0.0, R, L, max_rpm=1000)
        assert left == right == round(mps_to_rpm(0.5))  # 0.5 m/s ≈ 73 RPM

    def test_backward_gives_equal_negative_rpms(self):
        left, right = cmd_vel_to_wheel_rpms(-0.5, 0.0, R, L, max_rpm=1000)
        assert left == right == -round(mps_to_rpm(0.5))


class TestRotation:
    def test_left_turn_makes_right_wheel_faster(self):
        # REP 103: +ω = 반시계(좌회전) → 오른쪽 바퀴가 더 빨라야 함.
        left, right = cmd_vel_to_wheel_rpms(0.3, 1.0, R, L, max_rpm=1000)
        assert right > left

    def test_spin_in_place_wheels_are_opposite(self):
        left, right = cmd_vel_to_wheel_rpms(0.0, 2.0, R, L, max_rpm=1000)
        assert left == -right
        assert right > 0  # 좌회전이므로 오른쪽 바퀴가 전진 방향


class TestClamping:
    def test_peak_clamped_to_max_rpm(self):
        left, right = cmd_vel_to_wheel_rpms(10.0, 0.0, R, L, max_rpm=150)
        assert left == right == 150

    def test_clamp_preserves_left_right_ratio(self):
        # 클램핑이 좌우 비율(=선회 반경)을 깨면 로봇 궤적이 달라진다.
        raw_l, raw_r = cmd_vel_to_wheel_rpms(1.0, 2.0, R, L, max_rpm=10_000)
        cl_l, cl_r = cmd_vel_to_wheel_rpms(1.0, 2.0, R, L, max_rpm=100)
        assert max(abs(cl_l), abs(cl_r)) == 100
        assert cl_l / cl_r == pytest.approx(raw_l / raw_r, abs=0.02)

    def test_zero_command_is_zero(self):
        assert cmd_vel_to_wheel_rpms(0.0, 0.0, R, L, max_rpm=100) == (0, 0)


class TestValidation:
    def test_non_positive_radius_raises(self):
        with pytest.raises(ValueError):
            cmd_vel_to_wheel_rpms(0.1, 0.0, 0.0, L, max_rpm=100)

    def test_non_positive_separation_raises(self):
        with pytest.raises(ValueError):
            cmd_vel_to_wheel_rpms(0.1, 0.0, R, -0.1, max_rpm=100)

    def test_negative_max_rpm_raises(self):
        with pytest.raises(ValueError):
            cmd_vel_to_wheel_rpms(0.1, 0.0, R, L, max_rpm=-1)
