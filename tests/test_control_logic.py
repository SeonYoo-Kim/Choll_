"""Unit tests for pure control logic in control_node (no ROS required)."""

import importlib

import pytest

control_node = importlib.import_module("control_node")
normalize_center_x = control_node.normalize_center_x
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


class TestPidReset:
    def test_reset_clears_integral_and_derivative_state(self):
        pid = PID(kp=0.0, ki=1.0, kd=1.0, output_limit=100.0)
        pid.compute(error=5.0, dt=1.0)   # integral = 5, prev_error = 5
        pid.reset()
        # After reset the controller must behave as if freshly constructed.
        assert pid.compute(error=1.0, dt=1.0) == pytest.approx(1.0 + 1.0)  # ki*1 + kd*(1-0)/1
