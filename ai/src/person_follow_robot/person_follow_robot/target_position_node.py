"""target_position_node — 사서(타겟)의 지도(map) 좌표 추정·발행.

아키텍처 변경(2026-07-31): AI는 더 이상 속도 명령(cmd_vel/RPM)을 만들지 않는다.

- 변경 전: AI가 PID로 cmd_vel → RPM까지 계산해 STM32로 하행
- 변경 후: SLAM(EM)이 주는 카트 현재 포즈 + 카메라 방위각 + LiDAR 거리로
  타겟의 지도 좌표를 계산해 발행하면, SLAM 내비게이션이 경로를 계획하고
  STM32가 모터를 구동한다. **AI의 책임은 /target_position 발행까지.**

구독:
- /target_person (vision_msgs/Detection2DArray, reid_node)
- /scan (sensor_msgs/LaserScan, BEST_EFFORT)
- 카트 포즈 (geometry_msgs/PoseStamped, 토픽명 cart_pose_topic 파라미터 —
  EM과 계약 협의 중. 노드 CLAUDE.md Known Gaps 참조)

발행:
- /target_position (geometry_msgs/PointStamped, frame=map_frame_id)
  타겟 미관측·거리 실패·포즈 미수신(stale) 시에는 발행하지 않는다.
  소비자(SLAM Nav)가 마지막 좌표를 목표로 유지하면 "마지막 위치까지
  이동"이 자연히 구현된다.

기존 control_node/motor_node(cmd_vel→RPM)는 EM 파트가 STM 쪽에서 재활용할
예정이므로 수정하지 않는다. 방위각·LiDAR 거리 계산은 control_node의 순수
함수를 재사용한다.
"""

import math
from collections.abc import Sequence

import rclpy
from geometry_msgs.msg import PointStamped, PoseStamped
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from vision_msgs.msg import Detection2DArray

try:
    from .control_node import (
        _get_bbox_center,
        bbox_half_span_rad,
        camera_bearing_to_lidar_angle,
        min_valid_range_in_span,
        normalize_center_x,
    )
except ImportError:  # pytest가 노드 디렉토리를 sys.path에 놓고 단일 모듈로 import
    from control_node import (
        _get_bbox_center,
        bbox_half_span_rad,
        camera_bearing_to_lidar_angle,
        min_valid_range_in_span,
        normalize_center_x,
    )


def yaw_from_quaternion(x: float, y: float, z: float, w: float) -> float:
    """쿼터니언에서 yaw(z축 회전, rad)를 계산한다.

    Args:
        x: 쿼터니언 x 성분.
        y: 쿼터니언 y 성분.
        z: 쿼터니언 z 성분.
        w: 쿼터니언 w 성분.

    Returns:
        yaw (rad, 반시계 +). 평면 주행 로봇은 roll/pitch≈0이므로
        이 값이 곧 카트의 진행 방향이다.
    """
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def robot_frame_bearing(center_x_normalized: float, camera_fov_deg: float) -> float:
    """정규화 화면 x좌표를 로봇 프레임 방위각(rad, REP 103 반시계 +)으로 변환.

    LiDAR 조회각(camera_bearing_to_lidar_angle)과 달리 센서 장착 보정
    (mirrored/yaw offset)이 없는 **물리적 방향**이다 — 지도 좌표 변환에는
    이 값을 쓴다.

    Args:
        center_x_normalized: [-1, 1] 정규화 x. 0=화면 중앙, +1=오른쪽 끝.
        camera_fov_deg: 카메라 수평 화각(도).

    Returns:
        로봇 전방 기준 방위각 (rad). 화면 오른쪽 타겟은 음수.
    """
    return math.radians(-center_x_normalized * camera_fov_deg / 2.0)


def target_position_in_map(
    cart_x: float,
    cart_y: float,
    cart_yaw_rad: float,
    bearing_rad: float,
    distance_m: float,
) -> tuple[float, float]:
    """카트 포즈와 로봇 프레임 관측(방위각·거리)으로 타겟의 지도 좌표를 계산.

    Args:
        cart_x: 카트 지도 x (m).
        cart_y: 카트 지도 y (m).
        cart_yaw_rad: 카트 진행 방향 (rad, 반시계 +).
        bearing_rad: 로봇 프레임 타겟 방위각 (rad, 반시계 +).
        distance_m: 타겟까지 거리 (m).

    Returns:
        (x, y) 지도 좌표 (m).
    """
    angle = cart_yaw_rad + bearing_rad
    return (
        cart_x + distance_m * math.cos(angle),
        cart_y + distance_m * math.sin(angle),
    )


class TargetPositionNode(Node):
    """Fuse cart pose, camera bearing, and LiDAR range into a map-frame target."""

    def __init__(self) -> None:
        """Declare parameters and wire subscriptions/publisher."""
        super().__init__("target_position_node")

        self.declare_parameter("cart_pose_topic", "/robot_pose")  # EM 협의 중
        self.declare_parameter("target_position_topic", "/target_position")
        self.declare_parameter("map_frame_id", "map")
        self.declare_parameter("camera_fov_deg", 58.0)
        self.declare_parameter("image_width", 640)
        self.declare_parameter("lidar_yaw_offset_deg", 0.0)
        self.declare_parameter("lidar_mirrored", True)
        self.declare_parameter("bbox_span_scale", 0.8)
        self.declare_parameter("pose_timeout_sec", 1.0)  # 포즈 끊기면 발행 중단

        self.camera_fov_deg = float(self.get_parameter("camera_fov_deg").value)
        self.image_width = int(self.get_parameter("image_width").value)
        self.lidar_yaw_offset_deg = float(
            self.get_parameter("lidar_yaw_offset_deg").value
        )
        self.lidar_mirrored = bool(self.get_parameter("lidar_mirrored").value)
        self.bbox_span_scale = float(self.get_parameter("bbox_span_scale").value)
        self.pose_timeout_sec = float(self.get_parameter("pose_timeout_sec").value)
        self.map_frame_id = str(self.get_parameter("map_frame_id").value)

        self.latest_scan: LaserScan | None = None
        self.cart_x: float | None = None
        self.cart_y: float | None = None
        self.cart_yaw: float | None = None
        self.pose_received_at = None

        cart_pose_topic = str(self.get_parameter("cart_pose_topic").value)
        self.create_subscription(
            Detection2DArray, "/target_person", self.target_callback, 10
        )
        self.create_subscription(
            LaserScan, "/scan", self.scan_callback, qos_profile_sensor_data
        )
        self.create_subscription(
            PoseStamped, cart_pose_topic, self.pose_callback, 10
        )
        self.position_pub = self.create_publisher(
            PointStamped,
            str(self.get_parameter("target_position_topic").value),
            10,
        )

        self.get_logger().info(
            f"target_position_node 시작 (pose_topic={cart_pose_topic}, "
            f"frame={self.map_frame_id})"
        )

    def scan_callback(self, msg: LaserScan) -> None:
        """Cache the newest LiDAR scan."""
        self.latest_scan = msg

    def pose_callback(self, msg: PoseStamped) -> None:
        """Cache the newest SLAM cart pose (x, y, yaw)."""
        self.cart_x = float(msg.pose.position.x)
        self.cart_y = float(msg.pose.position.y)
        orientation = msg.pose.orientation
        self.cart_yaw = yaw_from_quaternion(
            float(orientation.x),
            float(orientation.y),
            float(orientation.z),
            float(orientation.w),
        )
        self.pose_received_at = self.get_clock().now()

    def _pose_is_fresh(self) -> bool:
        if self.pose_received_at is None:
            return False
        elapsed = (self.get_clock().now() - self.pose_received_at).nanoseconds / 1e9
        return elapsed <= self.pose_timeout_sec

    def target_callback(self, msg: Detection2DArray) -> None:
        """Estimate the target map position for each Re-ID target detection."""
        if not msg.detections:
            return
        if not self._pose_is_fresh():
            self.get_logger().warn(
                "카트 포즈 미수신/지연 — 타겟 좌표 발행 보류 "
                "(SLAM 포즈 토픽 연결 확인)",
                throttle_duration_sec=2.0,
            )
            return

        try:
            detection = msg.detections[0]
            center_x, _center_y = _get_bbox_center(detection)
            center_x_normalized = normalize_center_x(center_x, self.image_width)
        except (ValueError, AttributeError) as error:
            self.get_logger().error(f"타겟 메시지 해석 실패: {error}")
            return

        # LiDAR 거리: 센서 보정이 들어간 조회각으로 스캔에서 최소 유효 거리
        lookup_angle = camera_bearing_to_lidar_angle(
            center_x_normalized,
            self.camera_fov_deg,
            self.lidar_yaw_offset_deg,
            self.lidar_mirrored,
        )
        half_span = bbox_half_span_rad(
            float(detection.bbox.size_x) * self.bbox_span_scale,
            self.image_width,
            self.camera_fov_deg,
        )
        distance = min_valid_range_in_span(self.latest_scan, lookup_angle, half_span)
        if distance is None:
            self.get_logger().warn(
                "LiDAR 거리 획득 실패 — 타겟 좌표 발행 보류",
                throttle_duration_sec=2.0,
            )
            return

        # 지도 좌표 변환: 물리 방위각(센서 보정 없음) + 카트 포즈
        bearing = robot_frame_bearing(center_x_normalized, self.camera_fov_deg)
        target_x, target_y = target_position_in_map(
            self.cart_x, self.cart_y, self.cart_yaw, bearing, float(distance)
        )

        output = PointStamped()
        output.header.stamp = self.get_clock().now().to_msg()
        output.header.frame_id = self.map_frame_id
        output.point.x = target_x
        output.point.y = target_y
        output.point.z = 0.0
        self.position_pub.publish(output)


def main(args: Sequence[str] | None = None) -> None:
    """Start the target position node."""
    rclpy.init(args=args)
    node = TargetPositionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
