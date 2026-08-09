#!/usr/bin/env python3
"""카트 자기차폐 포인트를 걸러 `/scan`을 재발행하는 노드.

두 가지 필터를 쓴다. 기본은 **박스 판정**이고, 각도 마스킹은 보조다.

박스 판정 (기본, 각도 무관)
---------------------------
반사점이 카트 몸통 박스(laser_frame 기준 `min_x..max_x` x `min_y..max_y`) 안쪽이면
버린다. 기하학적 근거: 박스 안은 카트 자기 몸통이고, 거기에 실제 장애물이 있다면
이미 카트에 닿아 있는 상태다. 각도와 무관하므로 **카트를 옮기거나 케이블이
흘러도 재산정이 필요 없다.**

각도별 경계 거리는 원점에서 나간 광선이 박스를 벗어나는 거리다::

    tx = max_x/cos t (cos t > 0) | min_x/cos t (cos t < 0)
    ty = max_y/sin t (sin t > 0) | min_y/sin t (sin t < 0)
    r_box(t) = min(tx, ty) + margin

🔴 2026-08-09 대칭 박스 -> **비대칭 박스**. 이전 구현은 laser_frame 원점을 차체
중심으로 **가정**하고 `±half_x` x `±half_y` 를 썼다. 실측 결과 그 가정이 깨진다:

    base_link(= 좌우 구동륜 차축 정중앙) 기준 차체  front +0.10 / rear -0.50
                                                    left  +0.22 / right -0.22
    라이다는 base_link 보다 전방 +0.05 -> laser_frame 기준 차체는
        x in [-0.55, +0.05],  y in [-0.22, +0.22]

즉 라이다는 차체 **앞쪽 끝 근처**에 있고 몸통은 거의 전부 뒤에 있다. 이전 값
(`half_x 0.31`, `half_y 0.16`, 공차 +15%)은 정면 0.357 m 까지 지웠는데 그 구간에는
카트가 없다 — **정면 벽을 통째로 /scan 에서 지우고 있었다**(Nav2 가 앞의 벽을 못 봄).
동시에 후방 -0.36~-0.55 구간의 실제 몸통과 측면 ±0.184~±0.22 는 안 지워
자기 반사가 장애물로 남았다.

공차는 비율(+15%)이 아니라 **절대 여유 `margin`** 으로 바꿨다. 비율 공차는 긴 축
(후방 0.55)에 과하게 붙고 짧은 축(전방 0.05)에는 거의 안 붙어 비대칭 박스와 맞지
않는다. 기본 0.03 m 는 장착·측정 공차를 덮으면서 전방 컷오프를 0.08 m 로 유지한다
(X4 Pro 최소 유효거리 아래 → 전방은 사실상 마스킹 없음 = 벽을 지우지 않음).

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

# 카트 몸통 박스 (2026-08-09 사용자 줄자 실측, **laser_frame 기준**).
#   base_link = 좌우 구동륜 차축 정중앙, 전방 +X.
#   차체: front +0.10 / rear -0.50 / left +0.22 / right -0.22  (전후 0.60, 좌우 0.44)
#   라이다: base_link 보다 전방 +0.05  ->  아래 값은 위에서 0.05 를 뺀 것.
# 전륜 구동이라 차축이 차체 앞쪽에 치우쳐 있고, 라이다도 그 근처라 박스가
# 원점 기준으로 **뒤로 길다**. 대칭 half_x/half_y 로는 표현할 수 없다.
DEFAULT_BOX_MAX_X = 0.05   # 차체 최전방 (+0.10 - 0.05)
DEFAULT_BOX_MIN_X = -0.55  # 차체 최후방 (-0.50 - 0.05)
DEFAULT_BOX_MAX_Y = 0.22   # 좌측 최외곽 (바퀴 바깥면)
DEFAULT_BOX_MIN_Y = -0.22  # 우측 최외곽
# 장착·측정 절대 여유 [m]. 측면 경계가 0.25 m 가 되어 실측된 합판 절단면 스침
# (좌 0.15~0.19 m)을 덮는다. 전방은 0.08 m 로 라이다 최소 유효거리 아래라
# **실질적으로 마스킹하지 않는다** — 앞의 벽을 지우지 않기 위한 의도된 결과다.
DEFAULT_BOX_MARGIN = 0.03

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
        self.declare_parameter("box_max_x", DEFAULT_BOX_MAX_X)
        self.declare_parameter("box_min_x", DEFAULT_BOX_MIN_X)
        self.declare_parameter("box_max_y", DEFAULT_BOX_MAX_Y)
        self.declare_parameter("box_min_y", DEFAULT_BOX_MIN_Y)
        self.declare_parameter("box_margin", DEFAULT_BOX_MARGIN)
        self.declare_parameter(
            "mask_deg",
            DEFAULT_MASK_DEG,
            ParameterDescriptor(type=ParameterType.PARAMETER_DOUBLE_ARRAY),
        )

        self._input_topic = str(self.get_parameter("input_topic").value)
        self._output_topic = str(self.get_parameter("output_topic").value)
        self._max_x = float(self.get_parameter("box_max_x").value)
        self._min_x = float(self.get_parameter("box_min_x").value)
        self._max_y = float(self.get_parameter("box_max_y").value)
        self._min_y = float(self.get_parameter("box_min_y").value)
        self._margin = float(self.get_parameter("box_margin").value)
        # 원점(라이다)이 박스 안에 있어야 "박스를 벗어나는 거리" 가 정의된다.
        if not (self._min_x < 0.0 < self._max_x and self._min_y < 0.0 < self._max_y):
            raise ValueError(
                "라이다 원점이 박스 안에 있어야 한다 "
                f"(x={self._min_x}..{self._max_x}, y={self._min_y}..{self._max_y})"
            )
        if self._margin < 0.0:
            raise ValueError(f"box_margin 은 음수일 수 없다 ({self._margin})")

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
        self.get_logger().info(
            f"scan_mask_node: {self._input_topic} -> {self._output_topic} | "
            f"박스(laser_frame) x {self._min_x:+.2f}..{self._max_x:+.2f} "
            f"y {self._min_y:+.2f}..{self._max_y:+.2f} 여유 +{self._margin:.2f}m "
            f"→ 경계 정면 {self._box_limit(0.0):.3f} / "
            f"좌 {self._box_limit(90.0):.3f} / 우 {self._box_limit(-90.0):.3f} / "
            f"후방 {self._box_limit(180.0):.3f} m | 섹터 마스킹 {len(self._pairs)}개"
        )

    def _box_limit(self, deg: float) -> float:
        """해당 방위각에서 "이보다 가까우면 카트 몸통" 인 거리 [m].

        원점에서 방위각 `deg` 로 나간 광선이 몸통 박스를 벗어나는 거리에
        `box_margin` 을 더한 값. 원점이 박스 안이므로 항상 유한하다.

        Args:
            deg: laser_frame 기준 방위각 [deg]. 0 이 전방(+X), +가 좌측(+Y).

        Returns:
            컷오프 거리 [m].
        """
        t = math.radians(deg)
        c, s = math.cos(t), math.sin(t)
        if abs(c) > 1e-9:
            tx = (self._max_x if c > 0.0 else self._min_x) / c
        else:
            tx = math.inf
        if abs(s) > 1e-9:
            ty = (self._max_y if s > 0.0 else self._min_y) / s
        else:
            ty = math.inf
        return min(tx, ty) + self._margin

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
