"""Unit tests for pure control logic in control_node (no ROS required)."""

import importlib
import math

import pytest

control_node = importlib.import_module("control_node")
normalize_center_x = control_node.normalize_center_x
camera_bearing_to_lidar_angle = control_node.camera_bearing_to_lidar_angle
PID = control_node.PID


class TestNormalizeCenterX:
    def test_image_center_maps_to_zero(self):
        assert normalize_center_x(320.0, 640) == pytest.approx(0.0)

    def test_left_edge_maps_to_minus_one(self):
        assert normalize_center_x(0.0, 640) == pytest.approx(-1.0)

    def test_right_edge_maps_to_plus_one(self):
        assert normalize_center_x(640.0, 640) == pytest.approx(1.0)

    def test_quarter_position(self):
        # 160px on a 640px image = halfway between left edge and center.
        assert normalize_center_x(160.0, 640) == pytest.approx(-0.5)

    def test_out_of_frame_is_clamped(self):
        # A bbox center slightly outside the frame must not exceed [-1, 1].
        assert normalize_center_x(700.0, 640) == pytest.approx(1.0)
        assert normalize_center_x(-60.0, 640) == pytest.approx(-1.0)

    def test_non_positive_width_raises(self):
        with pytest.raises(ValueError):
            normalize_center_x(100.0, 0)


class TestCameraBearingToLidarAngle:
    def test_center_maps_to_zero(self):
        assert camera_bearing_to_lidar_angle(0.0, 58.0) == pytest.approx(0.0)

    def test_right_edge_is_negative_half_fov(self):
        # 화면 오른쪽(+x)의 타겟은 REP 103 기준 음의 방위각(시계 방향).
        expected = math.radians(-29.0)
        assert camera_bearing_to_lidar_angle(1.0, 58.0) == pytest.approx(expected)

    def test_left_edge_is_positive_half_fov(self):
        expected = math.radians(29.0)
        assert camera_bearing_to_lidar_angle(-1.0, 58.0) == pytest.approx(expected)

    def test_mount_offset_shifts_lookup_angle(self):
        # LiDAR 0°축이 전방에서 반시계로 90° 틀어져 장착된 경우,
        # 정면 타겟은 LiDAR 프레임 -90° 방향에서 잡힌다.
        angle = camera_bearing_to_lidar_angle(0.0, 58.0, lidar_yaw_offset_deg=90.0)
        assert angle == pytest.approx(math.radians(-90.0))


class TestPidReset:
    def test_reset_clears_integral_and_derivative_state(self):
        pid = PID(kp=0.0, ki=1.0, kd=1.0, output_limit=100.0)
        pid.compute(error=5.0, dt=1.0)   # integral = 5, prev_error = 5
        pid.reset()
        # After reset the controller must behave as if freshly constructed.
        # expected = ki*1 + kd*(1-0)/1
        assert pid.compute(error=1.0, dt=1.0) == pytest.approx(1.0 + 1.0)
