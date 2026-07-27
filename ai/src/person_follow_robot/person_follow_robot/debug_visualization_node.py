"""Debug visualization node for tracked persons and Re-ID recovery events."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge, CvBridgeError
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Float32, String
from vision_msgs.msg import Detection2D, Detection2DArray

BLUE = (255, 80, 30)
GREEN = (40, 220, 60)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (40, 40, 240)


@dataclass(frozen=True)
class DrawBox:
    """Drawable tracked person box."""

    track_id: int
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass
class RecoveryOverlay:
    """Short-lived recovery event shown on the debug image."""

    track_id: int
    similarity: float
    started_at: float


def _parse_bool(value: object) -> bool:
    """Parse bool-like ROS launch parameter values."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _get_bbox_center(detection: Detection2D) -> tuple[float, float]:
    """Read BoundingBox2D center across common vision_msgs layouts."""
    center = detection.bbox.center
    if hasattr(center, "position"):
        return float(center.position.x), float(center.position.y)
    return float(center.x), float(center.y)


class DebugVisualizationNode(Node):
    """Publish presentation-friendly overlay images for tracking and Re-ID."""

    def __init__(self) -> None:
        """Declare parameters and wire subscriptions/publisher."""
        super().__init__("debug_visualization_node")
        self.declare_parameter("save_debug_video", False)
        self.declare_parameter("debug_video_path", "result.mp4")
        self.declare_parameter("debug_video_fps", 30.0)
        self.declare_parameter("recovery_overlay_duration_sec", 2.0)
        self.declare_parameter("distance_display_timeout_sec", 1.0)

        self._save_debug_video = _parse_bool(
            self.get_parameter("save_debug_video").value
        )
        self._debug_video_path = Path(
            str(self.get_parameter("debug_video_path").value)
        )
        self._debug_video_fps = float(
            self.get_parameter("debug_video_fps").value
        )
        self._recovery_overlay_duration_sec = float(
            self.get_parameter("recovery_overlay_duration_sec").value
        )
        self._distance_display_timeout_sec = float(
            self.get_parameter("distance_display_timeout_sec").value
        )

        self._bridge = CvBridge()
        self._tracks: list[DrawBox] = []
        self._target_track_id: int | None = None
        self._target_distance_m: float | None = None
        self._distance_updated_at = 0.0
        self._recovery_overlay: RecoveryOverlay | None = None
        self._video_writer: cv2.VideoWriter | None = None

        self.create_subscription(
            Detection2DArray, "/person_tracks", self._tracks_callback, 10
        )
        self.create_subscription(
            Detection2DArray, "/target_person", self._target_callback, 10
        )
        self.create_subscription(
            String, "/reid/recovery_event", self._recovery_event_callback, 10
        )
        self.create_subscription(
            Float32, "/target_distance", self._distance_callback, 10
        )
        self.create_subscription(Image, "/camera/image_raw", self._image_callback, 10)
        self._publisher = self.create_publisher(Image, "/debug/image", 10)

        self.get_logger().info("Debug visualization node started")
        if self._save_debug_video:
            self.get_logger().info(
                f"Debug video saving enabled: {self._debug_video_path}"
            )

    def _tracks_callback(self, message: Detection2DArray) -> None:
        tracks: list[DrawBox] = []
        for detection in message.detections:
            box = self._to_draw_box(detection)
            if box is not None:
                tracks.append(box)
        self._tracks = tracks

    def _target_callback(self, message: Detection2DArray) -> None:
        if not message.detections:
            self._target_track_id = None
            return
        try:
            self._target_track_id = int(message.detections[0].id)
        except (TypeError, ValueError):
            self._target_track_id = None

    def _distance_callback(self, message: Float32) -> None:
        self._target_distance_m = float(message.data)
        self._distance_updated_at = time.monotonic()

    def _recovery_event_callback(self, message: String) -> None:
        try:
            payload = json.loads(message.data)
            track_id = int(payload["track_id"])
            similarity = float(payload["similarity"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self.get_logger().warn(f"Invalid recovery event payload: {error}")
            return

        self._recovery_overlay = RecoveryOverlay(
            track_id=track_id,
            similarity=similarity,
            started_at=time.monotonic(),
        )
        self.get_logger().info(
            f"Showing RECOVERED overlay: ID={track_id}, similarity={similarity:.3f}"
        )

    def _image_callback(self, message: Image) -> None:
        try:
            frame = self._bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
        except CvBridgeError as error:
            self.get_logger().error(f"Failed to convert debug image: {error}")
            return

        output = frame.copy()
        self._draw_tracks(output)
        self._draw_status(output)
        self._draw_recovery_overlay(output)
        self._publish_debug_image(output, message)
        self._write_debug_video(output)

    def _draw_tracks(self, frame: np.ndarray) -> None:
        for box in self._tracks:
            is_target = box.track_id == self._target_track_id
            color = GREEN if is_target else BLUE
            thickness = 4 if is_target else 3
            label = (
                f"TARGET ID {box.track_id}" if is_target else f"ID {box.track_id}"
            )

            cv2.rectangle(
                frame,
                (box.x1, box.y1),
                (box.x2, box.y2),
                color,
                thickness,
            )
            self._draw_label(frame, label, box.x1, max(32, box.y1 - 10), color)

            if is_target:
                distance_text = self._current_distance_text()
                if distance_text is not None:
                    self._draw_label_right_aligned(
                        frame, distance_text, box.x2, max(32, box.y1 - 10), GREEN
                    )

    def _current_distance_text(self) -> str | None:
        """Return the target distance label, or None if no fresh message.

        NaN from control_node means the target is visible but no valid LiDAR
        range was found (driver not running, or all rays invalid at that angle).
        """
        if self._target_distance_m is None:
            return None
        age = time.monotonic() - self._distance_updated_at
        if age > self._distance_display_timeout_sec:
            return None
        if math.isnan(self._target_distance_m):
            return "NO LIDAR"
        return f"{self._target_distance_m:.2f}m"

    def _draw_status(self, frame: np.ndarray) -> None:
        track_count = len(self._tracks)
        target_text = (
            "TARGET: NONE"
            if self._target_track_id is None
            else f"TARGET: ID {self._target_track_id}"
        )
        # DIST "--"는 /target_distance 미수신(control_node 미동작/타겟 미인식) 상태
        distance_text = self._current_distance_text() or "--"
        self._draw_banner(
            frame,
            f"Re-ID Debug | Tracks: {track_count} | {target_text}"
            f" | DIST: {distance_text}",
            20,
            42,
            BLACK,
        )

    def _draw_recovery_overlay(self, frame: np.ndarray) -> None:
        overlay = self._recovery_overlay
        if overlay is None:
            return

        elapsed = time.monotonic() - overlay.started_at
        if elapsed > self._recovery_overlay_duration_sec:
            self._recovery_overlay = None
            return

        text = f"RECOVERED  ID {overlay.track_id}  SIM {overlay.similarity:.3f}"
        height, width = frame.shape[:2]
        x = max(20, width // 2 - 330)
        y = max(90, height // 6)
        self._draw_banner(frame, text, x, y, RED)

    def _publish_debug_image(self, frame: np.ndarray, source_message: Image) -> None:
        try:
            output = self._bridge.cv2_to_imgmsg(frame, encoding="bgr8")
        except CvBridgeError as error:
            self.get_logger().error(f"Failed to publish debug image: {error}")
            return

        output.header = source_message.header
        self._publisher.publish(output)

    def _write_debug_video(self, frame: np.ndarray) -> None:
        if not self._save_debug_video:
            return
        if self._video_writer is None:
            height, width = frame.shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self._video_writer = cv2.VideoWriter(
                str(self._debug_video_path),
                fourcc,
                self._debug_video_fps,
                (width, height),
            )
            if not self._video_writer.isOpened():
                self.get_logger().error(
                    f"Failed to open debug video: {self._debug_video_path}"
                )
                self._save_debug_video = False
                return
        self._video_writer.write(frame)

    @staticmethod
    def _draw_label(
        frame: np.ndarray,
        text: str,
        x: int,
        y: int,
        color: tuple[int, int, int],
    ) -> None:
        """Draw a filled label, clamped so it stays fully inside the frame.

        Boxes may extend past the image edges (partially visible person);
        without clamping the label would be drawn off-screen and lost.
        """
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.9
        thickness = 2
        (width, height), baseline = cv2.getTextSize(text, font, scale, thickness)
        frame_height, frame_width = frame.shape[:2]
        x = max(0, min(x, frame_width - width - 14))
        y = max(height + baseline + 8, min(y, frame_height - 6))
        cv2.rectangle(
            frame,
            (x, y - height - baseline - 8),
            (x + width + 14, y + 6),
            color,
            -1,
        )
        cv2.putText(frame, text, (x + 7, y - 5), font, scale, WHITE, thickness)

    @classmethod
    def _draw_label_right_aligned(
        cls,
        frame: np.ndarray,
        text: str,
        right_x: int,
        y: int,
        color: tuple[int, int, int],
    ) -> None:
        """Draw a label whose background right edge sits at ``right_x``."""
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.9
        thickness = 2
        (width, _height), _baseline = cv2.getTextSize(text, font, scale, thickness)
        cls._draw_label(frame, text, right_x - width - 14, y, color)

    @staticmethod
    def _draw_banner(
        frame: np.ndarray,
        text: str,
        x: int,
        y: int,
        color: tuple[int, int, int],
    ) -> None:
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 1.1
        thickness = 3
        (width, height), baseline = cv2.getTextSize(text, font, scale, thickness)
        cv2.rectangle(
            frame,
            (x - 10, y - height - baseline - 12),
            (x + width + 18, y + 12),
            color,
            -1,
        )
        cv2.putText(frame, text, (x, y), font, scale, WHITE, thickness)

    @staticmethod
    def _to_draw_box(detection: Detection2D) -> DrawBox | None:
        try:
            track_id = int(detection.id)
        except (TypeError, ValueError):
            return None

        center_x, center_y = _get_bbox_center(detection)
        half_width = float(detection.bbox.size_x) / 2.0
        half_height = float(detection.bbox.size_y) / 2.0
        return DrawBox(
            track_id=track_id,
            x1=int(round(center_x - half_width)),
            y1=int(round(center_y - half_height)),
            x2=int(round(center_x + half_width)),
            y2=int(round(center_y + half_height)),
        )

    def destroy_node(self) -> None:
        """Release the video writer before the node is destroyed."""
        if self._video_writer is not None:
            self._video_writer.release()
        super().destroy_node()


def main(args: Sequence[str] | None = None) -> None:
    """Start the debug visualization node."""
    rclpy.init(args=args)
    node = DebugVisualizationNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
