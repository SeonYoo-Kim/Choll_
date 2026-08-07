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

# math 모듈: 삼각함수(atan2, cos, sin) 및 기본 수학 연산 사용
import math

# Sequence: 배열 같은 자료구조의 타입 힌팅
from collections.abc import Sequence

# ROS2 Python 클라이언트 라이브러리
import rclpy

# ROS2 메시지 타입: PointStamped (위치+시간), PoseStamped (위치+방향+시간)
from geometry_msgs.msg import PointStamped, PoseStamped

# ROS2 Node 클래스: 노드 생성·콜백 등록의 기본
from rclpy.node import Node

# ROS2 QoS(서비스 품질) 프로필: 센서 데이터(LiDAR 스캔)에 적합한 설정
from rclpy.qos import qos_profile_sensor_data

# ROS2 메시지 타입: LaserScan (LiDAR 거리 데이터)
from sensor_msgs.msg import LaserScan

# ROS2 메시지 타입: Detection2DArray (reid_node에서 온 타겟 정보)
from vision_msgs.msg import Detection2DArray

# control_node에서 이미 정의된 순수 함수들을 import (코드 재사용)
# 패키지 형태와 테스트 형태의 import 경로가 다르므로 try/except로 처리
try:
    # 패키지로 실행할 때: 상대 import 사용
    from .control_node import (
        # 바운딩박스의 중심점(x, y) 좌표 추출 (구형/신형 레이아웃 양쪽 지원)
        _get_bbox_center,
        # 바운딩박스 너비로부터 LiDAR 조회 반각(rad) 계산
        bbox_half_span_rad,
        # 정규화 화면 x좌표를 LiDAR 각도로 변환 (센서 장착 보정 포함)
        camera_bearing_to_lidar_angle,
        # LiDAR 스캔에서 일정 각도 범위의 최소 유효 거리 반환
        min_valid_range_in_span,
        # 바운딩박스 중심 x를 [-1, 1] 범위로 정규화
        normalize_center_x,
    )
except ImportError:  # pytest가 노드 디렉토리를 sys.path에 놓고 단일 모듈로 import
    # 테스트에서 직접 실행할 때: 절대 import 사용
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
    # atan2를 이용해 쿼터니언에서 z축 회전 각도(yaw) 추출
    # 공식: yaw = atan2(2(w*z + x*y), 1 - 2(y² + z²))
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
    # 정규화 x 좌표를 라디안 각도로 변환
    # 음수는 화면 오른쪽이 카트 기준 음의 방위각(오른쪽 방향)임을 나타냄
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
    # 지도 프레임의 절대 각도 = 카트의 방향(yaw) + 카트 기준 상대 방위각
    angle = cart_yaw_rad + bearing_rad
    # 극좌표(각도 + 거리) → 직교좌표(x, y) 변환
    # 삼각함수: x = r*cos(θ), y = r*sin(θ)
    return (
        cart_x + distance_m * math.cos(angle),  # 지도 x = 카트 x + 거리*cos(절대각도)
        cart_y + distance_m * math.sin(angle),  # 지도 y = 카트 y + 거리*sin(절대각도)
    )


class TargetPositionNode(Node):
    """지도 좌표계에서 타겟 위치를 계산·발행하는 노드.

    카트 포즈(SLAM) + 카메라 방위각 + LiDAR 거리를 융합하여
    타겟의 지도 좌표를 계산한다.
    """

    def __init__(self) -> None:
        """파라미터 선언, 구독/발행 설정."""
        # ROS2 노드 초기화 (노드명 = "target_position_node")
        super().__init__("target_position_node")

        # 카트 포즈를 받을 토픽 이름 (EM과의 계약, 기본값 = /robot_pose)
        self.declare_parameter("cart_pose_topic", "/robot_pose")
        # 타겟 좌표를 발행할 토픽 이름
        self.declare_parameter("target_position_topic", "/target_position")
        # TF2 프레임 ID (보통 "map" — 지도 좌표계)
        self.declare_parameter("map_frame_id", "map")
        # 카메라의 수평 화각 (도, 일반적 USB 카메라 ~58도)
        self.declare_parameter("camera_fov_deg", 58.0)
        # 카메라 영상 해상도 (픽셀, 가로)
        self.declare_parameter("image_width", 640)
        # LiDAR 0도 축과 카메라 광축의 각도 편차 보정값 (도)
        self.declare_parameter("lidar_yaw_offset_deg", 0.0)
        # LiDAR 각도 방향이 반대인지 여부 (True = 센서가 시계 + 보고)
        self.declare_parameter("lidar_mirrored", True)
        # 바운딩박스 너비의 몇 배까지 LiDAR 조회 범위를 확장할지 (0~1)
        self.declare_parameter("bbox_span_scale", 0.8)
        # SLAM 포즈 신선도 임계값 (초, 이 이상 수신 없으면 발행 중단)
        self.declare_parameter("pose_timeout_sec", 1.0)

        # 파라미터 값을 인스턴스 변수로 저장 (타입 변환 포함)
        self.camera_fov_deg = float(self.get_parameter("camera_fov_deg").value)
        self.image_width = int(self.get_parameter("image_width").value)
        self.lidar_yaw_offset_deg = float(
            self.get_parameter("lidar_yaw_offset_deg").value
        )
        self.lidar_mirrored = bool(self.get_parameter("lidar_mirrored").value)
        self.bbox_span_scale = float(self.get_parameter("bbox_span_scale").value)
        self.pose_timeout_sec = float(self.get_parameter("pose_timeout_sec").value)
        self.map_frame_id = str(self.get_parameter("map_frame_id").value)

        # 최신 LiDAR 스캔 캐시 (None = 아직 수신 안 함)
        self.latest_scan: LaserScan | None = None
        # 카트의 지도 좌표 x (None = 아직 수신 안 함)
        self.cart_x: float | None = None
        # 카트의 지도 좌표 y (None = 아직 수신 안 함)
        self.cart_y: float | None = None
        # 카트의 진행 방향 각도 (라디안, None = 아직 수신 안 함)
        self.cart_yaw: float | None = None
        # SLAM 포즈를 마지막으로 수신한 시각 (신선도 판정용)
        self.pose_received_at = None

        # 파라미터에서 카트 포즈 토픽 이름 읽기
        cart_pose_topic = str(self.get_parameter("cart_pose_topic").value)

        # reid_node에서 온 타겟 정보(Detection2DArray) 구독
        # QoS depth=10 (최대 10개 메시지 버퍼)
        self.create_subscription(
            Detection2DArray, "/target_person", self.target_callback, 10
        )

        # LiDAR 드라이버에서 온 거리 데이터(/scan) 구독
        # QoS = qos_profile_sensor_data (실시간 센서 데이터에 최적화)
        self.create_subscription(
            LaserScan, "/scan", self.scan_callback, qos_profile_sensor_data
        )

        # SLAM에서 온 카트 포즈 구독 (토픽명은 파라미터로 지정)
        # QoS depth=10 (최대 10개 메시지 버퍼)
        self.create_subscription(PoseStamped, cart_pose_topic, self.pose_callback, 10)

        # 타겟 지도 좌표(PointStamped) 발행자 생성
        # QoS depth=10, 토픽명은 파라미터에서 읽음
        self.position_pub = self.create_publisher(
            PointStamped,
            str(self.get_parameter("target_position_topic").value),
            10,
        )

        # 노드 시작 로그 (포즈 토픽명과 프레임 ID 표시)
        self.get_logger().info(
            f"target_position_node 시작 (pose_topic={cart_pose_topic}, "
            f"frame={self.map_frame_id})"
        )

    def scan_callback(self, msg: LaserScan) -> None:
        """최신 LiDAR 스캔 캐시."""
        # 수신한 LaserScan 메시지를 인스턴스 변수에 저장
        # (target_callback에서 거리 계산 시 사용)
        self.latest_scan = msg

    def pose_callback(self, msg: PoseStamped) -> None:
        """최신 SLAM 카트 포즈(x, y, yaw) 캐시."""
        # 카트 위치 x 좌표 (지도 프레임, 미터)
        self.cart_x = float(msg.pose.position.x)
        # 카트 위치 y 좌표 (지도 프레임, 미터)
        self.cart_y = float(msg.pose.position.y)
        # 포즈 메시지에서 회전 정보(쿼터니언) 추출
        orientation = msg.pose.orientation
        # 쿼터니언을 yaw 각도로 변환 (z축 회전 = 진행 방향)
        self.cart_yaw = yaw_from_quaternion(
            float(orientation.x),
            float(orientation.y),
            float(orientation.z),
            float(orientation.w),
        )
        # 포즈 수신 시간 기록 (신선도 판정용)
        self.pose_received_at = self.get_clock().now()

    def _pose_is_fresh(self) -> bool:
        """SLAM 포즈가 최근에 도착했는지 확인 (타임아웃 판정).

        Returns:
            포즈 신선도 여부 (True = 최근 수신, False = 지연/미수신)
        """
        # 포즈를 한 번도 받지 못했으면 신선하지 않음
        if self.pose_received_at is None:
            return False
        # 현재 시각과 마지막 포즈 수신 시각의 차이 계산 (초 단위)
        elapsed = (self.get_clock().now() - self.pose_received_at).nanoseconds / 1e9
        # 경과 시간이 임계값 이하면 신선한 포즈
        return elapsed <= self.pose_timeout_sec

    def target_callback(self, msg: Detection2DArray) -> None:
        """Re-ID 타겟 검출에서 지도 좌표계 타겟 위치를 계산·발행.

        reid_node에서 온 타겟 바운딩박스(Detection2DArray)를 받아
        카트 포즈 + LiDAR 거리 + 카메라 화각을 이용해 지도 좌표를 계산한다.
        """
        # 타겟이 검출되지 않았으면 아무것도 하지 않음
        if not msg.detections:
            return

        # SLAM 포즈가 최근에 도착했는지 확인 (신선하지 않으면 발행 중단)
        if not self._pose_is_fresh():
            # 2초에 한 번씩만 경고 로그 출력 (콘솔 스팸 방지)
            self.get_logger().warn(
                "카트 포즈 미수신/지연 — 타겟 좌표 발행 보류 "
                "(SLAM 포즈 토픽 연결 확인)",
                throttle_duration_sec=2.0,
            )
            return

        try:
            # 첫 번째 검출(최고 신뢰도) 추출
            detection = msg.detections[0]
            # 바운딩박스 중심의 x, y 픽셀 좌표 추출 (구형/신형 레이아웃 지원)
            center_x, _center_y = _get_bbox_center(detection)
            # 픽셀 x를 [-1, 1] 정규화 (0 = 화면 중앙, +1 = 오른쪽 끝)
            center_x_normalized = normalize_center_x(center_x, self.image_width)
        except (ValueError, AttributeError) as error:
            # 메시지 구조 이상 시 에러 로그하고 반환
            self.get_logger().error(f"타겟 메시지 해석 실패: {error}")
            return

        # === LiDAR 거리 측정 ===
        # 정규화 x → LiDAR 조회각 변환 (센서 장착 보정 포함)
        lookup_angle = camera_bearing_to_lidar_angle(
            center_x_normalized,
            self.camera_fov_deg,
            self.lidar_yaw_offset_deg,
            self.lidar_mirrored,
        )
        # 바운딩박스 너비로부터 LiDAR 조회 반각(span) 계산
        # (박스 왼쪽~오른쪽의 거리 모두 고려하는 범위)
        half_span = bbox_half_span_rad(
            float(detection.bbox.size_x) * self.bbox_span_scale,
            self.image_width,
            self.camera_fov_deg,
        )
        # 범위 내에서 최소 유효 거리 획득 (객체가 있는 곳의 거리)
        distance = min_valid_range_in_span(self.latest_scan, lookup_angle, half_span)
        # 거리 측정 실패 시 발행 중단
        if distance is None:
            self.get_logger().warn(
                "LiDAR 거리 획득 실패 — 타겟 좌표 발행 보류",
                throttle_duration_sec=2.0,
            )
            return

        # === 지도 좌표 변환 ===
        # 정규화 x → 로봇 프레임 물리 방위각 (센서 보정 제외, 지도 변환용)
        bearing = robot_frame_bearing(center_x_normalized, self.camera_fov_deg)
        # 카트 포즈 + 상대 방위각 + 거리 → 타겟 지도 좌표(x, y)
        target_x, target_y = target_position_in_map(
            self.cart_x, self.cart_y, self.cart_yaw, bearing, float(distance)
        )

        # === 메시지 조립 및 발행 ===
        # PointStamped: 시간과 좌표를 담은 ROS2 메시지
        output = PointStamped()
        # 헤더: 현재 시각 (나노초)
        output.header.stamp = self.get_clock().now().to_msg()
        # 헤더: 좌표계 (보통 "map" = 지도 좌표계)
        output.header.frame_id = self.map_frame_id
        # 포인트 좌표: x (미터)
        output.point.x = target_x
        # 포인트 좌표: y (미터)
        output.point.y = target_y
        # 포인트 좌표: z (평면 주행이므로 0)
        output.point.z = 0.0
        # /target_position 토픽으로 발행 (SLAM Nav가 구독)
        self.position_pub.publish(output)


def main(args: Sequence[str] | None = None) -> None:
    """target_position_node를 시작·실행.

    Args:
        args: ROS2 노드 명령행 인자 (보통 None)
    """
    # ROS2 클라이언트 라이브러리 초기화
    rclpy.init(args=args)
    # TargetPositionNode 인스턴스 생성 (생성자에서 구독/발행 설정)
    node = TargetPositionNode()
    try:
        # 노드 실행: 메시지 수신·콜백 호출 반복 (무한 루프)
        rclpy.spin(node)
    except KeyboardInterrupt:
        # Ctrl+C 입력 시 graceful 종료
        pass
    finally:
        # 노드 리소스 정리 (구독/발행 해제)
        node.destroy_node()
        # ROS2 클라이언트 라이브러리 종료
        rclpy.shutdown()


# 이 파일을 스크립트로 직접 실행했을 때만 main() 호출
# (import되었을 때는 실행하지 않음)
if __name__ == "__main__":
    main()
