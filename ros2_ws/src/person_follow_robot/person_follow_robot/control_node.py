"""
control_node
- /person_detection (카메라, 좌우 각도용) 구독
- /scan (LiDAR, sensor_msgs/LaserScan, 거리용) 구독
- 두 정보를 합쳐서 목표 거리(TARGET_DISTANCE_M) 유지하도록 PID 계산
- /cmd_vel (geometry_msgs/Twist) publish

좌우 각도(center_x_normalized, -1~1)를 실제 카메라 화각(FOV)에 맞는 각도로 변환한 뒤,
LiDAR의 해당 각도 근방 range 값들을 평균 내어 거리로 사용.
카메라와 LiDAR가 로봇 위에서 물리적으로 다른 위치에 있다면 정확히는 tf2로 좌표 변환해야 하지만,
1단계에서는 두 센서가 로봇 정면 기준으로 거의 같은 방향을 보고 있다고 가정하고 단순화함.
"""

import math
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray
from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import Twist


class PID:
    def __init__(self, kp, ki, kd, output_limit):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.integral = 0.0
        self.prev_error = 0.0
        self.output_limit = output_limit

    def compute(self, error, dt):
        self.integral += error * dt
        derivative = (error - self.prev_error) / dt if dt > 0 else 0.0
        output = self.kp * error + self.ki * self.integral + self.kd * derivative
        self.prev_error = error
        return max(-self.output_limit, min(self.output_limit, output))


class ControlNode(Node):
    def __init__(self):
        super().__init__("control_node")

        self.declare_parameter("target_distance_m", 1.0)   # 요청하신 목표 거리 1m
        self.declare_parameter("camera_fov_deg", 60.0)      # 카메라 수평 화각, 실제 스펙에 맞게 조정
        self.declare_parameter("angular_kp", 0.8)
        self.declare_parameter("angular_ki", 0.0)
        self.declare_parameter("angular_kd", 0.1)
        self.declare_parameter("linear_kp", 0.5)
        self.declare_parameter("linear_ki", 0.0)
        self.declare_parameter("linear_kd", 0.05)
        self.declare_parameter("max_linear_vel", 0.5)
        self.declare_parameter("max_angular_vel", 1.0)

        self.target_distance = self.get_parameter("target_distance_m").value
        self.camera_fov_deg = self.get_parameter("camera_fov_deg").value

        self.angular_pid = PID(
            self.get_parameter("angular_kp").value,
            self.get_parameter("angular_ki").value,
            self.get_parameter("angular_kd").value,
            self.get_parameter("max_angular_vel").value,
        )
        self.linear_pid = PID(
            self.get_parameter("linear_kp").value,
            self.get_parameter("linear_ki").value,
            self.get_parameter("linear_kd").value,
            self.get_parameter("max_linear_vel").value,
        )

        self.latest_scan = None
        self.detected = False
        self.center_x_normalized = 0.0

        self.create_subscription(Float32MultiArray, "person_detection", self.detection_callback, 10)
        self.create_subscription(LaserScan, "scan", self.scan_callback, 10)
        self.cmd_pub = self.create_publisher(Twist, "cmd_vel", 10)

        self.prev_time = self.get_clock().now()
        self.timer = self.create_timer(1.0 / 15.0, self.control_loop)  # 15Hz 제어 루프

        self.get_logger().info(f"control_node 시작 (target_distance={self.target_distance}m)")

    def detection_callback(self, msg: Float32MultiArray):
        detected, center_x_normalized, _bbox_height = msg.data
        self.detected = bool(detected)
        self.center_x_normalized = center_x_normalized

    def scan_callback(self, msg: LaserScan):
        self.latest_scan = msg

    def get_distance_at_angle(self, angle_rad):
        """LiDAR scan에서 특정 각도 근방의 유효 거리값 평균"""
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

    def control_loop(self):
        now = self.get_clock().now()
        dt = (now - self.prev_time).nanoseconds / 1e9
        self.prev_time = now
        if dt <= 0:
            return

        cmd = Twist()

        if not self.detected:
            self.cmd_pub.publish(cmd)  # 전부 0 -> 정지
            return

        # center_x_normalized(-1~1) -> 실제 각도(rad)로 변환
        angle_rad = math.radians(self.center_x_normalized * (self.camera_fov_deg / 2.0))

        distance = self.get_distance_at_angle(angle_rad)

        angular_error = -self.center_x_normalized  # 사람이 오른쪽(+)에 있으면 우회전(음수 각속도 방향은 로봇 규약에 맞게 조정)
        angular_vel = self.angular_pid.compute(angular_error, dt)

        if distance is not None:
            linear_error = distance - self.target_distance
            linear_vel = self.linear_pid.compute(linear_error, dt)
        else:
            # LiDAR 거리 못 구하면 안전하게 정지 (카메라만으로 전진은 위험)
            linear_vel = 0.0
            self.get_logger().warn("LiDAR 거리 획득 실패, 선속도 0으로 설정", throttle_duration_sec=2.0)

        cmd.linear.x = linear_vel
        cmd.angular.z = angular_vel
        self.cmd_pub.publish(cmd)


def main(args=None):
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
