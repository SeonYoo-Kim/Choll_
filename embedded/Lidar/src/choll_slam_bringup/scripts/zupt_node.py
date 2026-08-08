#!/usr/bin/env python3
"""ZUPT (zero-velocity update) — 엔코더가 멈춰 있으면 "안 움직였다"를 EKF 에 알린다.

## 왜 필요한가 (2026-08-09 실기)

지도 상 위치는 모터가 아니라 **라이다 스캔매칭(rf2o)** 이 만든다. 연속 스캔을 비교해
이동량을 추정하므로, 스캔이 애매하면 **정지 상태에서도 움직였다고 보고**한다.
실측: `/cmd_vel` 0 건인 90 초 동안 map->base_link 의 yaw 가 24° 흘렀다.

EKF 는 휠 오도메트리에서 **vx 만** 융합한다 — 휠 yaw 는 좌측 구동 슬립(전진 4.79% /
후진 11.86%) 때문에 못 믿기 때문이다. 그래서 yaw 를 견제할 소스가 rf2o 하나뿐이고,
rf2o 가 헛돌면 그대로 실린다.

엔코더가 **양쪽 다 정확히 0 변화**면 카트는 확실히 정지 상태다. 이건 슬립과 무관한
사실이다 — 슬립은 "바퀴는 도는데 안 나간다"이지 그 반대가 아니다. 이때만 vx=0,
vyaw=0 을 **작은 공분산**으로 넣으면 정지 중 드리프트가 잡힌다.

## 설계

- 정지 판정: 최근 `hold_sec` 동안 좌우 엔코더 델타가 모두 `count_tolerance` 이하.
- 정지일 때만 `/odom_zupt` 에 twist(0, 0) 을 발행한다. 움직이면 **아무것도 안 보낸다** —
  EKF 는 측정이 없으면 그냥 예측만 하므로 안전하다(`sensor_timeout` 이 처리).
- 포즈는 싣지 않는다(공분산 거대). 속도만 관측한다.

⚠️ 이 노드는 "정지"만 주장한다. 움직일 때의 속도는 절대 주장하지 않는다 — 그건
`wheel_odometry` 의 몫이고, 그쪽은 슬립 때문에 yaw 를 못 낸다.

실행:
    ros2 run choll_slam_bringup zupt_node.py
"""

import math
from collections import deque

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_msgs.msg import Int32MultiArray

ENCODER_TOPIC = "/stm/encoder_total"
DEFAULT_OUTPUT_TOPIC = "/odom_zupt"

#: 정지로 볼 엔코더 델타 [counts]. 68160 counts/rev 기준 1 count = 0.0000054 m 라
#: 2 counts 는 0.01 mm 수준 — 사실상 완전 정지만 통과시킨다.
DEFAULT_COUNT_TOLERANCE = 2
#: 이 시간 동안 계속 정지여야 ZUPT 를 발행한다 [s]. 감속 직후의 잔여 운동을 피한다.
DEFAULT_HOLD_SEC = 0.3

#: 정지 주장의 분산. sigma 0.01 m/s / 0.01 rad/s — rf2o(0.0025) 보다 훨씬 작아
#: 정지 중에는 EKF 가 이쪽을 확실히 택한다.
DEFAULT_VARIANCE = 1e-4
#: 관측하지 않는 자유도. 무한대 대신 큰 유한값 (행렬 역산 안정성).
UNOBSERVED_VARIANCE = 1e6
COVARIANCE_SIZE = 36
COVARIANCE_DIAGONAL_INDICES = (0, 7, 14, 21, 28, 35)


def build_twist_covariance(variance: float) -> list[float]:
    """Build the flattened 6x6 twist covariance for a zero-velocity claim.

    Args:
        variance: vx·vy·vyaw 에 넣을 분산. 0보다 큰 유한값이어야 한다.

    Returns:
        36원소 행 우선 공분산. 대각 외 성분은 0이다.

    Raises:
        ValueError: 분산이 유한하지 않거나 0 이하일 때. 0 은 "오차 없음"으로 읽혀
            융합기가 이 소스만 신뢰하게 된다.
    """
    if not math.isfinite(variance) or variance <= 0.0:
        raise ValueError(
            f"variance must be a finite value greater than 0.0, got {variance}"
        )
    diagonal = (
        variance,               # vx
        variance,               # vy
        UNOBSERVED_VARIANCE,    # vz
        UNOBSERVED_VARIANCE,    # vroll
        UNOBSERVED_VARIANCE,    # vpitch
        variance,               # vyaw
    )
    covariance = [0.0] * COVARIANCE_SIZE
    for index, value in zip(COVARIANCE_DIAGONAL_INDICES, diagonal, strict=True):
        covariance[index] = value
    return covariance


class ZuptNode(Node):
    """Publish a zero-velocity measurement while the encoders are static."""

    def __init__(self) -> None:
        """Declare parameters and wire the encoder subscription."""
        super().__init__("zupt")

        self.declare_parameter("output_topic", DEFAULT_OUTPUT_TOPIC)
        self.declare_parameter("count_tolerance", DEFAULT_COUNT_TOLERANCE)
        self.declare_parameter("hold_sec", DEFAULT_HOLD_SEC)
        self.declare_parameter("variance", DEFAULT_VARIANCE)
        self.declare_parameter("odom_frame_id", "odom")
        self.declare_parameter("base_frame_id", "base_link")

        self._tolerance = int(self.get_parameter("count_tolerance").value)
        self._hold_sec = float(self.get_parameter("hold_sec").value)
        self._odom_frame = str(self.get_parameter("odom_frame_id").value)
        self._base_frame = str(self.get_parameter("base_frame_id").value)
        self._twist_covariance = build_twist_covariance(
            float(self.get_parameter("variance").value)
        )
        # 포즈는 주장하지 않는다 — 전부 관측 불가로 둔다.
        self._pose_covariance = [0.0] * COVARIANCE_SIZE
        for index in COVARIANCE_DIAGONAL_INDICES:
            self._pose_covariance[index] = UNOBSERVED_VARIANCE

        output_topic = str(self.get_parameter("output_topic").value)
        self._publisher = self.create_publisher(Odometry, output_topic, 10)
        self.create_subscription(
            Int32MultiArray, ENCODER_TOPIC, self._on_encoder, 10
        )

        #: (수신시각, 좌, 우) 최근 이력. hold_sec 판정에 쓴다.
        self._history: deque[tuple[float, int, int]] = deque()
        self._published = 0
        self._was_static = False

        self.get_logger().info(
            f"ZUPT: {ENCODER_TOPIC} -> {output_topic} "
            f"(정지 판정 델타<={self._tolerance} counts, {self._hold_sec}s 유지)"
        )
        self.get_logger().info(
            "정지일 때만 vx=0·vyaw=0 을 발행한다 — "
            "움직일 때는 아무것도 주장하지 않는다."
        )

    def _now_sec(self) -> float:
        """Return the ROS clock time in seconds."""
        return self.get_clock().now().nanoseconds * 1e-9

    def _on_encoder(self, message: Int32MultiArray) -> None:
        """Decide whether the cart is static and publish a ZUPT if so.

        Args:
            message: `/stm/encoder_total` — data[0] 좌, data[1] 우 누적 카운트.
        """
        if len(message.data) < 2:
            return
        now = self._now_sec()
        self._history.append((now, int(message.data[0]), int(message.data[1])))
        while self._history and now - self._history[0][0] > self._hold_sec:
            if len(self._history) <= 1:
                break
            # 창 밖으로 나간 항목이 하나 남을 때까지만 버린다(창 전체를 비교해야 함).
            if now - self._history[1][0] > self._hold_sec:
                self._history.popleft()
            else:
                break

        oldest = self._history[0]
        if now - oldest[0] < self._hold_sec:
            return  # 아직 판정할 만큼의 이력이 없다

        left_delta = abs(self._history[-1][1] - oldest[1])
        right_delta = abs(self._history[-1][2] - oldest[2])
        is_static = (
            left_delta <= self._tolerance and right_delta <= self._tolerance
        )

        if is_static != self._was_static:
            state = "정지 — ZUPT 발행 시작" if is_static else "이동 — ZUPT 중단"
            self.get_logger().info(
                f"{state} (델타 L={left_delta} R={right_delta})"
            )
            self._was_static = is_static
        if not is_static:
            return

        odom = Odometry()
        odom.header.stamp = self.get_clock().now().to_msg()
        odom.header.frame_id = self._odom_frame
        odom.child_frame_id = self._base_frame
        # twist 는 전부 0 (기본값). 포즈도 0 이지만 공분산이 거대해 무시된다.
        odom.pose.covariance = list(self._pose_covariance)
        odom.twist.covariance = list(self._twist_covariance)
        self._publisher.publish(odom)

        self._published += 1
        if self._published % 200 == 0:
            self.get_logger().info(
                f"ZUPT {self._published}건 발행", throttle_duration_sec=10.0
            )


def main() -> None:
    """Spin the ZUPT node until shutdown."""
    rclpy.init()
    node = ZuptNode()
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
