"""STM32 UART Protocol v1 명령 문자열 생성 — 순수 문자열 조립 모듈.

이 모듈은 `rclpy`·ROS 메시지 타입·pyserial에 의존하지 않고, 파일이나 장치 I/O도
수행하지 않는다. 입력을 받아 문자열만 반환하는 순수 함수로만 구성되며 전역 상태를
두지 않는다. 하드웨어나 ROS 실행 환경 없이 pytest로 검증할 수 있다.

프로토콜 정본: embedded/motor/docs/serial_protocol.md
포맷 기준: embedded/motor/tools/motor_serial_test/motor_test.py 의
`build_wheel_vel_command()`(실기 검증을 통과한 형식, 소수점 3자리 + CRLF)와 동일하게
맞춰 실기 로그를 서로 비교할 수 있게 한다.

현재 구현된 명령은 `SET_WHEEL_VEL` 하나뿐이다. `STOP`/`ESTOP`/`RESET_STALL`/
`SET_PI_GAINS`/`PING`은 이후 단계에서 필요해질 때 추가한다.
"""

import math

# STM32 CommandParser는 줄 단위로 명령을 조립하며 CRLF 종단을 기대한다.
COMMAND_TERMINATOR = "\r\n"

# 좌우 각속도 소수점 자릿수. 기존 Python 실기 도구와 동일하게 3자리로 고정한다.
WHEEL_VEL_DECIMALS = 3


def build_set_wheel_vel_command(
    left_rad_s: float,
    right_rad_s: float,
) -> str:
    """Build the `SET_WHEEL_VEL` UART command line for the STM32.

    반환 형식::

        SET_WHEEL_VEL,<left_rad_s>,<right_rad_s>\\r\\n

    좌우 각속도는 항상 소수점 이하 3자리로 고정 출력한다(`2.0` -> `2.000`).
    종단 문자는 반드시 CRLF다.

    큰 유한값은 거부하지 않는다 — 바퀴 최대 각속도 제한(clamp)은 별개의 안전
    관심사이며 이 함수의 책임이 아니다.

    Args:
        left_rad_s: 왼쪽 바퀴 목표 각속도 (rad/s). 유한값이어야 한다.
        right_rad_s: 오른쪽 바퀴 목표 각속도 (rad/s). 유한값이어야 한다.

    Returns:
        CRLF로 끝나는 `SET_WHEEL_VEL` 명령 문자열.

    Raises:
        ValueError: `left_rad_s` 또는 `right_rad_s`가 유한하지 않을 때
            (NaN, +Infinity, -Infinity). 어느 파라미터가 잘못됐는지와 실제 값을
            메시지에 담는다. NaN/Infinity를 그대로 문자열로 만들면 STM 쪽
            `strtof` 파싱이 예측 불가능한 목표 속도로 이어질 수 있어 여기서 막는다.
    """
    if not math.isfinite(left_rad_s):
        raise ValueError(f"left_rad_s must be finite, got {left_rad_s}")
    if not math.isfinite(right_rad_s):
        raise ValueError(f"right_rad_s must be finite, got {right_rad_s}")

    return (
        f"SET_WHEEL_VEL,"
        f"{left_rad_s:.{WHEEL_VEL_DECIMALS}f},"
        f"{right_rad_s:.{WHEEL_VEL_DECIMALS}f}"
        f"{COMMAND_TERMINATOR}"
    )
