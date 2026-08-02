"""차동구동 기구학 변환 — 선속도·각속도를 좌우 바퀴 각속도로 변환한다.

이 모듈은 `rclpy`·ROS 메시지 타입·serial에 의존하지 않는 **순수 계산 모듈**이다.
하드웨어나 ROS 실행 환경 없이 pytest로 검증할 수 있도록 의도적으로 분리했다.
전역 상태를 두지 않으며, 입력에 대해 항상 같은 결과를 반환한다.

STM32는 `SET_WHEEL_VEL,<left_rad_s>,<right_rad_s>` 형식으로 좌우 바퀴 각속도(rad/s)를
받는다(프로토콜 정본: embedded/motor/docs/serial_protocol.md). 이 모듈은 그 값을
계산하는 단계까지만 담당하고, 명령 문자열 생성이나 전송은 하지 않는다.
"""


def cmd_vel_to_wheel_rad_s(
    linear_x: float,
    angular_z: float,
    wheel_radius_m: float,
    wheel_separation_m: float,
) -> tuple[float, float]:
    """Convert a differential-drive twist into left/right wheel angular velocities.

    계산식::

        left_linear_velocity  = linear_x - angular_z * wheel_separation_m / 2.0
        right_linear_velocity = linear_x + angular_z * wheel_separation_m / 2.0
        left_wheel_rad_s      = left_linear_velocity  / wheel_radius_m
        right_wheel_rad_s     = right_linear_velocity / wheel_radius_m

    ROS2 좌표계에서 `angular_z > 0`은 반시계 방향(좌회전)이다. 따라서 전진하면서
    양의 `angular_z`를 주면 **왼쪽 바퀴가 느리고 오른쪽 바퀴가 빠르다.**

    속도 제한(clamp)은 적용하지 않는다 — 이 함수는 순수 기구학 변환만 담당하며,
    바퀴 최대 속도 제한은 별개의 관심사로 상위 계층에서 처리한다.

    Args:
        linear_x: 로봇 전진 선속도 v (m/s). 양수가 전진.
        angular_z: 로봇 요(yaw) 각속도 ω (rad/s). 양수가 반시계 방향(좌회전).
        wheel_radius_m: 바퀴 반지름 r (m). 0보다 커야 한다.
        wheel_separation_m: 좌우 바퀴 중심 간 거리 L (m). 0보다 커야 한다.

    Returns:
        `(left_wheel_rad_s, right_wheel_rad_s)` 순서의 좌우 바퀴 각속도(rad/s).

    Raises:
        ValueError: `wheel_radius_m` 또는 `wheel_separation_m`가 0 이하일 때.
            어느 파라미터가 잘못됐는지 메시지에 값과 함께 담는다.
    """
    if wheel_radius_m <= 0.0:
        raise ValueError(
            f"wheel_radius_m must be greater than 0.0, got {wheel_radius_m}"
        )
    if wheel_separation_m <= 0.0:
        raise ValueError(
            f"wheel_separation_m must be greater than 0.0, got {wheel_separation_m}"
        )

    half_separation = wheel_separation_m / 2.0

    left_linear_velocity = linear_x - angular_z * half_separation
    right_linear_velocity = linear_x + angular_z * half_separation

    return (
        left_linear_velocity / wheel_radius_m,
        right_linear_velocity / wheel_radius_m,
    )
