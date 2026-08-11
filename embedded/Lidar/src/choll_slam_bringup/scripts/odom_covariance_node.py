#!/usr/bin/env python3
"""Odometry 공분산 스탬퍼 — 공분산을 안 채우는 발행자 앞에 끼워 넣는 중계 노드.

## 왜 필요한가

`rf2o_laser_odometry` 는 `nav_msgs/Odometry` 의 `pose.covariance` /
`twist.covariance` 를 **전혀 채우지 않는다**(upstream `CLaserOdometry2DNode.cpp` 에
covariance 대입이 한 줄도 없다 — 2026-08-08 확인). 그 결과 36원소가 전부 0으로 나간다.

`robot_localization` EKF 는 0 을 "이 측정에는 오차가 없다"로 읽는다. 그대로 넣으면
EKF 가 rf2o 만 절대 신뢰하게 되어 융합이 성립하지 않는다.

upstream 패키지는 **직접 수정 금지**(embedded/Lidar/CLAUDE.md §5)이므로, 원본 토픽을
구독해 공분산만 찍어 다시 발행하는 얇은 중계를 둔다. 헤더·포즈·속도는 **한 값도 바꾸지
않는다** — 이 노드의 유일한 책임은 공분산이다.

## 파라미터

- `input_topic` / `output_topic` : 중계할 토픽 이름
- `pose_xy_variance` / `pose_yaw_variance` : 포즈 대각 분산
- `twist_linear_variance` / `twist_angular_variance` : 속도 대각 분산

관측되지 않는 자유도(z, roll, pitch)는 `UNOBSERVED_VARIANCE` 로 채운다. 무한대 대신
큰 유한값을 쓰는 이유는 EKF 가 행렬을 뒤집을 때 수치적으로 터지지 않게 하기 위해서다.

## 실행

    ros2 run choll_slam_bringup odom_covariance_node.py --ros-args \
      -p input_topic:=/odom_rf2o -p output_topic:=/odom_rf2o_cov
"""

import math

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node

#: 평면 차동구동에서 관측되지 않는 자유도(z, roll, pitch)에 넣는 분산.
UNOBSERVED_VARIANCE = 1e6
#: 6x6 행 우선(row-major) 공분산의 원소 수.
COVARIANCE_SIZE = 36
#: 대각 성분의 평탄화 인덱스: x, y, z, roll, pitch, yaw 순.
COVARIANCE_DIAGONAL_INDICES = (0, 7, 14, 21, 28, 35)

DEFAULT_INPUT_TOPIC = "/odom_rf2o"
DEFAULT_OUTPUT_TOPIC = "/odom_rf2o_cov"

# rf2o 기본 분산. 스캔매칭은 바퀴 슬립과 무관하므로 **각속도를 특히 신뢰**한다.
# 휠 오도메트리의 twist_angular_variance(0.25)보다 100배 작게 두어, EKF 가 yaw 를
# rf2o 에서 가져가고 휠에서는 vx 만 가져가도록 만든다 — 이것이 융합 설계의 핵심이다.
DEFAULT_POSE_XY_VARIANCE = 0.05
DEFAULT_POSE_YAW_VARIANCE = 0.05
DEFAULT_TWIST_LINEAR_VARIANCE = 0.001
DEFAULT_TWIST_ANGULAR_VARIANCE = 0.0025


def build_covariance(planar_variance: float, yaw_variance: float) -> list[float]:
    """Build a flattened 6x6 diagonal covariance for planar motion.

    Args:
        planar_variance: x·y 축 분산. 차동구동은 옆으로 미끄러지지 않으므로 두 축의
            오차 특성을 따로 측정할 근거가 없어 같은 값을 넣는다.
        yaw_variance: yaw 축 분산.

    Returns:
        36원소 행 우선 공분산. 대각 외 성분은 0이다.

    Raises:
        ValueError: 분산이 유한하지 않거나 0 이하일 때. 0 은 "오차 없음"으로 읽혀
            융합기가 이 소스만 신뢰하게 되므로 거부한다.
    """
    for name, value in (
        ("planar_variance", planar_variance),
        ("yaw_variance", yaw_variance),
    ):
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(
                f"{name} must be a finite value greater than 0.0, got {value}"
            )

    diagonal = (
        planar_variance,
        planar_variance,
        UNOBSERVED_VARIANCE,
        UNOBSERVED_VARIANCE,
        UNOBSERVED_VARIANCE,
        yaw_variance,
    )
    covariance = [0.0] * COVARIANCE_SIZE
    for index, value in zip(COVARIANCE_DIAGONAL_INDICES, diagonal, strict=True):
        covariance[index] = value
    return covariance


class OdomCovarianceNode(Node):
    """Republish an Odometry stream with a fixed diagonal covariance."""

    def __init__(self) -> None:
        """Declare parameters, build the covariances, and wire the relay."""
        super().__init__("odom_covariance")

        self.declare_parameter("input_topic", DEFAULT_INPUT_TOPIC)
        self.declare_parameter("output_topic", DEFAULT_OUTPUT_TOPIC)
        self.declare_parameter("pose_xy_variance", DEFAULT_POSE_XY_VARIANCE)
        self.declare_parameter("pose_yaw_variance", DEFAULT_POSE_YAW_VARIANCE)
        self.declare_parameter(
            "twist_linear_variance", DEFAULT_TWIST_LINEAR_VARIANCE
        )
        self.declare_parameter(
            "twist_angular_variance", DEFAULT_TWIST_ANGULAR_VARIANCE
        )

        input_topic = str(self.get_parameter("input_topic").value)
        output_topic = str(self.get_parameter("output_topic").value)
        if input_topic == output_topic:
            raise ValueError(
                "input_topic과 output_topic이 같으면 자기 자신을 무한히 되먹인다: "
                f"{input_topic}"
            )

        self._pose_covariance = build_covariance(
            float(self.get_parameter("pose_xy_variance").value),
            float(self.get_parameter("pose_yaw_variance").value),
        )
        self._twist_covariance = build_covariance(
            float(self.get_parameter("twist_linear_variance").value),
            float(self.get_parameter("twist_angular_variance").value),
        )

        self._publisher = self.create_publisher(Odometry, output_topic, 10)
        self._subscription = self.create_subscription(
            Odometry, input_topic, self._on_odom, 10
        )
        self._relayed = 0

        self.get_logger().info(
            f"odom 공분산 스탬퍼: {input_topic} -> {output_topic}"
        )
        self.get_logger().info(
            f"  pose  xy={self._pose_covariance[0]:.4g} "
            f"yaw={self._pose_covariance[35]:.4g}"
        )
        self.get_logger().info(
            f"  twist vx={self._twist_covariance[0]:.4g} "
            f"vyaw={self._twist_covariance[35]:.4g}"
        )

    def _on_odom(self, message: Odometry) -> None:
        """Stamp the covariance onto one message and republish it.

        헤더·포즈·속도는 건드리지 않는다 — 이 노드의 책임은 공분산 하나다.

        Args:
            message: 원본 오도메트리 메시지.
        """
        message.pose.covariance = list(self._pose_covariance)
        message.twist.covariance = list(self._twist_covariance)
        self._publisher.publish(message)

        self._relayed += 1
        if self._relayed % 200 == 0:
            self.get_logger().info(
                f"중계 {self._relayed}건", throttle_duration_sec=10.0
            )


def main() -> None:
    """Spin the covariance stamper until shutdown."""
    rclpy.init()
    node = OdomCovarianceNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
