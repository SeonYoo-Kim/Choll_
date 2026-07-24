"""ByteTrack ROS 2 node for assigning stable IDs to person detections."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Sequence

import numpy as np
import rclpy
from rclpy.node import Node
from vision_msgs.msg import Detection2D, Detection2DArray


@dataclass(frozen=True)
class DetectionBox:
    """Detection box in xyxy pixel coordinates."""

    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float


def _get_bbox_center(detection: Detection2D) -> tuple[float, float]:
    """Read BoundingBox2D center across common vision_msgs layouts."""
    center = detection.bbox.center
    if hasattr(center, "position"):
        return float(center.position.x), float(center.position.y)
    return float(center.x), float(center.y)


class ByteTrackAdapter:
    """Small adapter around the ByteTrack implementation from supervision."""

    def __init__(
        self,
        track_activation_threshold: float,
        lost_track_buffer: int,
        minimum_matching_threshold: float,
        frame_rate: int,
    ) -> None:
        try:
            import supervision as sv
        except ImportError as error:
            raise RuntimeError(
                "supervision is required for ByteTrack. "
                "Install it in the ROS environment before running tracker_node."
            ) from error

        kwargs = {
            "track_activation_threshold": track_activation_threshold,
            "lost_track_buffer": lost_track_buffer,
            "minimum_matching_threshold": minimum_matching_threshold,
            "frame_rate": frame_rate,
            "track_thresh": track_activation_threshold,
            "track_buffer": lost_track_buffer,
            "match_thresh": minimum_matching_threshold,
        }
        signature = inspect.signature(sv.ByteTrack)
        filtered_kwargs = {
            name: value
            for name, value in kwargs.items()
            if name in signature.parameters
        }

        self._sv = sv
        self._tracker = sv.ByteTrack(**filtered_kwargs)

    def update(self, detections: Sequence[DetectionBox]) -> list[int | None]:
        """Update ByteTrack and return tracker IDs aligned to input detections."""
        if not detections:
            empty = self._sv.Detections.empty()
            self._tracker.update_with_detections(empty)
            return []

        sv_detections = self._sv.Detections(
            xyxy=np.array(
                [[box.x1, box.y1, box.x2, box.y2] for box in detections],
                dtype=np.float32,
            ),
            confidence=np.array(
                [box.confidence for box in detections],
                dtype=np.float32,
            ),
            class_id=np.zeros(len(detections), dtype=int),
        )
        tracked = self._tracker.update_with_detections(sv_detections)
        tracker_ids = getattr(tracked, "tracker_id", None)
        if tracker_ids is None:
            return [None for _ in detections]
        return [
            None if track_id is None else int(track_id)
            for track_id in tracker_ids
        ]


class TrackerNode(Node):
    """Subscribe to person detections and publish ByteTrack-assigned tracks."""

    def __init__(self) -> None:
        super().__init__("tracker_node")
        self.declare_parameter("track_activation_threshold", 0.25)
        self.declare_parameter("lost_track_buffer", 30)
        self.declare_parameter("minimum_matching_threshold", 0.80)
        self.declare_parameter("frame_rate", 30)

        try:
            self._tracker = ByteTrackAdapter(
                float(self.get_parameter("track_activation_threshold").value),
                int(self.get_parameter("lost_track_buffer").value),
                float(self.get_parameter("minimum_matching_threshold").value),
                int(self.get_parameter("frame_rate").value),
            )
        except RuntimeError as error:
            self.get_logger().fatal(f"Tracker initialization failed: {error}")
            raise

        self._subscription = self.create_subscription(
            Detection2DArray, "/person_detection", self._detection_callback, 10
        )
        self._publisher = self.create_publisher(Detection2DArray, "/person_tracks", 10)
        self.get_logger().info("Tracker node started with ByteTrack")

    def _detection_callback(self, message: Detection2DArray) -> None:
        boxes = [self._to_box(detection) for detection in message.detections]
        track_ids = self._tracker.update(boxes)

        output = Detection2DArray()
        output.header = message.header
        output.detections = [
            self._with_track_id(detection, track_id)
            for detection, track_id in zip(message.detections, track_ids)
            if track_id is not None
        ]
        self._publisher.publish(output)

    @staticmethod
    def _to_box(detection: Detection2D) -> DetectionBox:
        center_x, center_y = _get_bbox_center(detection)
        half_width = float(detection.bbox.size_x) / 2.0
        half_height = float(detection.bbox.size_y) / 2.0
        confidence = 0.0
        if detection.results:
            confidence = float(detection.results[0].hypothesis.score)

        return DetectionBox(
            x1=center_x - half_width,
            y1=center_y - half_height,
            x2=center_x + half_width,
            y2=center_y + half_height,
            confidence=confidence,
        )

    @staticmethod
    def _with_track_id(detection: Detection2D, track_id: int | None) -> Detection2D:
        tracked_detection = Detection2D()
        tracked_detection.header = detection.header
        tracked_detection.results = detection.results
        tracked_detection.bbox = detection.bbox
        tracked_detection.id = "" if track_id is None else str(track_id)
        return tracked_detection


def main(args: Sequence[str] | None = None) -> None:
    """Start the tracker node."""
    rclpy.init(args=args)
    node = TrackerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
