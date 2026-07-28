"""Unit tests for pure control logic in control_node (no ROS required)."""

import importlib
import math
from types import SimpleNamespace

import pytest

control_node = importlib.import_module("control_node")
normalize_center_x = control_node.normalize_center_x
camera_bearing_to_lidar_angle = control_node.camera_bearing_to_lidar_angle
bbox_half_span_rad = control_node.bbox_half_span_rad
min_valid_range_in_span = control_node.min_valid_range_in_span
PID = control_node.PID


def make_scan(ranges, angle_min=-math.pi, range_min=0.1, range_max=10.0):
    """360° LaserScan 대역: angle_increment는 광선 수로부터 계산."""
    return SimpleNamespace(
        ranges=list(ranges),
        angle_min=angle_min,
        angle_increment=2.0 * math.pi / len(ranges),
        range_min=range_min,
        range_max=range_max,
    )


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

    def test_mirrored_center_is_still_zero(self):
        # 중앙은 거울 반전의 대칭점이라 mirrored 여부와 무관하게 0이어야 한다.
        assert camera_bearing_to_lidar_angle(0.0, 58.0, mirrored=True) == (
            pytest.approx(0.0)
        )

    def test_mirrored_flips_left_right(self):
        # 각도 축이 시계 +인 LiDAR에서는 화면 오른쪽 타겟이 +각도로 잡힌다.
        expected = math.radians(29.0)
        assert camera_bearing_to_lidar_angle(1.0, 58.0, mirrored=True) == (
            pytest.approx(expected)
        )
        assert camera_bearing_to_lidar_angle(-1.0, 58.0, mirrored=True) == (
            pytest.approx(-expected)
        )

    def test_mirror_applies_before_mount_offset(self):
        # 반전은 방위각에만 적용되고, 장착 오프셋은 LiDAR 각도 축 기준 그대로 뺀다.
        angle = camera_bearing_to_lidar_angle(
            1.0, 58.0, lidar_yaw_offset_deg=10.0, mirrored=True
        )
        assert angle == pytest.approx(math.radians(29.0 - 10.0))


class TestBboxHalfSpanRad:
    def test_full_width_bbox_is_half_fov(self):
        assert bbox_half_span_rad(640.0, 640, 58.0) == (
            pytest.approx(math.radians(29.0))
        )

    def test_half_width_bbox_is_quarter_fov(self):
        assert bbox_half_span_rad(320.0, 640, 58.0) == (
            pytest.approx(math.radians(14.5))
        )

    def test_oversized_and_negative_widths_are_clamped(self):
        assert bbox_half_span_rad(900.0, 640, 58.0) == (
            pytest.approx(math.radians(29.0))
        )
        assert bbox_half_span_rad(-10.0, 640, 58.0) == pytest.approx(0.0)

    def test_non_positive_image_width_raises(self):
        with pytest.raises(ValueError):
            bbox_half_span_rad(100.0, 0, 58.0)


class TestMinValidRangeInSpan:
    def test_picks_nearest_surface_in_span(self):
        # 사람(2.0m)과 배경(7.3m) 광선이 섞이면 더 가까운 사람 쪽을 골라야 한다.
        ranges = [7.3] * 360
        ranges[180] = 2.0  # angle_min=-π 기준 index 180 = 0 rad(정면)
        scan = make_scan(ranges)
        distance = min_valid_range_in_span(scan, 0.0, math.radians(5.0))
        assert distance == pytest.approx(2.0)

    def test_survives_partial_dropout(self):
        # 조회 창 일부가 무효(0.0)여도 나머지 유효 광선으로 거리를 얻는다.
        ranges = [0.0] * 360
        ranges[183] = 2.1  # 중심에서 +3° 옆 광선만 살아있음
        scan = make_scan(ranges)
        distance = min_valid_range_in_span(scan, 0.0, math.radians(5.0))
        assert distance == pytest.approx(2.1)

    def test_all_invalid_returns_none(self):
        scan = make_scan([0.0] * 360)
        assert min_valid_range_in_span(scan, 0.0, math.radians(5.0)) is None

    def test_none_scan_returns_none(self):
        assert min_valid_range_in_span(None, 0.0, 1.0) is None

    def test_wraps_around_scan_boundary(self):
        # angle_min=-π 스캔에서 ±π 부근(index 0/359 경계)을 조회하면 순환해야 한다.
        ranges = [7.0] * 360
        ranges[359] = 1.5  # 경계 반대쪽 광선
        scan = make_scan(ranges)
        distance = min_valid_range_in_span(scan, math.pi, math.radians(3.0))
        assert distance == pytest.approx(1.5)

    def test_zero_span_still_uses_min_window(self):
        # 반폭 0이어도 최소 ±min_window 인덱스는 본다 (구버전 ±2 동작 보존).
        ranges = [0.0] * 360
        ranges[182] = 3.0  # 중심에서 +2 인덱스
        scan = make_scan(ranges)
        assert min_valid_range_in_span(scan, 0.0, 0.0) == pytest.approx(3.0)

    def test_out_of_range_values_are_filtered(self):
        # range_max 이상(무한대 포함)과 range_min 이하 값은 무효 처리.
        ranges = [float("inf")] * 360
        ranges[180] = 0.05  # range_min(0.1) 미만
        scan = make_scan(ranges)
        assert min_valid_range_in_span(scan, 0.0, math.radians(2.0)) is None


class TestPidReset:
    def test_reset_clears_integral_and_derivative_state(self):
        pid = PID(kp=0.0, ki=1.0, kd=1.0, output_limit=100.0)
        pid.compute(error=5.0, dt=1.0)   # integral = 5, prev_error = 5
        pid.reset()
        # After reset the controller must behave as if freshly constructed.
        # expected = ki*1 + kd*(1-0)/1
        assert pid.compute(error=1.0, dt=1.0) == pytest.approx(1.0 + 1.0)
