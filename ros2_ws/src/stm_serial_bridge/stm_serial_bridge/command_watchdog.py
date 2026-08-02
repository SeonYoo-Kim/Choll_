"""cmd_vel timeout 판단 — 매 송신 tick에 어떤 바퀴 목표를 보낼지 고르는 순수 모듈.

`rclpy`·ROS 메시지·pyserial·노드 클래스에 의존하지 않는다. 시간도 인자로 받으므로
`time.monotonic()`을 호출하지 않는다 — 덕분에 특정 시각을 만들어 넣어 경계 조건을
결정적으로 테스트할 수 있다.

안전 관점의 핵심은 "명령이 끊기면 멈춘다"이다. 상위(`/cmd_vel` 발행자)가 죽거나
네트워크가 끊겨도 브리지가 마지막 속도를 계속 반복해서는 안 된다.
"""

import math

# select_wheel_command()가 반환하는 상태값. 이 세 값만 사용한다.
STATE_WAITING = "waiting"
STATE_ACTIVE = "active"
STATE_TIMED_OUT = "timed_out"


def select_wheel_command(
    *,
    now_sec: float,
    last_cmd_vel_time_sec: float | None,
    cmd_vel_timeout_sec: float,
    latest_left_rad_s: float,
    latest_right_rad_s: float,
) -> tuple[float, float, str]:
    """Pick the wheel velocities to send on this tick, applying the cmd_vel timeout.

    판단 규칙:

    - `last_cmd_vel_time_sec is None` (아직 `/cmd_vel`을 한 번도 못 받음)
      -> `(0.0, 0.0, "waiting")`
    - 경과 시간 `< cmd_vel_timeout_sec`
      -> `(latest_left_rad_s, latest_right_rad_s, "active")`
    - 경과 시간 `>= cmd_vel_timeout_sec` (**경계값 포함**)
      -> `(0.0, 0.0, "timed_out")`

    경계값을 `timed_out`으로 판정하는 것은 의도적이다 — 애매한 순간에는 정지를
    택하는 편이 안전하다.

    `timed_out`에서는 최신 목표값이 0이 아니어도 반드시 0,0을 반환한다.

    큰 유한값은 clamp하지 않는다 — 최대 각속도 제한은 별개의 관심사다.

    Args:
        now_sec: 현재 시각(초). 단조 증가 시계 기준(`time.monotonic()`).
        last_cmd_vel_time_sec: 마지막 유효 `/cmd_vel` 수신 시각(초). 한 번도 받지
            않았으면 None.
        cmd_vel_timeout_sec: 이 시간 이상 새 명령이 없으면 정지로 전환한다. 양수.
        latest_left_rad_s: 마지막으로 저장한 왼쪽 바퀴 목표 각속도 (rad/s).
        latest_right_rad_s: 마지막으로 저장한 오른쪽 바퀴 목표 각속도 (rad/s).

    Returns:
        `(left_rad_s, right_rad_s, state)`. state는 `STATE_WAITING`/`STATE_ACTIVE`/
        `STATE_TIMED_OUT` 중 하나.

    Raises:
        ValueError: `cmd_vel_timeout_sec`가 0 이하이거나 유한하지 않을 때,
            `now_sec`가 유한하지 않을 때, `last_cmd_vel_time_sec`가 None이 아닌데
            유한하지 않을 때, 최신 좌우 각속도가 유한하지 않을 때.
    """
    if not math.isfinite(cmd_vel_timeout_sec):
        raise ValueError(
            f"cmd_vel_timeout_sec must be finite, got {cmd_vel_timeout_sec}"
        )
    if cmd_vel_timeout_sec <= 0.0:
        raise ValueError(
            f"cmd_vel_timeout_sec must be greater than 0.0, "
            f"got {cmd_vel_timeout_sec}"
        )
    if not math.isfinite(now_sec):
        raise ValueError(f"now_sec must be finite, got {now_sec}")
    if last_cmd_vel_time_sec is not None and not math.isfinite(last_cmd_vel_time_sec):
        raise ValueError(
            f"last_cmd_vel_time_sec must be finite or None, "
            f"got {last_cmd_vel_time_sec}"
        )
    if not math.isfinite(latest_left_rad_s):
        raise ValueError(f"latest_left_rad_s must be finite, got {latest_left_rad_s}")
    if not math.isfinite(latest_right_rad_s):
        raise ValueError(
            f"latest_right_rad_s must be finite, got {latest_right_rad_s}"
        )

    if last_cmd_vel_time_sec is None:
        return (0.0, 0.0, STATE_WAITING)

    elapsed_sec = now_sec - last_cmd_vel_time_sec
    if elapsed_sec >= cmd_vel_timeout_sec:
        return (0.0, 0.0, STATE_TIMED_OUT)

    return (latest_left_rad_s, latest_right_rad_s, STATE_ACTIVE)
