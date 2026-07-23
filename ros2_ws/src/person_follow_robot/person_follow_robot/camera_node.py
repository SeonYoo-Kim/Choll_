"""Acquire RGB frames from a camera and publish them to ROS 2."""

import rclpy
from rclpy.node import Node
import cv2
from cv_bridge import CvBridge, CvBridgeError
from sensor_msgs.msg import Image


class CameraNode(Node):
    """Publish camera frames independently from AI inference."""

    def __init__(self):
        super().__init__("camera_node")

        self.declare_parameter("camera_index", 0)
        self.declare_parameter("video_path", "")
        self.declare_parameter("frame_width", 640)
        self.declare_parameter("frame_height", 480)
        self.declare_parameter("publish_rate_hz", 30.0)

        camera_index = self.get_parameter("camera_index").value
        video_path = str(self.get_parameter("video_path").value).strip()
        frame_width = self.get_parameter("frame_width").value
        frame_height = self.get_parameter("frame_height").value
        rate_hz = self.get_parameter("publish_rate_hz").value

        self.bridge = CvBridge()
        self.video_path = video_path
        self.cap = cv2.VideoCapture(video_path if video_path else camera_index)
        if not video_path:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, frame_width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, frame_height)

        if not self.cap.isOpened():
            self.get_logger().error("카메라를 열 수 없습니다.")
            raise RuntimeError("camera input open failed")

        self.publisher = self.create_publisher(Image, "/camera/image_raw", 10)
        self.timer = self.create_timer(1.0 / rate_hz, self.timer_callback)

        if video_path:
            self.get_logger().info(
                f"Camera node started with video file: {video_path} "
                f"(rate={rate_hz:.1f} Hz)"
            )
        else:
            self.get_logger().info(
                f"Camera node started (device={camera_index}, rate={rate_hz:.1f} Hz)"
            )

    def timer_callback(self):
        ret, frame = self.cap.read()
        if not ret:
            if self.video_path:
                self.get_logger().info("Video input reached EOF, rewinding to start")
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
                if ret:
                    self._publish_frame(frame)
                return
            self.get_logger().warning("Failed to read a camera frame")
            return

        self._publish_frame(frame)

    def _publish_frame(self, frame):
        try:
            message = self.bridge.cv2_to_imgmsg(frame, encoding="bgr8")
        except CvBridgeError as error:
            self.get_logger().error(f"Failed to convert camera frame: {error}")
            return

        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = "camera_optical_frame"
        self.publisher.publish(message)

    def destroy_node(self):
        self.cap.release()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = CameraNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
