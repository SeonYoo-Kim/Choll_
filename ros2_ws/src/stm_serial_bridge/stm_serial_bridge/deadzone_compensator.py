"""모터 데드존 보상 — 작은 바퀴 명령이 "명령은 나가는데 안 도는" 구간을 없앤다.

`rclpy`·ROS 메시지·pyserial에 의존하지 않는 **순수 계산 모듈**이다. 전역 상태와
부작용이 없어 하드웨어 없이 pytest로 검증할 수 있다.

## 왜 필요한가 (2026-08-07/08 실측)

STM32 펌웨어는 개루프다 — `motor_pi_kp = 0.0`, `motor_pi_ki = 0.0` 이고 듀티는
`PWM = MOTOR_OPEN_LOOP_PWM_PER_RAD_S(10.0) x rad/s` 로만 정해진다. 실측 데드존은
공중에서 PWM 20, 바닥에서 PWM 10~12 부근이다. 즉 **바퀴 1.0~1.2 rad/s 미만 명령은
전송돼도 바퀴가 돌지 않는다.**

그 결과 Nav2 DWB가 내는 작은 조향 보정이 전부 소실되고, 큰 오차가 쌓여 명령이
데드존을 넘을 때만 움직이는 bang-bang 이 된다 — 2026-08-07 실기에서 관측한 회전
리밋 사이클의 직접 원인이다.

## 보상 방식 (affine offset)

죽은 구간을 잘라내고 살아 있는 구간 `[deadzone, max]` 로 **선형 재사상**한다::

    |w| <= epsilon        ->  0.0                      (정지 명령은 정지 그대로)
    epsilon < |w| <= max  ->  sign(w) x (deadzone + (max - deadzone) x |w| / max)

`|w| = max` 는 `max` 로 그대로 남고, `|w| -> 0+` 는 `deadzone` 으로 수렴한다.
따라서 **0이 아닌 어떤 명령도 실제 회전을 만든다**는 것이 이 함수의 계약이다.

임계값 방식(`|w| < deadzone` 이면 `deadzone` 으로 올림)을 쓰지 않은 이유: 그러면
데드존 바로 위 구간이 두 배로 눌려 속도-명령 관계가 꺾이고, 작은 명령이 실제
데드존 속도로 튀어 오히려 거칠어진다.

## 알고 있어야 할 부작용

좌우에 각각 offset이 붙으므로 **좌우 비율(=회전 반경)이 보존되지 않는다.**
`limit_wheel_rad_s()` 가 비율을 지키는 것과 반대다. 이건 데드존 보상의 본질이며,
작은 명령을 살리는 대가로 곡률이 약간 변하는 것을 받아들이는 것이다. 그래서 반드시
**속도 제한을 적용한 뒤 마지막 단계로** 호출해야 한다 — 먼저 걸면 제한이 offset을
도로 축소해 보상이 무의미해진다.

`deadzone_wheel_rad_s = 0.0` 이면 항등 함수가 되어 보상 이전 거동과 완전히 같다
(기본값이 0인 이유 — 켜는 것은 명시적 선택이어야 한다).
"""

import math


def apply_deadzone_compensation(
    left_rad_s: float,
    right_rad_s: float,
    deadzone_wheel_rad_s: float,
    max_wheel_rad_s: float,
    epsilon_rad_s: float = 1e-3,
) -> tuple[float, float]:
    """Remap wheel targets so any non-zero command clears the motor deadzone.

    각 바퀴에 독립적으로 적용한다(좌우 비율은 보존되지 않는다 — 모듈 docstring 참고).

    Args:
        left_rad_s: 보상 전 왼쪽 바퀴 목표 각속도 (rad/s). 유한값이어야 한다.
        right_rad_s: 보상 전 오른쪽 바퀴 목표 각속도 (rad/s). 유한값이어야 한다.
        deadzone_wheel_rad_s: 이 속도 미만에서는 바퀴가 돌지 않는다는 실측값 (rad/s).
            0이면 보상하지 않고 입력을 그대로 돌려준다. 음수는 허용하지 않는다.
        max_wheel_rad_s: 재사상의 상단 기준이자 출력 상한 (rad/s). 0보다 큰 유한값.
        epsilon_rad_s: 이 절댓값 이하는 "정지 명령"으로 보고 0으로 만든다. 부동소수
            잔값에 데드존 offset이 붙어 카트가 스멀스멀 움직이는 것을 막는다.

    Returns:
        `(left_rad_s, right_rad_s)` — 보상을 적용한 좌우 각속도. 절댓값은 항상
        `max_wheel_rad_s` 이하이며, 0이 아니면 항상 `deadzone_wheel_rad_s` 이상이다.

    Raises:
        ValueError: 입력이 유한하지 않을 때, `max_wheel_rad_s`가 0 이하일 때,
            `deadzone_wheel_rad_s`가 음수이거나 `max_wheel_rad_s` 이상일 때,
            `epsilon_rad_s`가 음수일 때.
    """
    for name, value in (
        ("left_rad_s", left_rad_s),
        ("right_rad_s", right_rad_s),
        ("deadzone_wheel_rad_s", deadzone_wheel_rad_s),
        ("max_wheel_rad_s", max_wheel_rad_s),
        ("epsilon_rad_s", epsilon_rad_s),
    ):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite, got {value}")

    if max_wheel_rad_s <= 0.0:
        raise ValueError(
            f"max_wheel_rad_s must be greater than 0.0, got {max_wheel_rad_s}"
        )
    if deadzone_wheel_rad_s < 0.0:
        raise ValueError(
            "deadzone_wheel_rad_s must not be negative, "
            f"got {deadzone_wheel_rad_s}"
        )
    if epsilon_rad_s < 0.0:
        raise ValueError(f"epsilon_rad_s must not be negative, got {epsilon_rad_s}")
    if deadzone_wheel_rad_s >= max_wheel_rad_s:
        # 데드존이 상한 이상이면 살아 있는 구간이 없다. 조용히 전 구간을 데드존
        # 속도로 밀어내면 저속 주행이 통째로 사라지므로 설정 오류로 거부한다.
        raise ValueError(
            "deadzone_wheel_rad_s must be less than max_wheel_rad_s, got "
            f"deadzone={deadzone_wheel_rad_s} max={max_wheel_rad_s}"
        )

    if deadzone_wheel_rad_s == 0.0:
        return (left_rad_s, right_rad_s)

    span = max_wheel_rad_s - deadzone_wheel_rad_s
    return (
        _compensate_one(left_rad_s, deadzone_wheel_rad_s, span, max_wheel_rad_s,
                        epsilon_rad_s),
        _compensate_one(right_rad_s, deadzone_wheel_rad_s, span, max_wheel_rad_s,
                        epsilon_rad_s),
    )


def _compensate_one(
    wheel_rad_s: float,
    deadzone: float,
    span: float,
    max_wheel_rad_s: float,
    epsilon: float,
) -> float:
    """한쪽 바퀴에 affine 재사상을 적용한다.

    Args:
        wheel_rad_s: 보상 전 각속도 (rad/s).
        deadzone: 데드존 속도 (rad/s). 0보다 크다.
        span: `max_wheel_rad_s - deadzone`. 0보다 크다.
        max_wheel_rad_s: 상단 기준이자 출력 상한 (rad/s).
        epsilon: 정지로 간주할 절댓값 (rad/s).

    Returns:
        보상 후 각속도 (rad/s).
    """
    magnitude = abs(wheel_rad_s)
    if magnitude <= epsilon:
        return 0.0

    # 상한을 넘겨 들어온 값(정상 경로에서는 limit_wheel_rad_s가 이미 막는다)이
    # 재사상으로 더 커지지 않도록 비율을 1.0에서 잘라낸다.
    ratio = min(magnitude / max_wheel_rad_s, 1.0)
    compensated = deadzone + span * ratio
    return math.copysign(compensated, wheel_rad_s)
