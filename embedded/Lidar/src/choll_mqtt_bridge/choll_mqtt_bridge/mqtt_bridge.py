"""MQTT↔ROS2 브릿지 노드.

EM-BE MQTT 명세서와 AI-EM ROS2 명세서 사이의 번역기:

- MQTT-04 ``cmd/move/cart`` 수신 → MOVE는 ``/cart/target_pose``(ROS2-14),
  CANCEL은 ``/cart/cancel``(ROS2-15, data=requestId)로 발행
- ``/robot_pose``(ROS2-08) 구독 → MQTT-01 ``status/position`` 발행
  (주기 스로틀, 기본 2Hz, 페이로드는 BE 파서 실측 계약)
- ``/cart/nav_status``(ROS2-16, 래치) 구독 → MQTT ``status/nav-result`` 발행
  (상태가 **바뀔 때만**, QoS1. BE가 이동 세션을 종료하는 신호라 유실되면
  FE의 이동이 영영 안 끝난다)
- SELECT_TARGET은 AI ``fe_bridge_node``가 ``/select_target`` 변환을 담당하므로
  무시하고, FOLLOW_*는 EM/AI 수신측 계약 확정 전까지 로그만 남긴다.

paho-mqtt 콜백은 별도 네트워크 스레드에서 실행되므로 ROS 발행은
스레드 안전 큐에 넣고 ROS 타이머가 꺼내 발행한다.
"""

import queue

import paho.mqtt.client as mqtt
import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy, QoSProfile, QoSReliabilityPolicy
from std_msgs.msg import String

from choll_mqtt_bridge.bridge_logic import (
    build_nav_result_payload,
    build_position_payload,
    parse_cart_command,
    should_publish_position,
    yaw_from_quaternion,
)


class MqttBridge(Node):
    """MQTT 브로커와 ROS2 토픽 사이를 중계하는 노드."""

    def __init__(self) -> None:
        """파라미터 선언, ROS 인터페이스 생성, MQTT 접속을 시작한다."""
        super().__init__("mqtt_bridge")
        self.declare_parameter("broker_host", "your-server.example.com")
        self.declare_parameter("broker_port", 1883)
        self.declare_parameter("username", "choll")
        self.declare_parameter("password", "CHANGE_ME")
        self.declare_parameter("client_id", "choll-jetson-bridge")
        self.declare_parameter("cmd_topic", "cmd/move/cart")
        self.declare_parameter("position_topic", "status/position")
        self.declare_parameter("position_min_period_sec", 0.5)
        self.declare_parameter("nav_result_topic", "status/nav-result")
        self.declare_parameter("pose_topic", "/robot_pose")
        self.declare_parameter("target_pose_topic", "/cart/target_pose")
        self.declare_parameter("cancel_topic", "/cart/cancel")
        self.declare_parameter("nav_status_topic", "/cart/nav_status")

        self._cmd_topic = str(self.get_parameter("cmd_topic").value)
        self._position_topic = str(self.get_parameter("position_topic").value)
        self._nav_result_topic = str(self.get_parameter("nav_result_topic").value)
        self._position_min_period = float(
            self.get_parameter("position_min_period_sec").value
        )

        self._cmd_queue: queue.Queue[dict] = queue.Queue()
        self._last_position_pub_sec: float | None = None
        self._last_nav_status: str | None = None

        self._target_pose_pub = self.create_publisher(
            PoseStamped, str(self.get_parameter("target_pose_topic").value), 10
        )
        self._cancel_pub = self.create_publisher(
            String, str(self.get_parameter("cancel_topic").value), 10
        )
        self.create_subscription(
            PoseStamped, str(self.get_parameter("pose_topic").value), self._on_pose, 10
        )
        # goal_forwarder는 /cart/nav_status를 래치(TRANSIENT_LOCAL)로 발행한다.
        # 구독도 맞춰야 브릿지가 늦게 떠도 **현재 상태를 즉시 받아** BE와 동기화된다.
        self.create_subscription(
            String,
            str(self.get_parameter("nav_status_topic").value),
            self._on_nav_status,
            QoSProfile(
                depth=1,
                reliability=QoSReliabilityPolicy.RELIABLE,
                durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            ),
        )
        self.create_timer(0.05, self._drain_cmd_queue)

        self._mqtt = self._make_mqtt_client()

    # ── MQTT 측 (paho 네트워크 스레드에서 콜백 실행) ──────────────────

    def _make_mqtt_client(self) -> mqtt.Client:
        """Paho 클라이언트를 만들고 백그라운드 접속 루프를 시작한다.

        paho 2.x는 첫 인자로 ``callback_api_version``을 받는다. 기본값이
        ``VERSION1``이라 인자를 생략해도 지금은 동작하지만 DeprecationWarning이
        뜨고 향후 제거될 수 있으므로 명시한다. 이 노드의 콜백 시그니처는
        VERSION1 규약(``rc``/``flags``)이므로 VERSION1을 고정한다.
        paho 1.x에는 ``CallbackAPIVersion``이 없어 인자를 넘기면 실패한다.
        """
        client_id = str(self.get_parameter("client_id").value)
        if hasattr(mqtt, "CallbackAPIVersion"):  # paho 2.x
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=client_id)
        else:  # paho 1.x
            client = mqtt.Client(client_id=client_id)
        client.username_pw_set(
            str(self.get_parameter("username").value),
            str(self.get_parameter("password").value),
        )
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        client.on_connect = self._on_mqtt_connect
        client.on_disconnect = self._on_mqtt_disconnect
        client.on_message = self._on_mqtt_message
        host = str(self.get_parameter("broker_host").value)
        port = int(self.get_parameter("broker_port").value)
        client.connect_async(host, port, keepalive=30)
        client.loop_start()
        self.get_logger().info(f"MQTT 브로커 접속 시도: {host}:{port}")
        return client

    def _on_mqtt_connect(
        self, client: mqtt.Client, userdata: object, flags: dict, rc: int
    ) -> None:
        """접속 성공 시 명령 토픽을 구독한다 (재접속 시에도 호출됨)."""
        if rc != 0:
            self.get_logger().error(f"MQTT 접속 거부: {mqtt.connack_string(rc)}")
            return
        client.subscribe(self._cmd_topic, qos=1)
        self.get_logger().info(f"MQTT 접속·구독 완료: {self._cmd_topic} (QoS1)")

    def _on_mqtt_disconnect(
        self, client: mqtt.Client, userdata: object, rc: int
    ) -> None:
        """접속 끊김을 기록한다 (paho가 자동 재접속)."""
        if rc != 0:
            self.get_logger().warning(f"MQTT 접속 끊김(rc={rc}) — 자동 재접속 대기")

    def _on_mqtt_message(
        self, client: mqtt.Client, userdata: object, msg: mqtt.MQTTMessage
    ) -> None:
        """명령 페이로드를 파싱해 ROS 타이머 큐로 넘긴다."""
        self._cmd_queue.put(parse_cart_command(msg.payload))

    # ── ROS 측 ────────────────────────────────────────────────────────

    def _drain_cmd_queue(self) -> None:
        """큐에 쌓인 MQTT 명령을 ROS 토픽으로 발행한다."""
        while True:
            try:
                cmd = self._cmd_queue.get_nowait()
            except queue.Empty:
                return
            kind = cmd["kind"]
            if kind == "move":
                pose = PoseStamped()
                pose.header.frame_id = "map"
                pose.header.stamp = self.get_clock().now().to_msg()
                pose.pose.position.x = cmd["x"]
                pose.pose.position.y = cmd["y"]
                pose.pose.orientation.w = 1.0
                self._target_pose_pub.publish(pose)
                self.get_logger().info(
                    f"MOVE → /cart/target_pose ({cmd['x']:.2f}, {cmd['y']:.2f}) "
                    f"requestId={cmd['request_id']!r} zoneId={cmd['zone_id']!r}"
                )
            elif kind == "cancel":
                self._cancel_pub.publish(String(data=cmd["request_id"]))
                self.get_logger().info(
                    f"CANCEL → /cart/cancel requestId={cmd['request_id']!r}"
                )
            elif kind == "select_target":
                self.get_logger().info(
                    "SELECT_TARGET 수신 — AI fe_bridge_node가 /select_target "
                    "변환을 담당하므로 이 브릿지는 무시"
                )
            elif kind == "follow":
                self.get_logger().warning(
                    f"FOLLOW 명령 수신 — EM/AI 수신측 계약 미확정이라 보류: {cmd}"
                )
            else:
                self.get_logger().warning(f"명령 무시: {cmd['reason']}")

    def _on_pose(self, msg: PoseStamped) -> None:
        """/robot_pose를 스로틀 후 MQTT 위치 텔레메트리로 발행한다."""
        now_sec = self.get_clock().now().nanoseconds * 1e-9
        if not should_publish_position(
            now_sec, self._last_position_pub_sec, self._position_min_period
        ):
            return
        if not self._mqtt.is_connected():
            return
        q = msg.pose.orientation
        payload = build_position_payload(
            msg.pose.position.x,
            msg.pose.position.y,
            yaw_from_quaternion(q.x, q.y, q.z, q.w),
            msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
        )
        self._mqtt.publish(self._position_topic, payload, qos=0)
        self._last_position_pub_sec = now_sec

    def _on_nav_status(self, msg: String) -> None:
        """/cart/nav_status를 MQTT 주행 결과로 중계한다.

        위치와 달리 **상태 전이 이벤트**라 스로틀하지 않고 변화 시에만 보낸다.
        QoS1인 이유는 유실되면 BE의 이동 세션이 끝나지 않아 FE에서 카트가
        영원히 "이동 중"으로 남기 때문이다.
        """
        status = msg.data.strip().upper()
        if status == self._last_nav_status:
            return

        payload = build_nav_result_payload(status)
        if payload is None:
            self.get_logger().warning(
                f"계약 밖 주행 상태라 발행하지 않음: {msg.data!r} "
                "(BE는 모르는 값을 조용히 버려 이동 세션이 안 끝난다)"
            )
            return

        if not self._mqtt.is_connected():
            self.get_logger().warning(
                f"MQTT 미접속 — 주행 상태 {status} 유실. "
                "재접속 후 다음 전이부터 반영된다"
            )
            return

        self._mqtt.publish(self._nav_result_topic, payload, qos=1)
        self._last_nav_status = status
        self.get_logger().info(f"/cart/nav_status {status} → {self._nav_result_topic}")

    def shutdown_mqtt(self) -> None:
        """MQTT 백그라운드 루프를 정리한다."""
        self._mqtt.loop_stop()
        self._mqtt.disconnect()


def main(args: "list[str] | None" = None) -> None:
    """mqtt_bridge 노드를 실행한다.

    Args:
        args: rclpy 초기화 인자.
    """
    rclpy.init(args=args)
    node = MqttBridge()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.shutdown_mqtt()
        node.destroy_node()
        rclpy.try_shutdown()
