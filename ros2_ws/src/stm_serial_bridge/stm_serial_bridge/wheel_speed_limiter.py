"""바퀴 각속도 안전 제한 — 좌우를 **같은 비율로** 축소하는 순수 모듈.

`rclpy`·ROS 메시지·pyserial·`command_watchdog`·노드 클래스에 의존하지 않는다.
전역 상태가 없고 부작용이 없으므로 하드웨어 없이 pytest로 검증할 수 있다.

좌우를 각각 독립적으로 clamp하지 않는 것이 핵심이다. 예를 들어 `(1.923, 4.231)`을
한계 2.0으로 각각 자르면 `(1.923, 2.0)`이 되어 **좌우 속도차(=회전 반경)가 바뀌고**
로봇이 의도한 것보다 크게 꺾인다. 같은 비율로 줄이면 `(0.909, 2.0)`이 되어 궤적의
곡률은 유지하고 속도만 낮춘다.

STM32에는 목표 각속도 상한 clamp가 아직 없다(`MOTION_CONTROLLER_MAX_WHEEL_RAD_S`가
정의만 되어 있고 미적용, 정본: embedded/motor/docs/serial_protocol.md). 따라서 상한
방어는 현재 이 브리지 쪽에만 존재한다.
"""

import math


def limit_wheel_rad_s(
    left_rad_s: float,
    right_rad_s: float,
    max_wheel_rad_s: float,
) -> tuple[float, float]:
    """Scale both wheel velocities down proportionally to respect a shared limit.

    계산::

        peak = max(abs(left_rad_s), abs(right_rad_s))
        peak <= max_wheel_rad_s  ->  (left_rad_s, right_rad_s)          # 그대로
        peak >  max_wheel_rad_s  ->  scale = max_wheel_rad_s / peak
                                     (left_rad_s * scale, right_rad_s * scale)

    경계값(`peak == max_wheel_rad_s`)에서는 축소하지 않는다 — 한계값 자체는 허용
    범위이며, 불필요한 부동소수 연산으로 값이 흔들리지 않게 한다.

    좌우 부호와 비율은 항상 보존된다(scale이 항상 양수). 둘 다 0이면 `peak`가 0이라
    첫 분기로 들어가 `(0.0, 0.0)`을 그대로 반환한다 — 0으로 나누는 경로는 없다.

    Args:
        left_rad_s: 제한 전 왼쪽 바퀴 목표 각속도 (rad/s).
        right_rad_s: 제한 전 오른쪽 바퀴 목표 각속도 (rad/s).
        max_wheel_rad_s: 허용하는 최대 절댓값 (rad/s). 0보다 큰 유한값이어야 한다.

    Returns:
        `(left_rad_s, right_rad_s)` — 제한을 적용한 좌우 각속도.

    Raises:
        ValueError: 좌우 각속도가 유한하지 않을 때, 또는 `max_wheel_rad_s`가 유한하지
            않거나 0 이하일 때.
    """
    if not math.isfinite(left_rad_s):
        raise ValueError(f"left_rad_s must be finite, got {left_rad_s}")
    if not math.isfinite(right_rad_s):
        raise ValueError(f"right_rad_s must be finite, got {right_rad_s}")
    if not math.isfinite(max_wheel_rad_s):
        raise ValueError(f"max_wheel_rad_s must be finite, got {max_wheel_rad_s}")
    if max_wheel_rad_s <= 0.0:
        raise ValueError(
            f"max_wheel_rad_s must be greater than 0.0, got {max_wheel_rad_s}"
        )

    peak = max(abs(left_rad_s), abs(right_rad_s))
    if peak <= max_wheel_rad_s:
        return (left_rad_s, right_rad_s)

    scale = max_wheel_rad_s / peak
    return (left_rad_s * scale, right_rad_s * scale)
