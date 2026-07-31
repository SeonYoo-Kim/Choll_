"""Unit tests for map-frame target position math (no ROS required)."""

import importlib
import math

import pytest

target_position_node = importlib.import_module("target_position_node")
robot_frame_bearing = target_position_node.robot_frame_bearing
target_position_in_map = target_position_node.target_position_in_map
yaw_from_quaternion = target_position_node.yaw_from_quaternion


class TestYawFromQuaternion:
    def test_identity_quaternion_is_zero_yaw(self):
        assert yaw_from_quaternion(0.0, 0.0, 0.0, 1.0) == pytest.approx(0.0)

    def test_quarter_turn_left(self):
        # z축 +90° 회전: q = (0, 0, sin45°, cos45°)
        half = math.sin(math.pi / 4)
        yaw = yaw_from_quaternion(0.0, 0.0, half, half)
        assert yaw == pytest.approx(math.pi / 2)

    def test_half_turn(self):
        assert yaw_from_quaternion(0.0, 0.0, 1.0, 0.0) == pytest.approx(math.pi)

    def test_clockwise_turn_is_negative(self):
        half = math.sin(math.pi / 4)
        yaw = yaw_from_quaternion(0.0, 0.0, -half, half)
        assert yaw == pytest.approx(-math.pi / 2)


class TestRobotFrameBearing:
    def test_center_is_zero(self):
        assert robot_frame_bearing(0.0, 58.0) == pytest.approx(0.0)

    def test_right_edge_is_negative_half_fov(self):
        # 화면 오른쪽(+x) 타겟 = 로봇 기준 시계 방향(음수). REP 103.
        assert robot_frame_bearing(1.0, 58.0) == pytest.approx(math.radians(-29.0))

    def test_left_edge_is_positive_half_fov(self):
        assert robot_frame_bearing(-1.0, 58.0) == pytest.approx(math.radians(29.0))


class TestTargetPositionInMap:
    def test_facing_east_target_ahead(self):
        # 카트 (1,2)에서 동쪽(yaw=0)을 보고 정면 2m → (3, 2)
        x, y = target_position_in_map(1.0, 2.0, 0.0, 0.0, 2.0)
        assert (x, y) == (pytest.approx(3.0), pytest.approx(2.0))

    def test_facing_north_target_ahead(self):
        # 북쪽(yaw=90°)을 보고 정면 2m → y가 +2
        x, y = target_position_in_map(1.0, 2.0, math.pi / 2, 0.0, 2.0)
        assert (x, y) == (pytest.approx(1.0), pytest.approx(4.0))

    def test_bearing_adds_to_yaw(self):
        # 동쪽을 보는데 타겟이 왼쪽 90°(bearing=+90°) → 북쪽 2m
        x, y = target_position_in_map(0.0, 0.0, 0.0, math.pi / 2, 2.0)
        assert (x, y) == (pytest.approx(0.0), pytest.approx(2.0))

    def test_screen_right_target_while_facing_north(self):
        # 북쪽을 보는데 화면 오른쪽 끝(bearing=-29°) 1m
        bearing = robot_frame_bearing(1.0, 58.0)
        x, y = target_position_in_map(0.0, 0.0, math.pi / 2, bearing, 1.0)
        # 북쪽에서 시계로 29° → 동쪽 성분 +sin(29°), 북쪽 성분 +cos(29°)
        assert x == pytest.approx(math.sin(math.radians(29.0)))
        assert y == pytest.approx(math.cos(math.radians(29.0)))

    def test_zero_distance_is_cart_position(self):
        x, y = target_position_in_map(5.0, -3.0, 1.234, 0.5, 0.0)
        assert (x, y) == (pytest.approx(5.0), pytest.approx(-3.0))
