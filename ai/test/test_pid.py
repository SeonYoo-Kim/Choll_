"""Unit tests for the PID controller used by control_node.

The PID class is pure Python (no ROS dependency), so we import it via the stubs
in conftest.py and verify its numeric behavior.
"""

import importlib

import pytest

control_node = importlib.import_module("control_node")
PID = control_node.PID


def test_proportional_term_only():
    pid = PID(kp=2.0, ki=0.0, kd=0.0, output_limit=100.0)
    # output = kp * error
    assert pid.compute(error=3.0, dt=0.1) == pytest.approx(6.0)


def test_output_is_clamped_to_limit():
    pid = PID(kp=1000.0, ki=0.0, kd=0.0, output_limit=0.5)
    assert pid.compute(error=10.0, dt=0.1) == pytest.approx(0.5)
    assert pid.compute(error=-10.0, dt=0.1) == pytest.approx(-0.5)


def test_integral_accumulates_over_time():
    pid = PID(kp=0.0, ki=1.0, kd=0.0, output_limit=100.0)
    first = pid.compute(error=1.0, dt=1.0)   # integral = 1.0
    second = pid.compute(error=1.0, dt=1.0)  # integral = 2.0
    assert first == pytest.approx(1.0)
    assert second == pytest.approx(2.0)


def test_derivative_responds_to_error_change():
    pid = PID(kp=0.0, ki=0.0, kd=2.0, output_limit=100.0)
    pid.compute(error=0.0, dt=1.0)               # prev_error = 0
    out = pid.compute(error=1.0, dt=1.0)         # derivative = (1-0)/1 = 1
    assert out == pytest.approx(2.0)


def test_zero_dt_disables_derivative():
    pid = PID(kp=0.0, ki=0.0, kd=5.0, output_limit=100.0)
    # dt == 0 must not raise ZeroDivisionError; derivative treated as 0.
    assert pid.compute(error=1.0, dt=0.0) == pytest.approx(0.0)
