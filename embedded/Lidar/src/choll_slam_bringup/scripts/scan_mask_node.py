#!/usr/bin/env python3
"""카트 자기차폐 포인트를 걸러 `/scan`을 재발행하는 노드.

두 가지 필터를 쓴다. 기본은 **박스 판정**이고, 각도 마스킹은 보조다.

박스 판정 (기본, 각도 무관)
---------------------------
반사점이 카트 상판 박스(`box_half_x` x `box_half_y`, laser_frame 기준) 안쪽이면
버린다. 기하학적 근거: 박스 안은 카트 자기 몸통이고, 거기에 실제 장애물이 있다면
이미 카트에 닿아 있는 상태다. 각도와 무관하므로 **카트를 옮기거나 케이블이
흘러도 재산정이 필요 없다.**

각도별 경계 거리는 ``r_box(t) = min(hx/|cos t|, hy/|sin t|)`` 이고,
전후 620 x 좌우 320 mm 기준으로 0.160 m(좌/우) ~ 0.349 m(모서리) 사이다.

왜 이 방식인가 — 2026-08-07 실측
--------------------------------
① 각도로 통째 자르면 먼 벽을 잃는다. 합판 절단면을 거의 평행하게 스치는 구간
   (좌우 55~95°)에서 **유효율 98%인 빔이 10% 확률로 0.135 m를 보고**한다
   (`S5_detail.log`의 p10 열). 그 구간을 각도로 막으면 이 장소의 가장 먼 관측
   (+58~+60° 7.7 m, +87~+91° 6.7 m)이 통째로 사라져 스캔매칭 기준을 잃는다.
② 거리로만 자르면 서가 통로에서 벽을 잃는다 (`slam_toolbox min_laser_range` /
   Nav2 `obstacle_min_range`를 0.5로 올리면 라이다에서 0.3~0.4 m인 서가가 지워짐).
③ 박스 판정은 둘을 합친 것이다. 잃는 시야가 거의 0이고 (실측: 환경 관측 316/440빔,
   최대 8.81 m 유지) 자기 구조물만 정확히 걸러진다.

왜 드라이버(`ignore_array`)가 아니라 노드인가
---------------------------------------------
드라이버에서 자르면 스캔의 19.9%가 무효가 되고 rf2o가 range 이미지 경계에서
허위 gradient를 만들어 **정지 상태에서 -0.4 deg/s** 로 드리프트한다
(`S2_drift.log`). 마스킹을 끄면 같은 조건에서 yaw가 진동만 하고 누적되지 않는다
(`S2_drift_nomask.log`). 구조물 포인트는 센서 좌표계에서 완전히 고정이라
스캔매칭을 붙잡아 주는 역할을 하고 있었다. 그래서 배선을 이렇게 나눈다::

    드라이버 → /scan_raw ──→ rf2o          (전체 스캔 → 드리프트 0)
                    └→ 이 노드 → /scan → slam_toolbox / Nav2 / AI

`/scan`이 계약 토픽(docs/ROS2_API.md, ~11 Hz, BestEffort)이므로 걸러진 쪽이
`/scan`을 유지한다. 구독 측 변경은 없다.

마스킹 값은 NaN이다. 0.0은 Nav2가 range_min 미만으로 무시하지만 rf2o처럼 0을
유효값으로 오해하는 소비자가 있을 수 있고, inf는 Nav2 obstacle_layer가
`range_max - eps`로 바꿔 **raytrace 클리어링**을 유발해 그 방향의 실제 장애물을
지운다. NaN은 laser_geometry·RViz·costmap 모두 그냥 버린다.
"""

import math

import rclpy
from rcl_interfaces.msg import ParameterDescriptor, ParameterType
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan

# 카트 본체 실측(2026-08-08 사용자 정정): **전후 620 x 좌우 320 mm**.
# 🔴 2026-08-07 에는 이 두 축이 **뒤바뀐 채로** (전후 330 / 좌우 630) 들어가 있었다.
#    사용자 표현 "가로 630 세로 330" 을 좌우/전후로 해석한 것이 원인이며,
#    실제로는 좌우가 짧고(320) 전후가 길다(620). 2026-08-08 에 바로잡았다.
#    이 정정으로 `base_link->laser_frame x=0.30` 과의 모순도 해소된다 —
#    전방 한계가 0.31 m 이므로 라이다(0.30 m)가 앞단 바로 안쪽에 놓인다.
# 라이다는 각 변의 중앙에 있다고 보고 laser_frame 기준 반깊이/반폭으로 쓴다.
DEFAULT_BOX_HALF_X = 0.31  # 전후 620 mm / 2 (전방/후방)
DEFAULT_BOX_HALF_Y = 0.16  # 좌우 320 mm / 2 (좌/우)
# 장착·측정 공차. 0.15면 좌우 경계가 0.184 m — 실측된 합판 절단면 스침
# (좌 0.15~0.19 m)을 덮는다.
DEFAULT_BOX_TOLERANCE = 0.15

# 각도 마스킹은 기본 없음. 박스 판정으로 안 잡히는 구간이 나오면 여기에 쌍으로
# 넣는다 (예: 스캔면에 걸치는 외부 부착물). 실측 근거 없이 채우지 말 것.
DEFAULT_MASK_DEG: list[float] = []


class ScanMaskNode(Node):
    """`input_topic`에서 카트 자기 구조물 반사를 걸러 `output_topic`으로 낸다."""

    def __init__(self) -> None:
        """파라미터를 읽고 검증한 뒤 pub/sub을 만든다."""
        super().__init__("scan_mask_node")
        self.declare_parameter("input_topic", "/scan_raw")
        self.declare_parameter("output_topic", "/scan")
        self.declare_parameter("box_half_x", DEFAULT_BOX_HALF_X)
        self.declare_parameter("box_half_y", DEFAULT_BOX_HALF_Y)
        self.declare_parameter("box_tolerance", DEFAULT_BOX_TOLERANCE)
        self.declare_parameter(
            "mask_deg",
            DEFAULT_MASK_DEG,
            ParameterDescriptor(type=ParameterType.PARAMETER_DOUBLE_ARRAY),
        )

        self._input_topic = str(self.get_parameter("input_topic").value)
        self._output_topic = str(self.get_parameter("output_topic").value)
        self._hx = float(self.get_parameter("box_half_x").value)
        self._hy = float(self.get_parameter("box_half_y").value)
        self._tol = float(self.get_parameter("box_tolerance").value)
        if self._hx <= 0.0 or self._hy <= 0.0:
            raise ValueError(f"box 반폭은 양수여야 한다 (x={self._hx}, y={self._hy})")

        mask = [float(v) for v in (self.get_parameter("mask_deg").value or [])]
        if len(mask) % 2 != 0:
            raise ValueError(f"mask_deg는 쌍이어야 한다 (현재 {len(mask)}개)")
        self._pairs: list[tuple[float, float]] = [
            (mask[i], mask[i + 1]) for i in range(0, len(mask), 2)
        ]

        # 스캔 기하가 바뀔 때만 다시 계산한다 (라이다는 세션마다 angle_increment가
        # 조금씩 다르다 — 0.8200 / 0.8392 deg 실측).
        self._geom: tuple[int, float, float] | None = None
        self._limits: list[float] = []  # 빔별 박스 경계 거리, 섹터 마스킹은 inf
        self._reported = False

        self._pub = self.create_publisher(
            LaserScan, self._output_topic, qos_profile_sensor_data
        )
        self._sub = self.create_subscription(
            LaserScan, self._input_topic, self._on_scan, qos_profile_sensor_data
        )
        corner = math.degrees(math.atan2(self._hy, self._hx))
        self.get_logger().info(
            f"scan_mask_node: {self._input_topic} -> {self._output_topic} | "
            f"박스 {2000 * self._hx:.0f}x{2000 * self._hy:.0f}mm 공차 +{self._tol:.0%} "
            f"→ 경계 정면 {self._box_limit(0.0):.3f} / "
            f"모서리({corner:.1f}deg) {self._box_limit(corner):.3f} / "
            f"측면 {self._box_limit(90.0):.3f} m | 섹터 마스킹 {len(self._pairs)}개"
        )

    def _box_limit(self, deg: float) -> float:
        """해당 방위각에서 "이보다 가까우면 카트 몸통" 인 거리 [m]."""
        t = math.radians(deg)
        c, s = abs(math.cos(t)), abs(math.sin(t))
        rx = self._hx / c if c > 1e-9 else math.inf
        ry = self._hy / s if s > 1e-9 else math.inf
        return min(rx, ry) * (1.0 + self._tol)

    def _rebuild(self, msg: LaserScan) -> None:
        """스캔 기하에 맞춰 빔별 컷오프 거리를 미리 계산한다."""
        limits: list[float] = []
        n_sector = 0
        for i in range(len(msg.ranges)):
            deg = math.degrees(msg.angle_min + i * msg.angle_increment)
            deg = ((deg + 180.0) % 360.0) - 180.0
            if any(lo <= deg <= hi for lo, hi in self._pairs):
                limits.append(math.inf)  # 섹터 전체 제거
                n_sector += 1
            else:
                limits.append(self._box_limit(deg))
        self._limits = limits
        self._geom = (len(msg.ranges), msg.angle_min, msg.angle_increment)
        self.get_logger().info(
            f"컷오프 재계산: {len(limits)}빔, 섹터 전체제거 {n_sector}빔, "
            f"inc={math.degrees(msg.angle_increment):.4f}deg"
        )

    def _on_scan(self, msg: LaserScan) -> None:
        """카트 박스 안쪽 반사와 섹터 마스킹 구간을 NaN으로 바꿔 재발행한다."""
        geom = (len(msg.ranges), msg.angle_min, msg.angle_increment)
        if self._geom != geom:
            self._rebuild(msg)

        ranges = list(msg.ranges)
        dropped = 0
        for i, r in enumerate(ranges):
            if i >= len(self._limits):
                break
            # NaN/inf는 비교가 False가 되어 그대로 통과한다 (이미 무효값).
            if r < self._limits[i]:
                ranges[i] = math.nan
                dropped += 1
        msg.ranges = ranges
        if msg.intensities:
            inten = list(msg.intensities)
            for i in range(min(len(inten), len(self._limits))):
                if math.isnan(ranges[i]):
                    inten[i] = 0.0
            msg.intensities = inten
        self._pub.publish(msg)

        if not self._reported:
            self._reported = True
            self.get_logger().info(f"첫 스캔 처리 완료 — 제거 {dropped}빔")


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
