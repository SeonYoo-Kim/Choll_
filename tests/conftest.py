"""Test bootstrap: stub ROS modules so pure logic can be imported without a ROS install.

These tests exercise framework-independent algorithm code (e.g. the PID controller)
by injecting minimal stand-ins for `rclpy` and the ROS message packages into
``sys.modules`` before the node module is imported. No GPU, TensorRT, or ROS
runtime is required.
"""

import sys
import types
from pathlib import Path

# Make the ROS2 node package importable by file path.
NODE_DIR = (
    Path(__file__).resolve().parents[1]
    / "ai"
    / "src"
    / "person_follow_robot"
    / "person_follow_robot"
)
sys.path.insert(0, str(NODE_DIR))


def _stub(name: str, **attrs: object) -> types.ModuleType:
    """Register a stub module under ``name`` with the given attributes."""
    module = sys.modules.get(name) or types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


# rclpy + rclpy.node.Node (Node used only as a base class we never instantiate here).
_stub(
    "rclpy",
    init=lambda *a, **k: None,
    spin=lambda *a, **k: None,
    shutdown=lambda *a, **k: None,
)
_stub("rclpy.node", Node=type("Node", (), {}))

# ROS message packages referenced at import time by the node modules.
for pkg in ("std_msgs", "sensor_msgs", "geometry_msgs", "vision_msgs"):
    _stub(pkg)
    _stub(
        f"{pkg}.msg",
        Float32MultiArray=type("Float32MultiArray", (), {}),
        Int32MultiArray=type("Int32MultiArray", (), {}),
        LaserScan=type("LaserScan", (), {}),
        Twist=type("Twist", (), {}),
        Image=type("Image", (), {}),
        Int32=type("Int32", (), {}),
        String=type("String", (), {}),
        Detection2D=type("Detection2D", (), {}),
        Detection2DArray=type("Detection2DArray", (), {}),
        ObjectHypothesisWithPose=type("ObjectHypothesisWithPose", (), {}),
    )
