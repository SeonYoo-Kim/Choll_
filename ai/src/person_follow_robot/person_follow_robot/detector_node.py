"""YOLOv10s TensorRT person detector ROS 2 node."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import rclpy
from cv_bridge import CvBridge, CvBridgeError
from rclpy.node import Node
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose


PERSON_CLASS_ID = 0
PERSON_CLASS_NAME = "person"


@dataclass(frozen=True)
class PersonDetection:
    """Framework-independent person detection result in pixel coordinates."""

    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float


class YoloTensorRtDetector:
    """Load a TensorRT engine lazily and run person-only YOLO inference."""

    def __init__(self, engine_path: str, confidence_threshold: float) -> None:
        self._engine_path = Path(engine_path)
        self._confidence_threshold = confidence_threshold
        self._model: Any = self._load_model()

    def _load_model(self) -> Any:
        """Load the TensorRT engine through the Ultralytics inference wrapper."""
        if self._engine_path.suffix.lower() != ".engine":
            raise ValueError("model_path must reference a TensorRT .engine file")
        if not self._engine_path.is_file():
            raise FileNotFoundError(f"TensorRT engine not found: {self._engine_path}")

        try:
            from ultralytics import YOLO
        except ImportError as error:
            raise RuntimeError(
                "ultralytics is required to load the YOLO TensorRT engine"
            ) from error

        return YOLO(str(self._engine_path), task="detect")

    def detect(self, image: Any) -> list[PersonDetection]:
        """Return all person detections from one BGR image."""
        results: Sequence[Any] = self._model.predict(
            image,
            classes=[PERSON_CLASS_ID],
            conf=self._confidence_threshold,
            verbose=False,
        )
        if not results or results[0].boxes is None:
            return []

        boxes = results[0].boxes
        xyxy = boxes.xyxy.cpu().numpy()
        confidences = boxes.conf.cpu().numpy()
        return [
            PersonDetection(
                x1=float(box[0]),
                y1=float(box[1]),
                x2=float(box[2]),
                y2=float(box[3]),
                confidence=float(confidence),
            )
            for box, confidence in zip(xyxy, confidences)
        ]


class DetectorNode(Node):
    """Convert RGB images to person detections using YOLOv10s TensorRT."""

    def __init__(self) -> None:
        super().__init__("detector_node")
        self.declare_parameter("model_path", "models/yolov10s.engine")
        self.declare_parameter("confidence_threshold", 0.50)

        model_path = str(self.get_parameter("model_path").value)
        confidence_threshold = float(
            self.get_parameter("confidence_threshold").value
        )
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0.0 and 1.0")

        try:
            self._detector = YoloTensorRtDetector(model_path, confidence_threshold)
        except (FileNotFoundError, RuntimeError, ValueError) as error:
            self.get_logger().fatal(f"Detector initialization failed: {error}")
            raise

        self._bridge = CvBridge()
        self._publisher = self.create_publisher(
            Detection2DArray, "/person_detection", 10
        )
        self._subscription = self.create_subscription(
            Image, "/camera/image_raw", self._image_callback, 10
        )
        self.get_logger().info(
            f"Detector node started with TensorRT engine: {model_path}"
        )

    def _image_callback(self, message: Image) -> None:
        """Run inference for one camera image and publish all person detections."""
        try:
            image = self._bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
            detections = self._detector.detect(image)
        except CvBridgeError as error:
            self.get_logger().error(f"Failed to convert input image: {error}")
            return
        except Exception as error:  # Keep camera processing alive after inference errors.
            self.get_logger().error(f"Person detection failed: {error}")
            return

        output = Detection2DArray()
        output.header = message.header
        output.detections = [self._to_ros_detection(item) for item in detections]
        self._publisher.publish(output)

    @staticmethod
    def _to_ros_detection(source: PersonDetection) -> Detection2D:
        """Convert an internal detection into the ROS standard message type."""
        detection = Detection2D()
        DetectorNode._set_bbox_center(
            detection,
            (source.x1 + source.x2) / 2.0,
            (source.y1 + source.y2) / 2.0,
        )
        detection.bbox.size_x = source.x2 - source.x1
        detection.bbox.size_y = source.y2 - source.y1

        hypothesis = ObjectHypothesisWithPose()
        hypothesis.hypothesis.class_id = PERSON_CLASS_NAME
        hypothesis.hypothesis.score = source.confidence
        detection.results.append(hypothesis)
        return detection

    @staticmethod
    def _set_bbox_center(
        detection: Detection2D, center_x: float, center_y: float
    ) -> None:
        """Write BoundingBox2D center across common vision_msgs layouts."""
        center = detection.bbox.center
        if hasattr(center, "position"):
            center.position.x = center_x
            center.position.y = center_y
            return
        center.x = center_x
        center.y = center_y


def main(args: Sequence[str] | None = None) -> None:
    """Start the detector node."""
    rclpy.init(args=args)
    node = DetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
