"""차동구동 기구학 변환 — 선속도·각속도를 좌우 바퀴 각속도로 변환한다.

이 모듈은 `rclpy`·ROS 메시지 타입·serial에 의존하지 않는 **순수 계산 모듈**이다.
하드웨어나 ROS 실행 환경 없이 pytest로 검증할 수 있도록 의도적으로 분리했다.
전역 상태를 두지 않으며, 입력에 대해 항상 같은 결과를 반환한다.

STM32는 `SET_WHEEL_VEL,<left_rad_s>,<right_rad_s>` 형식으로 좌우 바퀴 각속도(rad/s)를
받는다(프로토콜 정본: embedded/motor/docs/serial_protocol.md). 이 모듈은 그 값을
계산하는 단계까지만 담당하고, 명령 문자열 생성이나 전송은 하지 않는다.

`required_max_wheel_rad_s()`는 반대 방향 질문("상위 주행 스택이 요구하는 속도 봉투를
비례 축소 없이 수용하려면 `max_wheel_rad_s`가 얼마여야 하는가")에 답한다.

상한이 봉투보다 낮으면 `wheel_speed_limiter.limit_wheel_rad_s()`가 좌우 비율을 유지한
채 전체 속도를 비례 축소한다. 이때 노드는 제한이 걸릴 때마다 경고를 남기므로(브리지
노드의 `was_limited` 분기) **로그에서 관측 가능한 상태**다 — 조용히 일어나는 일은 아니다.
문제는 궤적·조향은 그대로인 채 속도만 느려진다는 점이다. 그래서 증상이 "상한이 낮다"가
아니라 "주행 스택이 동작하지 않는다"처럼 보이기 쉽다. 이 관계를 주석이 아니라 실행·
테스트 가능한 코드로 두는 이유가 그것이다.
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


def required_max_wheel_rad_s(
    max_linear_mps: float,
    max_angular_rps: float,
    wheel_radius_m: float,
    wheel_separation_m: float,
) -> float:
    """Return the peak wheel angular velocity that a v/ω envelope can demand.

    상위 주행 스택이 낼 수 있는 최대 선속도·각속도를 주면, **그 봉투 안의 어떤 명령도
    비례 축소 없이 통과시키려면 `max_wheel_rad_s`가 얼마여야 하는지**를 돌려준다.
    Nav2를 쓰는 경우 입력값은 `controller_server`의 `max_vel_x`·`max_vel_theta`다.

    `cmd_vel_to_wheel_rad_s()`를 **봉투의 두 꼭짓점** `(|v|, +|ω|)`와 `(|v|, -|ω|)`에서
    호출해 좌우 네 값의 절댓값 중 최대를 취한다. 변환이 `v`·`ω`에 대해 선형이므로
    최댓값은 항상 꼭짓점에서 나온다 — 덕분에 기구학식을 다시 쓰지 않는다.

    부호는 봉투의 크기와 무관하므로 두 최대값을 **절댓값으로** 취급한다. 즉
    `max_angular_rps`에 음수를 줘도 결과는 같다.

    Args:
        max_linear_mps: 상위 스택의 최대 선속도 |v| (m/s). 부호는 무시된다.
        max_angular_rps: 상위 스택의 최대 각속도 |ω| (rad/s). 부호는 무시된다.
        wheel_radius_m: 바퀴 반지름 r (m). 0보다 커야 한다.
        wheel_separation_m: 좌우 바퀴 중심 간 거리 L (m). 0보다 커야 한다.

    Returns:
        필요한 최대 바퀴 각속도 (rad/s). 유한 입력에서는 항상 0 이상이며, 봉투가
        `(0, 0)`이면 `0.0`이다.

    Raises:
        ValueError: `wheel_radius_m` 또는 `wheel_separation_m`가 0 이하일 때.
            `cmd_vel_to_wheel_rad_s()`가 던지는 예외를 그대로 전달한다 — 검증을
            중복해서 구현하지 않는다.

    Note:
        `cmd_vel_to_wheel_rad_s()`와 **같은 규칙**으로 속도 인자의 유한성은 검사하지
        않는다. NaN/Inf를 주면 그대로 전파된다. 유한성 검증은 이 모듈의 관심사가
        아니라 상위 계층(브리지 노드의 파라미터 검증)의 몫이다.
    """
    linear = abs(max_linear_mps)
    angular = abs(max_angular_rps)

    # 0.0을 초기값으로 두고 max()를 누적하면 NaN이 삼켜진다(`nan > 0.0`이 False).
    # 후보를 모아 한 번에 max()를 취해 NaN이 그대로 전파되게 한다.
    candidates: list[float] = []
    for angular_z in (angular, -angular):
        left_rad_s, right_rad_s = cmd_vel_to_wheel_rad_s(
            linear, angular_z, wheel_radius_m, wheel_separation_m
        )
        candidates.append(abs(left_rad_s))
        candidates.append(abs(right_rad_s))

    return max(candidates)
