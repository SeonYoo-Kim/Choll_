"""카트 현재 위치 발행 노드.

TF map→base_link를 조회해 PoseStamped를 파라미터로 지정한 여러 토픽
(기본: /robot_pose, /cart/pose)에 동시 발행한다. /robot_pose는 AI 파트
target_position_node와의 확정 계약(2026-07-31), /cart/pose는 BE 연동용
README 계약이다. QoS는 RELIABLE — AI 쪽이 기본 QoS로 구독하므로
BestEffort로 바꾸면 전달되지 않는다.
"""

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.publisher import Publisher
from tf2_ros import Buffer, TransformException, TransformListener


class CartPosePublisher(Node):
    """TF 기반 카트 위치를 주기 발행하는 노드."""

    def __init__(self) -> None:
        """파라미터 선언, TF 리스너와 발행자·타이머를 초기화한다."""
        super().__init__("cart_pose_publisher")
        self.declare_parameter("pose_topics", ["/robot_pose", "/cart/pose"])
        self.declare_parameter("publish_rate_hz", 10.0)
        self.declare_parameter("map_frame", "map")
        self.declare_parameter("base_frame", "base_link")

        self._map_frame: str = str(self.get_parameter("map_frame").value)
        self._base_frame: str = str(self.get_parameter("base_frame").value)
        rate_hz = float(self.get_parameter("publish_rate_hz").value)
        topics = [
            str(t) for t in self.get_parameter("pose_topics").value or [] if t
        ]

        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)
        self._pose_pubs: list[Publisher] = [
            self.create_publisher(PoseStamped, topic, 10) for topic in topics
        ]
        self.create_timer(1.0 / rate_hz, self._on_timer)
        self.get_logger().info(
            f"카트 위치 발행 시작: {topics} @ {rate_hz}Hz "
            f"({self._map_frame}->{self._base_frame})"
        )

    def _on_timer(self) -> None:
        """TF를 조회해 모든 대상 토픽으로 현재 위치를 발행한다."""
        try:
            transform = self._tf_buffer.lookup_transform(
                self._map_frame, self._base_frame, rclpy.time.Time()
            )
        except TransformException:
            self.get_logger().warning(
                f"TF {self._map_frame}->{self._base_frame} 조회 실패 — "
                "SLAM(slam_toolbox)이 떠 있는지 확인",
                throttle_duration_sec=5.0,
            )
            return
        try:
            msg = PoseStamped()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = self._map_frame
            msg.pose.position.x = transform.transform.translation.x
            msg.pose.position.y = transform.transform.translation.y
            msg.pose.position.z = transform.transform.translation.z
            msg.pose.orientation = transform.transform.rotation
            for pub in self._pose_pubs:
                pub.publish(msg)
        except Exception as exc:  # noqa: BLE001 — 콜백은 죽지 않고 로깅
            self.get_logger().error(f"위치 발행 실패: {exc}")


def main(args: list[str] | None = None) -> None:
    """cart_pose_publisher 노드를 실행한다.

    Args:
        args: rclpy 초기화 인자.
    """
    rclpy.init(args=args)
    node = CartPosePublisher()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
