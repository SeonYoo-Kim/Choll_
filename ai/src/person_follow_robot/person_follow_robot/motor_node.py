"""
motor_node
- /cmd_vel (geometry_msgs/Twist) 구독
- 실제 모터 드라이버(시리얼/PWM 등)로 변환해서 전송

지금은 로그 출력만 함. 실제 Orin Car의 모터 컨트롤러 인터페이스(시리얼 포트, 프로토콜 등)를
알려주면 이 부분을 채워드릴 수 있음. 예: Arduino가 모터 담당이면 시리얼로 선속도/각속도를
그대로 전달하고 Arduino 쪽에서 좌우 바퀴 PWM으로 변환하는 구조가 흔함.
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

# import serial  # 실제 시리얼 통신 시 주석 해제


class MotorNode(Node):
    def __init__(self):
        super().__init__("motor_node")

        self.declare_parameter("serial_port", "/dev/ttyUSB0")
        self.declare_parameter("baud_rate", 115200)

        # self.serial_conn = serial.Serial(
        #     self.get_parameter("serial_port").value,
        #     self.get_parameter("baud_rate").value,
        #     timeout=0.1,
        # )

        self.create_subscription(Twist, "cmd_vel", self.cmd_vel_callback, 10)
        self.get_logger().info("motor_node 시작")

    def cmd_vel_callback(self, msg: Twist):
        linear_vel = msg.linear.x
        angular_vel = msg.angular.z

        # 실제 모터 제어로 교체할 부분
        self.get_logger().info(f"linear={linear_vel:.2f} m/s, angular={angular_vel:.2f} rad/s")

        # 예: 시리얼로 "L,A\n" 형태 전송하는 경우
        # command = f"{linear_vel:.3f},{angular_vel:.3f}\n"
        # self.serial_conn.write(command.encode())

        # 예: 차동구동(differential drive) 좌우 바퀴 속도로 변환하는 경우
        # wheel_base = 0.3  # 바퀴 간 거리(m), 실제 로봇에 맞게 설정
        # left_wheel = linear_vel - (angular_vel * wheel_base / 2)
        # right_wheel = linear_vel + (angular_vel * wheel_base / 2)
        # command = f"{left_wheel:.3f},{right_wheel:.3f}\n"
        # self.serial_conn.write(command.encode())


def main(args=None):
    rclpy.init(args=args)
    node = MotorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
