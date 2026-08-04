"""SSH 터미널 WASD 수동 주행 노드 — 지도 작성용.

```
SSH 키보드 -> cart_teleop -> /cmd_vel -> stm_serial_bridge -> STM32
```

⚠️ 이 노드는 **Serial 포트를 열지 않는다.** `stm_serial_bridge`의 내부 모듈
(`serial_link.py` 등)을 import하지도 않는다. Serial 포트 소유자는 항상
`stm_serial_bridge` 하나뿐이다. 이 노드가 하는 일은 `/cmd_vel` 발행까지다.

실행::

    export ROS_LOCALHOST_ONLY=1
    ros2 run cart_teleop keyboard_teleop

⚠️ `ros2 launch`로는 실행하지 않는다 — launch는 stdin을 tty로 넘겨주지 않아
   키 입력을 받을 수 없다. 그래서 이 패키지에는 launch 파일이 없다.

⚠️ **지도 작성 중에는 Nav2와 AI launch를 실행하지 않는다.** 이 노드는 시작 시와
   실행 중 주기적으로 외부 `/cmd_vel` Publisher를 검사해, 하나라도 있으면
   `DISARMED`로 전환하고 non-zero 명령을 발행하지 않는다.

⚠️ `Space`는 **정지 명령(zero Twist)** 이다. ESTOP이 아니다 — 현재 Bridge에는 STM
   `ESTOP` 송신 인터페이스가 없다. **실제 비상정지는 물리 전원 차단이 필요하다.**

⚠️ 터미널은 **키 릴리즈를 감지할 수 없다.** command lease 방식(입력마다 유효시간
   갱신, 만료 시 zero)으로 근사한다 — 자세한 근거는 `teleop_keys` 모듈 docstring 참고.
"""

import select
import sys
import termios
import time
import tty
from collections.abc import Sequence

import rclpy
from geometry_msgs.msg import Twist
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from cart_teleop.teleop_keys import (
    DEFAULT_INPUT_TIMEOUT_SEC,
    DEFAULT_MAX_ANGULAR_RPS,
    DEFAULT_MAX_LINEAR_MPS,
    DEFAULT_SPEED_STEP_COUNT,
    TeleopCommand,
    TeleopState,
    TeleopStatus,
)

CMD_VEL_TOPIC = "/cmd_vel"
CMD_VEL_QOS_DEPTH = 10

DEFAULT_PUBLISH_RATE_HZ = 20.0
DEFAULT_CONFLICT_CHECK_HZ = 2.0

# 종료 시 zero Twist 를 이 횟수·간격으로 반복 발행한다. 한 번만 보내면 DDS 유실
# 시 마지막 non-zero 명령이 Bridge 에 남을 수 있다(Bridge watchdog 이 0.5초 뒤
# 정지시키지만, 명시적으로 0 을 보내는 편이 확실하다).
STOP_REPEAT_COUNT = 5
STOP_REPEAT_INTERVAL_SEC = 0.02

SPIN_TIMEOUT_SEC = 0.02
STDIN_POLL_TIMEOUT_SEC = 0.0

EXIT_SUCCESS = 0
EXIT_FAILURE = 1

_NOT_A_TTY_MESSAGE = (
    "cart_teleop: stdin 이 TTY 가 아니다 — 키 입력을 받을 수 없어 종료한다.\n"
    "  `ros2 launch` 나 파이프·리다이렉션으로 실행하면 이 상태가 된다.\n"
    "  대화형 터미널에서 다음으로 실행할 것:\n"
    "      ros2 run cart_teleop keyboard_teleop"
)

# ANSI: 커서를 홈으로 옮기고 화면을 지운다. 매 tick 전체를 다시 그린다.
_ANSI_HOME_CLEAR = "\x1b[H\x1b[2J"
_ANSI_SHOW_CURSOR = "\x1b[?25h"
_ANSI_HIDE_CURSOR = "\x1b[?25l"


class KeyboardTeleopNode(Node):
    """키 입력을 읽어 `/cmd_vel`로 발행하는 노드.

    터미널 설정 변경·복원은 이 클래스가 아니라 `main()`이 담당한다 — 노드 생성이
    실패해도 터미널이 복원되도록 하기 위해서다.
    """

    def __init__(self) -> None:
        """파라미터를 선언하고 상태 기계를 만든다. 아직 발행하지 않는다."""
        super().__init__("cart_keyboard_teleop")

        self.declare_parameter("max_linear_mps", DEFAULT_MAX_LINEAR_MPS)
        self.declare_parameter("max_angular_rps", DEFAULT_MAX_ANGULAR_RPS)
        self.declare_parameter("input_timeout_sec", DEFAULT_INPUT_TIMEOUT_SEC)
        self.declare_parameter("speed_step_count", DEFAULT_SPEED_STEP_COUNT)
        self.declare_parameter("publish_rate_hz", DEFAULT_PUBLISH_RATE_HZ)
        self.declare_parameter("conflict_check_hz", DEFAULT_CONFLICT_CHECK_HZ)

        self._publish_rate_hz = float(self.get_parameter("publish_rate_hz").value)
        self._conflict_check_hz = float(self.get_parameter("conflict_check_hz").value)
        if self._publish_rate_hz <= 0.0:
            msg = f"publish_rate_hz must be > 0.0, got {self._publish_rate_hz}"
            raise ValueError(msg)
        if self._conflict_check_hz <= 0.0:
            msg = f"conflict_check_hz must be > 0.0, got {self._conflict_check_hz}"
            raise ValueError(msg)

        # 파라미터 검증은 TeleopState 가 담당한다(ValueError 를 그대로 올린다).
        self._state = TeleopState(
            max_linear_mps=float(self.get_parameter("max_linear_mps").value),
            max_angular_rps=float(self.get_parameter("max_angular_rps").value),
            input_timeout_sec=float(self.get_parameter("input_timeout_sec").value),
            speed_step_count=int(self.get_parameter("speed_step_count").value),
        )

        self._publisher = self.create_publisher(
            Twist, CMD_VEL_TOPIC, CMD_VEL_QOS_DEPTH
        )
        self._publish_timer = None
        self._conflict_timer = None
        self._last_render = ""

    @property
    def quit_requested(self) -> bool:
        """상태 기계가 종료를 요청했는지."""
        return self._state.quit_requested

    def start(self) -> None:
        """타이머를 만들고 첫 충돌 검사를 수행한다."""
        self._check_publisher_conflict()
        self._publish_timer = self.create_timer(
            1.0 / self._publish_rate_hz, self._publish_timer_callback
        )
        self._conflict_timer = self.create_timer(
            1.0 / self._conflict_check_hz, self._check_publisher_conflict
        )

    def request_quit(self) -> None:
        """외부 신호로 종료를 요청한다."""
        self._state.request_quit()

    # ── 타이머 ─────────────────────────────────────────────────────────────

    def _publish_timer_callback(self) -> None:
        """키를 읽고, 명령을 판정해 발행하고, 화면을 갱신한다."""
        now_sec = time.monotonic()

        for key in _read_available_keys():
            self._state.handle_key(key, now_sec)

        command = self._state.evaluate(now_sec)
        self._publish(command.linear_x, command.angular_z)
        self._render(command)

    def _check_publisher_conflict(self) -> None:
        """`/cmd_vel` 의 외부 Publisher 수를 세어 상태에 반영한다.

        `count_publishers()` 는 자신의 Publisher 도 포함하므로 1을 뺀다.
        """
        total = self.count_publishers(CMD_VEL_TOPIC)
        self._state.set_external_publisher_count(total - 1)

    # ── 발행 ───────────────────────────────────────────────────────────────

    def _publish(self, linear_x: float, angular_z: float) -> None:
        """Twist 를 발행한다. 차동구동이라 linear.x·angular.z 만 채운다."""
        message = Twist()
        message.linear.x = linear_x
        message.angular.z = angular_z
        self._publisher.publish(message)

    def publish_zero_burst(self) -> None:
        """정지 명령(zero Twist)을 짧은 간격으로 반복 발행한다.

        종료 경로에서 호출한다. context 가 이미 내려갔으면 조용히 건너뛴다.
        """
        for _ in range(STOP_REPEAT_COUNT):
            if not rclpy.ok():
                return
            try:
                self._publish(0.0, 0.0)
            except Exception:  # noqa: BLE001 — 종료 경로는 어떤 이유로도 막지 않는다
                return
            time.sleep(STOP_REPEAT_INTERVAL_SEC)

    # ── 화면 ───────────────────────────────────────────────────────────────

    def _render(self, command: TeleopCommand) -> None:
        """콘솔 UI 를 갱신한다. 내용이 바뀌지 않으면 다시 그리지 않는다."""
        text = _build_screen(command, self._state.input_timeout_sec)
        if text == self._last_render:
            return
        self._last_render = text
        sys.stdout.write(_ANSI_HOME_CLEAR + text)
        sys.stdout.flush()


def _read_available_keys() -> list[str]:
    """지금 stdin 에 도착해 있는 키를 모두 읽는다 (blocking 하지 않는다).

    자동반복으로 여러 문자가 한 번에 쌓일 수 있으므로 버퍼를 비운다. 순서대로
    처리하면 마지막 키가 최종 상태가 된다.

    Returns:
        읽은 문자 목록. 없으면 빈 목록.
    """
    keys: list[str] = []
    while True:
        ready, _, _ = select.select([sys.stdin], [], [], STDIN_POLL_TIMEOUT_SEC)
        if not ready:
            return keys
        char = sys.stdin.read(1)
        if not char:
            return keys
        keys.append(char)


def _format_lease(command: TeleopCommand, input_timeout_sec: float) -> str:
    """lease 남은 시간을 표시 문자열로 만든다."""
    if command.status is TeleopStatus.ARMED and command.lease_remaining_sec is not None:
        return f"{command.lease_remaining_sec:.2f}s / {input_timeout_sec:.2f}s"
    if command.status is TeleopStatus.TIMEOUT:
        return f"만료 (>{input_timeout_sec:.2f}s 무입력)"
    return "-"


def _build_screen(command: TeleopCommand, input_timeout_sec: float) -> str:
    """콘솔에 출력할 전체 화면 문자열을 만든다.

    Args:
        command: 이 tick 의 `TeleopCommand`.
        input_timeout_sec: command lease 유효시간.

    Returns:
        여러 줄 문자열.
    """
    if command.external_publisher_count > 0:
        conflict = (
            f"⚠️ 충돌 — 외부 Publisher {command.external_publisher_count}개 "
            "(Nav2/AI 를 종료할 것)"
        )
    else:
        conflict = "없음 (teleop 단독)"

    if command.status is TeleopStatus.DISARMED:
        note = "DISARMED — non-zero 명령을 발행하지 않는다. 외부 Publisher 를 종료할 것."
    elif command.status is TeleopStatus.TIMEOUT:
        note = "무입력 timeout 으로 정지했다. 다시 움직이려면 W/S/A/D 를 누를 것."
    elif command.status is TeleopStatus.QUIT:
        note = "종료 중 — 정지 명령을 발행한다."
    elif command.status is TeleopStatus.ARMED:
        note = "주행 중. 키를 놓으면 timeout 후 정지한다."
    else:
        note = "정지 상태. W/S/A/D 로 주행."

    lines = [
        "=" * 64,
        " cart_teleop — 수동 주행 (지도 작성용)",
        "=" * 64,
        f"  상태            : {command.status.value}",
        f"  마지막 입력 키  : {command.last_key_label or '-'}",
        f"  linear.x        : {command.linear_x:+.3f} m/s",
        f"  angular.z       : {command.angular_z:+.3f} rad/s",
        f"  속도 단계       : {command.speed_step} / {command.speed_step_count}",
        f"  lease 남은 시간 : {_format_lease(command, input_timeout_sec)}",
        f"  /cmd_vel 충돌   : {conflict}",
        "-" * 64,
        "  W 전진   S 후진   A 제자리 좌회전   D 제자리 우회전",
        "  Space 정지 (ESTOP 아님)   +/= 속도↑   - 속도↓   q/Esc 종료",
        "-" * 64,
        f"  {note}",
        "",
        "  ⚠️ 실제 비상정지는 물리 전원 차단이 필요하다.",
        "",
    ]
    return "\r\n".join(lines) + "\r\n"


def main(argv: Sequence[str] | None = None) -> int:
    """터미널을 cbreak 로 바꾸고 teleop 루프를 돌린다.

    종료 경로가 어디로 빠지든 `finally` 에서 **정지 명령 발행 → 터미널 복원 →
    노드 정리** 를 순서대로 수행한다.

    `tty.setraw()` 대신 `tty.setcbreak()` 를 쓴다 — cbreak 는 ISIG 를 유지하므로
    **Ctrl+C 가 SIGINT 로 계속 동작**한다(raw 는 Ctrl+C 를 그냥 문자로 만든다).

    Args:
        argv: ROS 인자. `None` 이면 기본값.

    Returns:
        정상 종료 0, stdin 이 TTY 가 아니거나 초기화 실패 시 1.
    """
    if not sys.stdin.isatty():
        print(_NOT_A_TTY_MESSAGE, file=sys.stderr)
        return EXIT_FAILURE

    old_settings = termios.tcgetattr(sys.stdin.fileno())
    node: KeyboardTeleopNode | None = None
    exit_code = EXIT_SUCCESS

    rclpy.init(args=argv)
    try:
        tty.setcbreak(sys.stdin.fileno())
        sys.stdout.write(_ANSI_HIDE_CURSOR)
        sys.stdout.flush()

        node = KeyboardTeleopNode()
        node.start()

        while rclpy.ok() and not node.quit_requested:
            rclpy.spin_once(node, timeout_sec=SPIN_TIMEOUT_SEC)
    except KeyboardInterrupt:
        if node is not None:
            node.request_quit()
    except ExternalShutdownException:
        if node is not None:
            node.request_quit()
    except (ValueError, OSError) as error:
        print(f"cart_teleop: 시작 실패 — {error}", file=sys.stderr)
        exit_code = EXIT_FAILURE
    finally:
        # 1) 정지 명령 — context 가 살아 있는 동안에만 가능하다.
        if node is not None:
            node.publish_zero_burst()

        # 2) 터미널 복원 — 실패해도 나머지 정리는 계속한다.
        try:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)
            sys.stdout.write(_ANSI_SHOW_CURSOR + "\r\n")
            sys.stdout.flush()
        except Exception:  # noqa: BLE001
            pass

        # 3) 노드·context 정리. rosout 이 이미 내려갔을 수 있어 print 를 쓴다.
        if node is not None:
            try:
                node.destroy_node()
            except Exception:  # noqa: BLE001
                pass
        if rclpy.ok():
            rclpy.shutdown()
        print("cart_teleop: 정지 명령 발행 후 종료했다.")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
