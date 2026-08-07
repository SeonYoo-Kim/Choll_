#!/usr/bin/env python3
"""카트 자기차폐 섹터를 각도로 마스킹해 재발행하는 노드.

왜 드라이버(`ignore_array`)가 아니라 별도 노드인가 — 2026-08-07 실측:

드라이버 `ignore_array`로 마스킹하면 스캔의 19.9%가 무효가 되고, rf2o가
range 이미지 경계에서 허위 gradient를 만들어 **정지 상태에서 −0.4 deg/s**
드리프트를 낸다(`S2_drift.log`). 마스킹을 끄면 같은 조건에서 yaw가 진동만
하고 누적되지 않는다(`S2_drift_nomask.log`). 구조물 포인트는 센서 좌표계에서
완전히 고정이라 스캔매칭을 붙잡아 주는 역할을 하고 있었다.

반면 slam_toolbox·Nav2는 구조물을 **반드시 걸러야** 한다. 0.12~0.46 m 포인트는
`base_link` 기준 footprint 안쪽이라 지도에 영구 장애물로 박히고 Nav2 local
costmap이 로봇을 상시 장애물로 둘러싼다.

거리 기반 필터(`min_laser_range` / `obstacle_min_range`)는 쓸 수 없다 —
도서관 서가 통로에서 서가 자체가 라이다에서 0.3~0.4 m 거리라 벽이 지워진다.
구조물은 특정 각도 섹터에만 있으므로 **각도로만** 잘라야 한다.

그래서 배선을 이렇게 나눈다::

    드라이버 → /scan_raw ──→ rf2o          (전체 스캔 → 드리프트 0)
                    └→ 이 노드 → /scan → slam_toolbox / Nav2 / AI

`/scan`이 계약 토픽(docs/ROS2_API.md, ~11 Hz, BestEffort)이므로 마스킹된 쪽이
`/scan`을 유지한다. 구독 측 변경은 없다.

마스킹 값은 NaN이다. 0.0은 Nav2가 range_min 미만으로 무시하지만 rf2o처럼
0을 유효값으로 오해하는 소비자가 있을 수 있고, inf는 Nav2 obstacle_layer가
`range_max - eps`로 바꿔 **raytrace 클리어링**을 유발해 그 방향의 실제
장애물을 지운다. NaN은 laser_geometry·RViz·costmap 모두 그냥 버린다.
"""

import math

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan

# 2026-08-07 실측 자기차폐 섹터(도). 여유각 ±2° 포함, 병합·정렬된 쌍.
# 근거: 200스캔 시간 지속성 + 10분 간격 2회 측정 교차검증 (tests/TEST_LOG.md).
#   -179..-173° 0.454 m | -161..-160° 0.121 | -157..-148° 0.128 | -138° 0.185
#    -88..-86°  0.170   |  -81..-77°  0.131 |  -74..-73°  0.136 (좌 기둥 2개)
#    +73..+74°  0.143   |  +79..+80°  0.141 (우 기둥 2개)
#   +165..+167° 0.185   | +178..+180° 0.459
DEFAULT_MASK_DEG = [
    -180.0,
    -171.0,
    -163.0,
    -146.0,
    -140.0,
    -136.0,
    -90.0,
    -71.0,
    71.0,
    82.0,
    163.0,
    169.0,
    176.0,
    180.0,
]


class ScanMaskNode(Node):
    """`input_topic`을 받아 지정 각도 섹터를 NaN으로 만들어 `output_topic`에 낸다."""

    def __init__(self) -> None:
        """파라미터를 읽고 마스킹 섹터 쌍을 검증한 뒤 pub/sub을 만든다."""
        super().__init__("scan_mask_node")
        self.declare_parameter("input_topic", "/scan_raw")
        self.declare_parameter("output_topic", "/scan")
        self.declare_parameter("mask_deg", DEFAULT_MASK_DEG)

        self._input_topic = str(self.get_parameter("input_topic").value)
        self._output_topic = str(self.get_parameter("output_topic").value)
        mask = [float(v) for v in self.get_parameter("mask_deg").value]
        if len(mask) % 2 != 0:
            raise ValueError(f"mask_deg는 쌍이어야 한다 (현재 {len(mask)}개)")
        self._pairs: list[tuple[float, float]] = [
            (mask[i], mask[i + 1]) for i in range(0, len(mask), 2)
        ]

        # 스캔 기하가 바뀔 때만 인덱스를 다시 계산한다 (라이다는 세션마다
        # angle_increment가 조금씩 다르다 — 0.8200° / 0.8392° 실측).
        self._geom: tuple[int, float, float] | None = None
        self._mask_idx: list[int] = []
        self._reported = False

        self._pub = self.create_publisher(
            LaserScan, self._output_topic, qos_profile_sensor_data
        )
        self._sub = self.create_subscription(
            LaserScan, self._input_topic, self._on_scan, qos_profile_sensor_data
        )
        self.get_logger().info(
            f"scan_mask_node: {self._input_topic} -> {self._output_topic}, "
            f"섹터 {len(self._pairs)}개 {self._pairs}"
        )

    def _rebuild_index(self, msg: LaserScan) -> None:
        """스캔 기하에 맞춰 마스킹할 빔 인덱스를 미리 계산한다."""
        idx: list[int] = []
        for i in range(len(msg.ranges)):
            deg = math.degrees(msg.angle_min + i * msg.angle_increment)
            deg = ((deg + 180.0) % 360.0) - 180.0
            if any(lo <= deg <= hi for lo, hi in self._pairs):
                idx.append(i)
        self._mask_idx = idx
        self._geom = (len(msg.ranges), msg.angle_min, msg.angle_increment)
        self.get_logger().info(
            f"마스킹 인덱스 재계산: {len(idx)}/{len(msg.ranges)} 빔 "
            f"({100.0 * len(idx) / max(1, len(msg.ranges)):.1f}%), "
            f"inc={math.degrees(msg.angle_increment):.4f}deg"
        )

    def _on_scan(self, msg: LaserScan) -> None:
        """섹터를 NaN으로 바꿔 재발행한다."""
        geom = (len(msg.ranges), msg.angle_min, msg.angle_increment)
        if self._geom != geom:
            self._rebuild_index(msg)

        ranges = list(msg.ranges)
        n = len(ranges)
        for i in self._mask_idx:
            if i < n:
                ranges[i] = math.nan
        msg.ranges = ranges
        if msg.intensities:
            inten = list(msg.intensities)
            for i in self._mask_idx:
                if i < len(inten):
                    inten[i] = 0.0
            msg.intensities = inten
        self._pub.publish(msg)

        if not self._reported:
            self._reported = True
            self.get_logger().info("첫 스캔 마스킹·재발행 완료")


def main() -> None:
    """노드를 실행한다."""
    rclpy.init()
    node = ScanMaskNode()
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
