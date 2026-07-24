"""control_node — 타겟(사서) 추종 PID 제어.

- /target_person (vision_msgs/Detection2DArray, reid_node 발행) 구독
- /scan (sensor_msgs/LaserScan, LiDAR 드라이버 발행) 구독
- 화면 중심 오차(각도) + LiDAR 거리(전방) → PID → /cmd_vel (geometry_msgs/Twist) 발행

좌우 각도(center_x_normalized, -1~1)를 카메라 화각(FOV)에 맞는 각도로 변환한 뒤,
LiDAR의 해당 각도 근방 range 값들을 평균 내어 거리로 사용.
카메라와 LiDAR가 로봇 위에서 물리적으로 다른 위치에 있다면 정확히는 tf2로 좌표 변환해야 하지만,
1단계에서는 두 센서가 로봇 정면 기준으로 거의 같은 방향을 보고 있다고 가정하고 단순화함.

안전 규칙: 타겟 미검출·타겟 메시지 끊김(staleness)·LiDAR 거리 획득 실패 시 정지(0 속도) 발행.
"""

import math
from typing import Sequence

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
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
        self.declare_parameter("camera_fov_deg", 60.0)      # 카메라 수평 화각, 실제 스펙에 맞게 조정
        self.declare_parameter("image_width", 640)          # camera_node frame_width와 일치해야 함
        self.declare_parameter("target_timeout_sec", 1.0)   # 이 시간 동안 타겟 메시지 없으면 정지
        self.declare_parameter("angular_kp", 0.8)
        self.declare_parameter("angular_ki", 0.0)
        self.declare_parameter("angular_kd", 0.1)
        self.declare_parameter("linear_kp", 0.5)
        self.declare_parameter("linear_ki", 0.0)
        self.declare_parameter("linear_kd", 0.05)
        self.declare_parameter("max_linear_vel", 0.5)
        self.declare_parameter("max_angular_vel", 1.0)

        self.target_distance = float(self.get_parameter("target_distance_m").value)
        self.camera_fov_deg = float(self.get_parameter("camera_fov_deg").value)
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
        self.last_target_time = self.get_clock().now()

        self.create_subscription(
            Detection2DArray, "/target_person", self.target_callback, 10
        )
        self.create_subscription(LaserScan, "/scan", self.scan_callback, 10)
        self.cmd_pub = self.create_publisher(Twist, "/cmd_vel", 10)

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
        except (ValueError, AttributeError) as error:
            self.get_logger().error(f"타겟 메시지 해석 실패: {error}")
            self.detected = False
            return

        self.detected = True
        self.last_target_time = self.get_clock().now()

    def scan_callback(self, msg: LaserScan) -> None:
        """Cache the newest LiDAR scan."""
        self.latest_scan = msg

    def get_distance_at_angle(self, angle_rad: float) -> float | None:
        """LiDAR scan에서 특정 각도 근방의 유효 거리값 평균을 반환."""
        scan = self.latest_scan
        if scan is None:
            return None

        # 해당 각도에 가장 가까운 인덱스 계산
        index = int((angle_rad - scan.angle_min) / scan.angle_increment)

        # 주변 +-2개 인덱스 평균 (노이즈 완화)
        window = 2
        valid_ranges = []
        for i in range(index - window, index + window + 1):
            if 0 <= i < len(scan.ranges):
                r = scan.ranges[i]
                if scan.range_min < r < scan.range_max:
                    valid_ranges.append(r)

        if not valid_ranges:
            return None
        return sum(valid_ranges) / len(valid_ranges)

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

        # center_x_normalized(-1~1) -> 실제 각도(rad)로 변환
        angle_rad = math.radians(self.center_x_normalized * (self.camera_fov_deg / 2.0))

        distance = self.get_distance_at_angle(angle_rad)

        angular_error = -self.center_x_normalized  # 사람이 오른쪽(+)에 있으면 우회전(부호는 로봇 규약에 맞게 조정)
        angular_vel = self.angular_pid.compute(angular_error, dt)

        if distance is not None:
            linear_error = distance - self.target_distance
            linear_vel = self.linear_pid.compute(linear_error, dt)
        else:
            # LiDAR 거리 못 구하면 안전하게 정지 (카메라만으로 전진은 위험)
            linear_vel = 0.0
            self.get_logger().warn(
                "LiDAR 거리 획득 실패, 선속도 0으로 설정", throttle_duration_sec=2.0
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
