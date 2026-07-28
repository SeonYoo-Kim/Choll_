"""motor_node — /cmd_vel을 차동구동 좌우 바퀴 RPM으로 변환해 STM32로 발행.

- /cmd_vel (geometry_msgs/Twist, control_node 발행) 구독
- 차동구동 역기구학: (선속도 v, 각속도 ω) → 좌/우 바퀴 목표 RPM
- /wheel_speed_cmd (std_msgs/Int32MultiArray, data=[left_rpm, right_rpm]) 발행
  → micro-ROS agent를 거쳐 STM32가 구독 (규격: docs/JETSON_TO_STM.md, 10~12Hz)

부호 규약 (ROS REP 103, 오른손 좌표계 — 프로젝트 공통):
- +linear.x = 전진, +angular.z = 반시계(좌회전).
- 좌회전 시 오른쪽 바퀴가 더 빠르다: v_l = v - ω·L/2, v_r = v + ω·L/2.
- RPM 부호: +는 전진 방향 회전, -는 후진 방향 회전 (제자리 회전 시 한쪽이 음수).
  실기에서 회전 방향이 반대로 나오면 이 노드가 아니라 STM32 배선/모터 극성부터 확인.

안전 규칙: cmd_vel이 cmd_timeout_sec 동안 끊기면 [0, 0]을 발행해 정지한다.
"""

import math
from collections.abc import Sequence

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Int32MultiArray


def cmd_vel_to_wheel_rpms(
    linear_mps: float,
    angular_radps: float,
    wheel_radius_m: float,
    wheel_separation_m: float,
    max_rpm: int,
) -> tuple[int, int]:
    """차동구동 역기구학으로 몸체 속도 (v, ω)를 (left_rpm, right_rpm)으로 변환.

    v_left = v - ω·L/2, v_right = v + ω·L/2 (REP 103: +ω = 좌회전 → 오른쪽이 빠름).
    바퀴 선속도는 rpm = v / (2πr) × 60 으로 환산한다.

    Args:
        linear_mps: 전진 속도 v (m/s). 음수는 후진.
        angular_radps: 회전 속도 ω (rad/s). +는 반시계(좌회전).
        wheel_radius_m: 바퀴 반지름 r (m). 양수여야 함.
        wheel_separation_m: 좌우 바퀴 중심 간 거리 L (m). 양수여야 함.
        max_rpm: RPM 절대값 상한. 초과 시 좌우 비율(=선회 반경)을 유지한 채 축소.

    Returns:
        (left_rpm, right_rpm) 정수 쌍.

    Raises:
        ValueError: 바퀴 기하 값이 0 이하이거나 max_rpm이 음수일 때.
    """
    if wheel_radius_m <= 0 or wheel_separation_m <= 0:
        raise ValueError("wheel_radius_m and wheel_separation_m must be positive")
    if max_rpm < 0:
        raise ValueError("max_rpm must be non-negative")

    half_separation = wheel_separation_m / 2.0
    v_left = linear_mps - angular_radps * half_separation
    v_right = linear_mps + angular_radps * half_separation

    mps_to_rpm = 60.0 / (2.0 * math.pi * wheel_radius_m)
    rpm_left = v_left * mps_to_rpm
    rpm_right = v_right * mps_to_rpm

    peak = max(abs(rpm_left), abs(rpm_right))
    if peak > max_rpm:
        scale = max_rpm / peak
        rpm_left *= scale
        rpm_right *= scale

    return round(rpm_left), round(rpm_right)


class MotorNode(Node):
    """Convert /cmd_vel into /wheel_speed_cmd wheel RPMs for the STM32."""

    def __init__(self) -> None:
        """Declare wheel geometry parameters and wire the topic pipeline."""
        super().__init__("motor_node")

        self.declare_parameter("wheel_radius_m", 0.065)  # 실측 65mm
        self.declare_parameter("wheel_separation_m", 0.30)  # TODO: 조립 후 실측
        self.declare_parameter("max_rpm", 200)  # TODO: 모터 스펙 확정 시 조정
        self.declare_parameter("publish_rate_hz", 10.0)  # 규격상 10~12Hz
        self.declare_parameter("cmd_timeout_sec", 0.5)  # cmd_vel 끊기면 정지

        self.wheel_radius_m = float(self.get_parameter("wheel_radius_m").value)
        self.wheel_separation_m = float(
            self.get_parameter("wheel_separation_m").value
        )
        self.max_rpm = int(self.get_parameter("max_rpm").value)
        self.cmd_timeout_sec = float(self.get_parameter("cmd_timeout_sec").value)
        publish_rate_hz = float(self.get_parameter("publish_rate_hz").value)

        self.latest_linear = 0.0
        self.latest_angular = 0.0
        self.last_cmd_time = self.get_clock().now()

        self.create_subscription(Twist, "/cmd_vel", self.cmd_vel_callback, 10)
        self.wheel_pub = self.create_publisher(Int32MultiArray, "/wheel_speed_cmd", 10)
        self.timer = self.create_timer(1.0 / publish_rate_hz, self.publish_wheel_cmd)

        self.get_logger().info(
            f"motor_node 시작 (r={self.wheel_radius_m}m, "
            f"L={self.wheel_separation_m}m, max_rpm={self.max_rpm}, "
            f"{publish_rate_hz}Hz)"
        )

    def cmd_vel_callback(self, msg: Twist) -> None:
        """Cache the newest body velocity command."""
        self.latest_linear = float(msg.linear.x)
        self.latest_angular = float(msg.angular.z)
        self.last_cmd_time = self.get_clock().now()

    def _cmd_is_stale(self) -> bool:
        """Return True if no cmd_vel arrived within the timeout window."""
        elapsed = (self.get_clock().now() - self.last_cmd_time).nanoseconds / 1e9
        return elapsed > self.cmd_timeout_sec

    def publish_wheel_cmd(self) -> None:
        """Publish [left_rpm, right_rpm] at the fixed rate (0 when stale)."""
        left_rpm, right_rpm = 0, 0
        if not self._cmd_is_stale():
            try:
                left_rpm, right_rpm = cmd_vel_to_wheel_rpms(
                    self.latest_linear,
                    self.latest_angular,
                    self.wheel_radius_m,
                    self.wheel_separation_m,
                    self.max_rpm,
                )
            except ValueError as error:
                self.get_logger().error(
                    f"바퀴 RPM 변환 실패, 정지 발행: {error}",
                    throttle_duration_sec=2.0,
                )

        msg = Int32MultiArray()
        msg.data = [left_rpm, right_rpm]
        self.wheel_pub.publish(msg)


def main(args: Sequence[str] | None = None) -> None:
    """Start the motor node."""
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
