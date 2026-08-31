"""control_node — 타겟(사서) 추종 PID 제어.

- /target_person (vision_msgs/Detection2DArray, reid_node 발행) 구독
- /scan (sensor_msgs/LaserScan, LiDAR 드라이버 발행) 구독
- 화면 중심 오차(각도) + LiDAR 거리(전방) → PID → /cmd_vel (geometry_msgs/Twist) 발행
- 측정한 타겟 거리를 /target_distance (std_msgs/Float32, m)로 발행 — 디버그 오버레이용.
  타겟이 보이는데 LiDAR 거리 측정에 실패하면 NaN을 발행한다 (타겟 미검출 시 미발행)

좌우 각도(center_x_normalized, -1~1)를 카메라 화각(FOV)에 맞는 방위각으로 변환한 뒤,
타겟 bbox의 각도 폭 범위에서 유효 range의 최소값(가장 가까운 표면=사람)을 거리로
사용. 순간 드롭아웃(다리 틈·IR 흡수 의류·유리)은 짧은 유예 시간 동안 직전 유효
거리를 유지해 흡수한다.

각도 규약 (ROS REP 103, 오른손 좌표계): +각도 = 반시계(왼쪽). 화면 오른쪽(+x)에
보이는 타겟의 방위각은 음수다. LiDAR의 0° 축이 카메라 광축(로봇 전방)과 어긋나게
장착된 경우 lidar_yaw_offset_deg 파라미터로 보정한다 (조립 후 캘리브레이션:
사람을 화면 정중앙에 세우고 LiDAR에서 그 사람이 잡히는 각도가 곧 오프셋).
카메라와 LiDAR의 위치 차이(수 cm)는 tf2로 정확히 변환해야 하지만, 1단계에서는
두 센서가 같은 축 위에 있다고 가정하고 단순화함.

안전 규칙: 타겟 미검출·타겟 메시지 끊김(staleness)·LiDAR 거리 획득 실패 시
정지(0 속도)를 발행.
"""

import math
from collections.abc import Sequence

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Float32
from vision_msgs.msg import Detection2D, Detection2DArray


def _get_bbox_center(detection: Detection2D) -> tuple[float, float]:
    """Read BoundingBox2D center across common vision_msgs layouts."""
    center = detection.bbox.center
    if hasattr(center, "position"):
        return float(center.position.x), float(center.position.y)
    return float(center.x), float(center.y)


def normalize_center_x(center_x_px: float, image_width_px: float) -> float:
    """Map a pixel x-coordinate to [-1, 1], where 0 is the image center.

    Args:
        center_x_px: Bounding box center x in pixels.
        image_width_px: Full image width in pixels. Must be positive.

    Returns:
        Normalized offset clamped to [-1, 1]. Negative = target left of center.

    Raises:
        ValueError: If image_width_px is not positive.
    """
    if image_width_px <= 0:
        raise ValueError("image_width_px must be positive")
    half_width = image_width_px / 2.0
    normalized = (center_x_px - half_width) / half_width
    return max(-1.0, min(1.0, normalized))


def camera_bearing_to_lidar_angle(
    center_x_normalized: float,
    camera_fov_deg: float,
    lidar_yaw_offset_deg: float = 0.0,
    mirrored: bool = False,
) -> float:
    """정규화 화면 x좌표(+는 오른쪽)를 LiDAR 프레임 방위각(rad, 반시계 +)으로 변환.

    REP 103 오른손 좌표계에서 +각도는 반시계(왼쪽)이므로, 화면 오른쪽(+x)에 보이는
    타겟의 방위각은 음수가 된다. lidar_yaw_offset_deg는 LiDAR의 0° 축이 로봇
    전방(카메라 광축)에서 반시계 방향으로 틀어져 장착된 각도로, 로봇 프레임
    방위각에서 이를 빼면 LiDAR 프레임 각도가 된다.

    Args:
        center_x_normalized: [-1, 1] 정규화 x. 0=화면 중앙, +1=오른쪽 끝.
        camera_fov_deg: 카메라 수평 화각(도).
        lidar_yaw_offset_deg: LiDAR 0° 축의 장착 오프셋(도, LiDAR 각도 축 기준 +).
        mirrored: LiDAR가 각도를 REP 103과 반대 방향(시계 +)으로 보고하면 True.
            뒤집어 장착했거나 드라이버 reversion 설정에 따라 발생하며, 증상은
            "화면 왼쪽의 타겟인데 오른쪽 물체의 거리가 잡힘"의 좌우 반전.

    Returns:
        LiDAR 프레임 기준 방위각(rad).
    """
    bearing_deg = -center_x_normalized * (camera_fov_deg / 2.0)
    if mirrored:
        bearing_deg = -bearing_deg
    return math.radians(bearing_deg - lidar_yaw_offset_deg)


def bbox_half_span_rad(
    bbox_width_px: float, image_width_px: float, camera_fov_deg: float
) -> float:
    """타겟 bbox 픽셀 폭을 카메라 화각 기준 각도 반폭(rad)으로 환산.

    Args:
        bbox_width_px: 타겟 bbox 폭(픽셀). 음수는 0으로 취급.
        image_width_px: 이미지 전체 폭(픽셀). 양수여야 함.
        camera_fov_deg: 카메라 수평 화각(도).

    Returns:
        bbox가 차지하는 시야각의 절반(rad). 이미지 폭 초과 bbox는 화각 절반으로 클램프.

    Raises:
        ValueError: image_width_px가 양수가 아닐 때.
    """
    if image_width_px <= 0:
        raise ValueError("image_width_px must be positive")
    fraction = min(1.0, max(0.0, bbox_width_px / image_width_px))
    return math.radians(fraction * camera_fov_deg / 2.0)


def min_valid_range_in_span(
    scan: LaserScan | None,
    center_angle_rad: float,
    half_span_rad: float,
    min_window: int = 2,
) -> float | None:
    """360° LaserScan에서 각도 범위 내 유효 range의 최소값을 반환.

    [center - half_span, center + half_span] 구간의 광선 중 유효한 것들의
    최소값(가장 가까운 표면)을 고른다. 타겟 bbox 폭만큼 조회하면 사람 몸과
    배경 광선이 섞여도 더 가까운 사람 쪽이 선택되고, 일부 광선이 무효
    (다리 틈·IR 흡수 의류·유리)여도 나머지가 보완한다.

    Args:
        scan: 최신 LaserScan. 전방위(360°) 스캔을 가정하며 인덱스는 순환.
        center_angle_rad: 조회 중심 각도(rad, LiDAR 프레임).
        half_span_rad: 조회 반폭(rad). 0이어도 min_window만큼은 조회.
        min_window: 반폭이 작아도 최소한 조회할 ±인덱스 수 (노이즈 완화).

    Returns:
        유효 range 최소값(m). 스캔이 없거나 유효 광선이 없으면 None.
    """
    if scan is None or scan.angle_increment <= 0.0:
        return None
    ray_count = len(scan.ranges)
    if ray_count == 0:
        return None

    # 360° 스캔 경계 처리: 각도를 [angle_min, angle_min + 2π) 범위로 정규화
    two_pi = 2.0 * math.pi
    center = scan.angle_min + ((center_angle_rad - scan.angle_min) % two_pi)
    center_index = int((center - scan.angle_min) / scan.angle_increment)

    window = max(min_window, math.ceil(half_span_rad / scan.angle_increment))
    best: float | None = None
    for i in range(center_index - window, center_index + window + 1):
        r = scan.ranges[i % ray_count]  # 전방위 스캔이므로 경계를 넘으면 순환
        if scan.range_min < r < scan.range_max and (best is None or r < best):
            best = r
    return best


class PID:
    """Simple PID controller with symmetric output clamping."""

    def __init__(self, kp: float, ki: float, kd: float, output_limit: float) -> None:
        """Store gains and initialize integrator/derivative state."""
        self.kp, self.ki, self.kd = kp, ki, kd
        self.integral = 0.0
        self.prev_error = 0.0
        self.output_limit = output_limit

    def compute(self, error: float, dt: float) -> float:
        """Return the clamped PID output for one control step."""
        self.integral += error * dt
        derivative = (error - self.prev_error) / dt if dt > 0 else 0.0
        output = self.kp * error + self.ki * self.integral + self.kd * derivative
        self.prev_error = error
        return max(-self.output_limit, min(self.output_limit, output))

    def reset(self) -> None:
        """Clear accumulated state (call when the target is lost)."""
        self.integral = 0.0
        self.prev_error = 0.0


class ControlNode(Node):
    """Follow the Re-ID target at a fixed distance using camera + LiDAR + PID."""

    def __init__(self) -> None:
        """Declare parameters, build PID controllers, and wire topics."""
        super().__init__("control_node")

        self.declare_parameter("target_distance_m", 1.0)   # 목표 거리 1m
        self.declare_parameter("camera_fov_deg", 58.0)      # 수평 화각 (실측 58°)
        self.declare_parameter("image_width", 640)  # camera frame_width와 일치
        self.declare_parameter("lidar_yaw_offset_deg", 0.0)  # 0°축 오프셋
        self.declare_parameter("lidar_mirrored", True)  # 각도 축 좌우 반전 (실측)
        self.declare_parameter("bbox_span_scale", 0.8)  # bbox 폭 중 조회에 쓸 비율
        self.declare_parameter("distance_grace_period_sec", 0.5)  # 드롭아웃 유예
        self.declare_parameter("target_timeout_sec", 1.0)  # 타겟 끊기면 정지
        self.declare_parameter("angular_kp", 0.8)
        self.declare_parameter("angular_ki", 0.0)
        self.declare_parameter("angular_kd", 0.1)
        self.declare_parameter("linear_kp", 0.5)
        self.declare_parameter("linear_ki", 0.0)
        self.declare_parameter("linear_kd", 0.05)
        self.declare_parameter("max_linear_vel", 0.5)
        self.declare_parameter("max_angular_vel", 1.0)
        # 🔴 후진 금지 (2026-08-10). 기본 False.
        #    사서가 책을 꺼내려 카트 쪽으로 다가오면 거리 오차가 음수가 되어
        #    카트가 뒷걸음질친다. 실기에서 "사서가 다가가면 카트가 멀어진다"로
        #    관측된 그 동작이다. 뒤쪽은 라이다 자기차폐 구간이라 후방 장애물도
        #    못 본다 — 안전상으로도 후진은 열지 않는다.
        #    True 로 바꾸면 예전 동작(거리 유지형 전후진)으로 돌아간다.
        self.declare_parameter("allow_reverse", False)
        # 🔴 전방 장애물 정지 (2026-08-10). Nav2 없이 단순 추종만 돌릴 때
        #    유일한 충돌 방어다 — 기존 거리 조회는 **타겟 방향 창만** 보므로
        #    정면에 벽이나 끼어든 사람이 있어도 감지하지 못했다.
        #    임계값은 target_distance_m(1.0)보다 **작아야** 한다. 같거나 크면
        #    추종 대상 본인이 매번 걸려 카트가 영영 전진하지 못한다.
        self.declare_parameter("obstacle_stop_enabled", True)
        self.declare_parameter("min_obstacle_distance_m", 0.8)
        self.declare_parameter("front_half_span_deg", 30.0)

        self.allow_reverse = bool(self.get_parameter("allow_reverse").value)
        self.obstacle_stop_enabled = bool(
            self.get_parameter("obstacle_stop_enabled").value
        )
        self.min_obstacle_distance_m = float(
            self.get_parameter("min_obstacle_distance_m").value
        )
        self.front_half_span_rad = math.radians(
            float(self.get_parameter("front_half_span_deg").value)
        )
        self.target_distance = float(self.get_parameter("target_distance_m").value)
        self.camera_fov_deg = float(self.get_parameter("camera_fov_deg").value)
        self.lidar_yaw_offset_deg = float(
            self.get_parameter("lidar_yaw_offset_deg").value
        )
        self.lidar_mirrored = bool(self.get_parameter("lidar_mirrored").value)
        self.bbox_span_scale = float(self.get_parameter("bbox_span_scale").value)
        self.distance_grace_period_sec = float(
            self.get_parameter("distance_grace_period_sec").value
        )
        self.image_width = int(self.get_parameter("image_width").value)
        self.target_timeout_sec = float(self.get_parameter("target_timeout_sec").value)

        self.angular_pid = PID(
            float(self.get_parameter("angular_kp").value),
            float(self.get_parameter("angular_ki").value),
            float(self.get_parameter("angular_kd").value),
            float(self.get_parameter("max_angular_vel").value),
        )
        self.linear_pid = PID(
            float(self.get_parameter("linear_kp").value),
            float(self.get_parameter("linear_ki").value),
            float(self.get_parameter("linear_kd").value),
            float(self.get_parameter("max_linear_vel").value),
        )

        self.latest_scan: LaserScan | None = None
        self.detected = False
        self.center_x_normalized = 0.0
        self.target_bbox_width_px = 0.0
        self.last_target_time = self.get_clock().now()
        self.last_valid_distance: float | None = None
        self.last_valid_distance_time = self.get_clock().now()

        self.create_subscription(
            Detection2DArray, "/target_person", self.target_callback, 10
        )
        # LiDAR 드라이버는 BEST_EFFORT(sensor QoS)로 발행하므로 구독도 맞춘다
        # (기본 RELIABLE 구독은 BEST_EFFORT 발행자와 매칭되지 않아 /scan을 못 받음)
        self.create_subscription(
            LaserScan, "/scan", self.scan_callback, qos_profile_sensor_data
        )
        self.cmd_pub = self.create_publisher(Twist, "/cmd_vel", 10)
        self.distance_pub = self.create_publisher(Float32, "/target_distance", 10)

        self.prev_time = self.get_clock().now()
        self.timer = self.create_timer(1.0 / 15.0, self.control_loop)  # 15Hz 제어 루프

        self.get_logger().info(
            f"control_node 시작 (target_distance={self.target_distance}m, "
            f"image_width={self.image_width}px)"
        )

    def target_callback(self, msg: Detection2DArray) -> None:
        """Consume the Re-ID target detection and cache its normalized x-offset."""
        if not msg.detections:
            self.detected = False
            return

        try:
            center_x, _center_y = _get_bbox_center(msg.detections[0])
            self.center_x_normalized = normalize_center_x(center_x, self.image_width)
            self.target_bbox_width_px = float(msg.detections[0].bbox.size_x)
        except (ValueError, AttributeError) as error:
            self.get_logger().error(f"타겟 메시지 해석 실패: {error}")
            self.detected = False
            return

        self.detected = True
        self.last_target_time = self.get_clock().now()

    def scan_callback(self, msg: LaserScan) -> None:
        """Cache the newest LiDAR scan."""
        self.latest_scan = msg

    def _front_obstacle_distance(self) -> float | None:
        """Return the front obstacle distance when it is closer than the threshold.

        로봇 정면(카메라 광축) 섹터를 조회한다. 기준각은 타겟 조회와 **같은 변환**을
        쓴다 — `center_x_normalized=0` 이 곧 화면 중앙이자 로봇 정면이고, 라이다
        장착 오프셋·좌우 반전이 여기에 함께 반영되어야 두 조회가 같은 축을 본다.

        Returns:
            임계값보다 가까운 장애물이 있으면 그 거리[m], 없으면 None.
            유효 반사가 하나도 없을 때도 None (근거 없이 멈추지 않는다).
        """
        if not self.obstacle_stop_enabled or self.latest_scan is None:
            return None
        front_angle_rad = camera_bearing_to_lidar_angle(
            0.0,
            self.camera_fov_deg,
            self.lidar_yaw_offset_deg,
            self.lidar_mirrored,
        )
        nearest = min_valid_range_in_span(
            self.latest_scan, front_angle_rad, self.front_half_span_rad
        )
        if nearest is None or nearest >= self.min_obstacle_distance_m:
            return None
        return nearest

    def _target_is_stale(self) -> bool:
        """Return True if no target message arrived within the timeout window."""
        elapsed = (self.get_clock().now() - self.last_target_time).nanoseconds / 1e9
        return elapsed > self.target_timeout_sec

    def control_loop(self) -> None:
        """Run one 15 Hz control step and publish a Twist command."""
        now = self.get_clock().now()
        dt = (now - self.prev_time).nanoseconds / 1e9
        self.prev_time = now
        if dt <= 0:
            return

        cmd = Twist()

        if not self.detected or self._target_is_stale():
            # 타겟 없음/끊김 → 정지 + PID 상태 초기화 (재획득 시 적분 잔량 방지)
            self.angular_pid.reset()
            self.linear_pid.reset()
            self.cmd_pub.publish(cmd)
            return

        # center_x_normalized(-1~1) -> LiDAR 프레임 방위각(rad, 반시계 +)으로 변환
        angle_rad = camera_bearing_to_lidar_angle(
            self.center_x_normalized,
            self.camera_fov_deg,
            self.lidar_yaw_offset_deg,
            self.lidar_mirrored,
        )

        # 타겟 bbox가 차지하는 각도 폭에서 가장 가까운 유효 표면을 거리로 채택.
        # bbox 가장자리의 배경 광선이 옆 물체를 잡지 않게 폭을 bbox_span_scale로 줄인다.
        half_span_rad = bbox_half_span_rad(
            self.target_bbox_width_px * self.bbox_span_scale,
            self.image_width,
            self.camera_fov_deg,
        )
        distance = min_valid_range_in_span(self.latest_scan, angle_rad, half_span_rad)

        if distance is not None:
            self.last_valid_distance = distance
            self.last_valid_distance_time = now
        elif self.last_valid_distance is not None:
            # 순간 드롭아웃(다리 틈·IR 흡수 의류·유리)은 직전 유효 거리로 이어간다
            held_sec = (now - self.last_valid_distance_time).nanoseconds / 1e9
            if held_sec <= self.distance_grace_period_sec:
                distance = self.last_valid_distance

        # 디버그 오버레이용으로 측정 거리를 공유. 측정 실패(/scan 없음·무효 range)도
        # NaN으로 발행해 "LiDAR 데이터 없음"을 오버레이가 구분 표시할 수 있게 한다.
        self.distance_pub.publish(
            Float32(data=float(distance) if distance is not None else math.nan)
        )

        angular_error = -self.center_x_normalized  # 오른쪽(+)이면 우회전(-ω, REP 103)
        angular_vel = self.angular_pid.compute(angular_error, dt)

        if distance is not None:
            linear_error = distance - self.target_distance
            if not self.allow_reverse:
                # 1차 방어 — 오차 단계에서 자른다. 음수 오차를 PID 에 그대로
                # 넣으면 사람이 접근하는 내내 D 항이 음수를 만들어, 출력만
                # 잘라도 반응이 굼떠진다.
                linear_error = max(0.0, linear_error)
            linear_vel = self.linear_pid.compute(linear_error, dt)
        else:
            # LiDAR 거리 못 구하면 안전하게 정지 (카메라만으로 전진은 위험)
            linear_vel = 0.0
            reason = (
                "/scan 미수신 (드라이버·QoS 확인)"
                if self.latest_scan is None
                else "조회 각도에 유효 range 없음"
            )
            self.get_logger().warn(
                f"LiDAR 거리 획득 실패({reason}), 선속도 0으로 설정",
                throttle_duration_sec=2.0,
            )

        if not self.allow_reverse:
            # 2차 방어 — 오차가 0 이어도 kd(0.05) 미분항이 순간 음수를 낼 수 있다.
            # 회전(angular_vel)은 그대로 둔다: 제자리에서 사서를 계속 바라본다.
            linear_vel = max(0.0, linear_vel)

        # 전방 장애물 정지 — 전진만 막고 회전은 살린다. 그래야 사서를 계속
        # 바라보다가, 장애물이 비키거나 사서가 옆으로 이동하면 바로 재개된다.
        # 유효 반사가 하나도 없으면(None) 근거가 없으므로 정지시키지 않는다.
        blocked_distance = self._front_obstacle_distance()
        if blocked_distance is not None:
            linear_vel = 0.0
            self.get_logger().warning(
                f"전방 {blocked_distance:.2f} m 에 장애물 — 전진 정지"
                f" (임계 {self.min_obstacle_distance_m:.2f} m)",
                throttle_duration_sec=2.0,
            )

        cmd.linear.x = linear_vel
        cmd.angular.z = angular_vel
        self.cmd_pub.publish(cmd)


def main(args: Sequence[str] | None = None) -> None:
    """Start the control node."""
    rclpy.init(args=args)
    node = ControlNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
