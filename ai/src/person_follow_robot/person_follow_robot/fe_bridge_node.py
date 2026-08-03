"""fe_bridge_node — FE 타겟 선택 연동 브릿지 (영상·트랙 하행, 선택 명령 상행).

사용자가 UI(영상+bbox)에서 추종 대상을 직접 고르는 모드를 위해 카트(Jetson)와
BE 사이를 잇는다. reid_node는 auto_select_enabled:=false로 실행한다.

- 영상 하행: /camera/image_raw → JPEG(품질 jpeg_quality) → BE WebSocket
  (video_ws_url, 바이너리 1메시지=1프레임, video_fps로 제한·초과분 폐기)
- 트랙 하행: /person_tracks → {"image_width","image_height","tracks":[{id,x,y,w,h}]}
  → MQTT tracks_topic (tracks_rate_hz로 제한)
- 선택 상행: MQTT command_topic의 {"command":"SELECT_TARGET","trackId":N}
  → /select_target(Int32) 발행 → reid_node가 등록 시작

의존성(Jetson에 설치 필요): `pip3 install websocket-client paho-mqtt`
연결 실패 시 노드는 죽지 않고 주기적으로 재접속을 시도한다 (BE보다 먼저
떠도 안전). 순수 로직은 fe_bridge_logic.py, 테스트는 ai/test/test_fe_bridge_logic.py.
"""

import time
from collections.abc import Sequence

import cv2
import rclpy
from cv_bridge import CvBridge, CvBridgeError
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Int32
from vision_msgs.msg import Detection2DArray

try:
    from .fe_bridge_logic import (
        RateLimiter,
        build_tracks_payload,
        parse_select_command,
    )
except ImportError:  # pytest가 노드 디렉토리를 sys.path에 놓고 단일 모듈로 import
    from fe_bridge_logic import (
        RateLimiter,
        build_tracks_payload,
        parse_select_command,
    )

try:
    from .control_node import _get_bbox_center
except ImportError:
    from control_node import _get_bbox_center

RECONNECT_INTERVAL_SEC = 3.0


class FeBridgeNode(Node):
    """Bridge camera frames/tracks down to the BE and target selection back up."""

    def __init__(self) -> None:
        """Declare parameters, connect lazily, and wire the topic pipeline."""
        super().__init__("fe_bridge_node")

        self.declare_parameter(
            "video_ws_url", "ws://localhost:8080/ws/carts/1/video/publish"
        )
        self.declare_parameter("mqtt_host", "localhost")
        self.declare_parameter("mqtt_port", 1883)
        self.declare_parameter("mqtt_username", "")
        self.declare_parameter("mqtt_password", "")
        self.declare_parameter("tracks_topic", "status/target")
        self.declare_parameter("command_topic", "cmd/move/cart")
        self.declare_parameter("video_fps", 10.0)
        self.declare_parameter("jpeg_quality", 70)
        self.declare_parameter("tracks_rate_hz", 5.0)

        self._video_ws_url = str(self.get_parameter("video_ws_url").value)
        self._jpeg_quality = int(self.get_parameter("jpeg_quality").value)
        self._tracks_topic = str(self.get_parameter("tracks_topic").value)
        self._command_topic = str(self.get_parameter("command_topic").value)

        video_fps = float(self.get_parameter("video_fps").value)
        tracks_hz = float(self.get_parameter("tracks_rate_hz").value)
        self._video_limiter = RateLimiter(1.0 / video_fps if video_fps > 0 else 0.0)
        self._tracks_limiter = RateLimiter(1.0 / tracks_hz if tracks_hz > 0 else 0.0)

        try:
            import websocket

            self._websocket_module = websocket
        except ImportError as error:
            self.get_logger().fatal(
                "websocket-client가 필요합니다: pip3 install websocket-client"
            )
            raise RuntimeError("websocket-client not installed") from error

        self._bridge = CvBridge()
        self._video_ws = None
        self._last_ws_attempt_at = 0.0

        self._mqtt_client = self._connect_mqtt()

        self.create_subscription(Image, "/camera/image_raw", self._image_callback, 10)
        self.create_subscription(
            Detection2DArray, "/person_tracks", self._tracks_callback, 10
        )
        self._select_publisher = self.create_publisher(Int32, "/select_target", 10)

        self.get_logger().info(
            f"FE 브릿지 시작 (video={self._video_ws_url}, "
            f"tracks={self._tracks_topic}, cmd={self._command_topic})"
        )

    def _connect_mqtt(self):  # noqa: ANN202 — paho 지연 import라 타입 명시 불가
        """Paho MQTT 클라이언트를 만들고 명령 토픽 구독을 건다."""
        try:
            import paho.mqtt.client as mqtt
        except ImportError as error:
            self.get_logger().fatal(
                "paho-mqtt가 필요합니다: pip3 install paho-mqtt"
            )
            raise RuntimeError("paho-mqtt not installed") from error

        client = mqtt.Client()
        username = str(self.get_parameter("mqtt_username").value)
        if username:
            client.username_pw_set(
                username, str(self.get_parameter("mqtt_password").value)
            )
        client.on_connect = self._on_mqtt_connect
        client.on_message = self._on_mqtt_message
        host = str(self.get_parameter("mqtt_host").value)
        port = int(self.get_parameter("mqtt_port").value)
        # connect_async + loop_start: 브로커가 늦게 떠도 자동 재접속
        client.connect_async(host, port)
        client.loop_start()
        return client

    def _on_mqtt_connect(self, client, userdata, flags, rc) -> None:  # noqa: ANN001
        self.get_logger().info(f"MQTT 연결됨 (rc={rc}), {self._command_topic} 구독")
        client.subscribe(self._command_topic)

    def _on_mqtt_message(self, client, userdata, message) -> None:  # noqa: ANN001
        track_id = parse_select_command(message.payload.decode(errors="replace"))
        if track_id is None:
            return  # SELECT_TARGET이 아닌 명령(MOVE 등)은 무시
        output = Int32()
        output.data = track_id
        self._select_publisher.publish(output)
        self.get_logger().info(f"FE 타겟 선택 수신 → /select_target {track_id}")

    def _image_callback(self, message: Image) -> None:
        if not self._video_limiter.should_send(time.monotonic()):
            return
        websocket_connection = self._ensure_video_ws()
        if websocket_connection is None:
            return
        try:
            frame = self._bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
            ok, jpeg = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality]
            )
            if not ok:
                return
            websocket_connection.send_binary(jpeg.tobytes())
        except CvBridgeError as error:
            self.get_logger().error(f"프레임 변환 실패: {error}")
        except Exception as error:  # noqa: BLE001 — 소켓 끊김은 재접속으로 복구
            self.get_logger().warn(
                f"영상 전송 실패, 재접속 예정: {error}", throttle_duration_sec=5.0
            )
            self._close_video_ws()

    def _tracks_callback(self, message: Detection2DArray) -> None:
        if not self._tracks_limiter.should_send(time.monotonic()):
            return
        tracks = []
        image_width, image_height = 640, 480
        for detection in message.detections:
            try:
                track_id = int(detection.id)
            except (TypeError, ValueError):
                continue
            center_x, center_y = _get_bbox_center(detection)
            tracks.append((
                track_id,
                center_x,
                center_y,
                float(detection.bbox.size_x),
                float(detection.bbox.size_y),
            ))
        payload = build_tracks_payload(image_width, image_height, tracks)
        try:
            import json

            self._mqtt_client.publish(self._tracks_topic, json.dumps(payload))
        except Exception as error:  # noqa: BLE001 — 발행 실패는 다음 주기에 재시도
            self.get_logger().warn(
                f"트랙 발행 실패: {error}", throttle_duration_sec=5.0
            )

    def _ensure_video_ws(self):  # noqa: ANN202 — websocket 지연 import
        """영상 WS 연결을 반환한다 (없으면 재접속 간격을 지켜 재시도)."""
        if self._video_ws is not None:
            return self._video_ws
        now = time.monotonic()
        if now - self._last_ws_attempt_at < RECONNECT_INTERVAL_SEC:
            return None
        self._last_ws_attempt_at = now
        try:
            self._video_ws = self._websocket_module.create_connection(
                self._video_ws_url, timeout=3
            )
            self.get_logger().info(f"영상 WS 연결됨: {self._video_ws_url}")
        except Exception as error:  # noqa: BLE001 — BE 미기동 시 재시도
            self.get_logger().warn(
                f"영상 WS 연결 실패 (재시도 예정): {error}",
                throttle_duration_sec=10.0,
            )
            self._video_ws = None
        return self._video_ws

    def _close_video_ws(self) -> None:
        if self._video_ws is not None:
            try:
                self._video_ws.close()
            except Exception:  # noqa: BLE001 — 이미 끊긴 소켓 정리
                pass
        self._video_ws = None

    def destroy_node(self) -> None:
        """Close network connections before the node is destroyed."""
        self._close_video_ws()
        try:
            self._mqtt_client.loop_stop()
            self._mqtt_client.disconnect()
        except Exception:  # noqa: BLE001 — 종료 중 예외는 무시
            pass
        super().destroy_node()


def main(args: Sequence[str] | None = None) -> None:
    """Start the FE bridge node."""
    rclpy.init(args=args)
    node = FeBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
