"""stm_serial_bridge_node — /cmd_vel을 STM32 모터 제어 보드로 중계하는 브리지 노드.

구현 단계 5c-1 (현재): `/cmd_vel` 구독 → 최신 좌우 목표값과 수신 시각만 **저장** →
독립적인 `tx_rate_hz`(기본 20Hz) 타이머가 cmd_vel timeout을 검사해 보낼 목표를
고르고 → `SET_WHEEL_VEL` 명령 문자열 생성 → **송신 단일 출구 `_send_command()`** 가
`dry_run=false`일 때 **실제 Serial write를 수행**한다.

⚠️ 5c-1 검증은 Linux PTY(`/dev/pts/*`)로만 했다. 실제 `/dev/ttyACM*`(STM32) 연결과
모터 구동은 아직 하지 않았다.

콜백과 송신을 분리한 이유: STM32는 유효한 `SET_WHEEL_VEL`을 주기적으로 받아야 하고,
`/cmd_vel`이 끊겼을 때 마지막 속도를 계속 반복하면 위험하다. 명령 생성 주기를
`/cmd_vel` 도착 주기에서 떼어내면 상위가 죽어도 브리지가 스스로 0을 보낼 수 있다.

Watchdog 상태(`command_watchdog.select_wheel_command()`):
- `waiting`: 아직 `/cmd_vel`을 한 번도 못 받음 -> 0,0
- `active`: `cmd_vel_timeout_sec` 이내 -> 최신 목표값(이미 제한이 적용된 값)
- `timed_out`: `cmd_vel_timeout_sec` 이상 경과(경계값 포함) -> 0,0

안전 상한: `/cmd_vel` 콜백이 `wheel_speed_limiter.limit_wheel_rad_s()`로 좌우를 같은
비율로 축소한 뒤 저장하므로, `max_wheel_rad_s`를 넘는 목표는 어떤 경로로도 STM에
나가지 않는다. STM32에는 목표 각속도 clamp가 아직 없어 이 방어가 유일하다.

`dry_run` 정책:
- `dry_run=true`(기본): `SerialLink`를 **생성하지도 않는다.** 포트를 열지 않으므로
  `serial_port`가 존재하지 않는 경로여도 정상 실행된다. 명령은 `DRY-RUN` 로그만.
- `dry_run=false`: `SerialLink`를 만들어 포트를 연다. 연결에 성공한 뒤에야 구독·타이머를
  시작하고, 매 tick의 명령을 실제로 write한 뒤 **성공한 경우에만** `TX` 로그를 남긴다.
  연결 실패 시 구독·타이머를 시작하지 않고 0이 아닌 종료 코드로 끝낸다.

write가 실패하면 경고만 남기고 계속하지 않는다 — 사용자가 "명령이 가고 있다"고 믿는데
실제로는 가지 않는 상태가 가장 위험하다. 타이머 콜백은 fatal 상태만 래치하고 타이머를
취소한 뒤 정상 반환하며(`_abort_on_tx_failure()`), 실제 종료 정리(포트 close → node
destroy → rclpy shutdown)와 종료 코드 1은 `main()`의 공통 경로가 담당한다.

이 단계에서는 **아직 구현하지 않은 것**:
- Serial read/readline, 수신 스레드, STATUS 파싱
- 바퀴 최대 속도 clamp
- STOP/ESTOP/RESET_STALL/SET_PI_GAINS 명령, 상태 토픽 발행
- 실제 `/dev/ttyACM*` 연결 및 모터 구동

STM 통신 프로토콜 정본: embedded/motor/docs/serial_protocol.md
"""

import math
import sys
import time
from collections.abc import Sequence

import rclpy
from geometry_msgs.msg import Twist
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from stm_serial_bridge.command_watchdog import select_wheel_command
from stm_serial_bridge.differential_drive import cmd_vel_to_wheel_rad_s
from stm_serial_bridge.protocol import build_set_wheel_vel_command
from stm_serial_bridge.serial_link import SerialLink, SerialLinkError
from stm_serial_bridge.wheel_speed_limiter import limit_wheel_rad_s

# 로그 최소 간격(초). 20Hz 타이머와 teleop 스트림으로 콘솔이 넘치지 않게 억제하되,
# 단발 메시지는 첫 호출에서 바로 통과한다. 억제되는 동안에도 수신 카운터와 tx tick은
# 계속 증가하므로, 로그의 `#N`/`tx#N`으로 실제 건수를 확인할 수 있다.
CMD_VEL_LOG_THROTTLE_SEC = 0.5

CMD_VEL_TOPIC = "/cmd_vel"
CMD_VEL_QOS_DEPTH = 10

EXIT_SUCCESS = 0
EXIT_FAILURE = 1

# main()의 spin 루프가 한 번에 대기하는 시간(초). 유한값이어야 한다 — 콜백이 치명적
# 실패를 래치하고 반환하면 최대 이 시간 안에 루프 조건이 다시 평가되어 종료로 넘어간다.
SPIN_TIMEOUT_SEC = 0.1

# dry_run=false로 포트를 연 직후, 실제 전송이 시작됨을 사용자에게 알리는 문구.
# 5c-1에서는 PTY 검증만 했으므로 실기 대상이 아님도 함께 알린다.
TX_ENABLED_NOTICE = (
    "TX is ENABLED: every timer tick will be written to the serial port. "
    "Stage 5c-1 is verified with a Linux PTY only — do not connect a real STM32 "
    "or power the motors yet."
)


class StmSerialBridgeNode(Node):
    """Convert /cmd_vel into STM32 wheel-velocity commands.

    향후 이 노드가 `/cmd_vel`을 좌우 바퀴 목표 각속도로 변환해 USB Serial로
    STM32에 전달하게 된다. 현재는 명령 문자열 생성과 포트 연결까지만 하고,
    실제 송신은 하지 않는다.

    생성은 두 단계로 나뉜다: `__init__`은 파라미터만 준비하고, `start()`가 실행 모드를
    확정(필요하면 포트 연결)한 뒤에야 `/cmd_vel` 구독을 시작한다. 이렇게 하면
    "연결 실패 시 구독하지 않는다"가 호출 순서에 의존하지 않고 구조적으로 보장된다.
    """

    def __init__(self) -> None:
        """Declare and log parameters. 연결과 `/cmd_vel` 구독은 `start()`에서 한다."""
        super().__init__("stm_serial_bridge")

        # --- tx_rate_hz/cmd_vel_timeout_sec은 이 단계에서 로그 출력 외 사용하지 않음 ---
        self.declare_parameter("serial_port", "/dev/ttyACM0")
        self.declare_parameter("baud_rate", 115200)
        self.declare_parameter("wheel_radius_m", 0.065)
        # ⚠️ 임시값: 좌우 바퀴 중심 간 거리는 조립 후 실측이 필요하다.
        # 이 값이 틀리면 angular.z -> 좌우 속도 차 변환이 어긋나 회전량이 맞지 않는다.
        self.declare_parameter("wheel_separation_m", 0.30)
        self.declare_parameter("tx_rate_hz", 20.0)
        self.declare_parameter("cmd_vel_timeout_sec", 0.5)
        self.declare_parameter("dry_run", True)
        # ⚠️ 실제 모터 정격 최대속도가 아니라 첫 벤치 테스트용 임시 안전 제한이다.
        # STM32에는 목표 각속도 상한 clamp가 아직 없으므로(MOTION_CONTROLLER_MAX_
        # WHEEL_RAD_S 미적용) 현재 상한 방어는 브리지 쪽에만 존재한다.
        self.declare_parameter("max_wheel_rad_s", 1.0)

        self._log_parameters()

        # 차동구동 계산에 쓰는 두 값만 시작 시점에 읽어 보관한다. 이 단계에서는
        # 파라미터 동적 변경 콜백을 구현하지 않으므로, 실행 중 값을 바꿔도 반영되지
        # 않는다(필요해지면 별도 단계에서 add_on_set_parameters_callback 추가).
        self._wheel_radius_m = float(self._param_value("wheel_radius_m"))
        self._wheel_separation_m = float(self._param_value("wheel_separation_m"))
        self._dry_run = bool(self._param_value("dry_run"))
        self._tx_rate_hz = float(self._param_value("tx_rate_hz"))
        self._cmd_vel_timeout_sec = float(self._param_value("cmd_vel_timeout_sec"))
        self._max_wheel_rad_s = float(self._param_value("max_wheel_rad_s"))

        self._cmd_vel_count = 0
        self._subscription: object | None = None
        self._tx_timer: object | None = None

        # --- 타이머가 읽는 최신 목표 상태 ---
        # 콜백은 여기에만 쓰고, 송신은 타이머가 이 값을 읽어서 한다.
        self._latest_left_rad_s = 0.0
        self._latest_right_rad_s = 0.0
        # None = 아직 유효한 /cmd_vel을 한 번도 받지 않음(watchdog의 waiting 조건).
        self._last_cmd_vel_time_sec: float | None = None
        self._tx_tick_count = 0
        self._last_watchdog_state: str | None = None
        # Serial write가 한 번이라도 실패하면 True로 래치된다. 이후 어떤 tick도
        # write를 시도하지 않으며, main()의 spin 루프가 이 값을 보고 빠져나온다.
        self._tx_fatal_error = False
        # main()이 반환할 종료 코드. 치명적 실패가 래치되면 EXIT_FAILURE로 바뀐다.
        self._requested_exit_code = EXIT_SUCCESS

        # dry-run에서는 SerialLink를 아예 만들지 않는다. 객체가 없으면 포트를 열
        # 방법도 없으므로, "dry-run인데 실수로 열었다"가 구조적으로 불가능해진다.
        self._serial_link: SerialLink | None = None

    @staticmethod
    def _now_sec() -> float:
        """Return the monotonic timestamp used for every timeout calculation.

        시스템 시계(wall clock)나 ROS time이 아니라 `time.monotonic()`을 쓴다 —
        시스템 시간이 바뀌어도 경과 시간 계산이 뒤틀리지 않고, 나중에 sim time을
        도입해도 안전 timeout이 그 영향을 받지 않는다. 노드 전체에서 timeout 기준
        시각은 이 메서드 하나로 통일한다.

        Returns:
            단조 증가 시계의 현재 값(초).
        """
        return time.monotonic()

    def start(self) -> None:
        """Validate parameters, connect if required, then subscribe and start the timer.

        순서가 중요하다: 파라미터를 **포트를 열기 전에** 검증하고, 연결에 성공한 뒤에야
        구독과 타이머를 만든다. 어느 단계에서든 실패하면 예외가 올라가므로 구독·타이머가
        생성되지 않고, 노드가 살아 있는 채로 명령을 조용히 버리는 상태가 만들어지지 않는다.

        Raises:
            ValueError: `tx_rate_hz`/`cmd_vel_timeout_sec`가 0 이하이거나,
                `serial_port`/`baud_rate` 값이 유효하지 않을 때.
            SerialLinkError: `dry_run=false`인데 포트를 열 수 없을 때.
        """
        self._validate_drive_parameters()

        if self._dry_run:
            self.get_logger().info(
                "dry_run=true — SerialLink를 생성하지 않는다 "
                "(포트를 열지 않으므로 serial_port 값은 사용되지 않음)"
            )
        else:
            self._connect_serial()

        self._subscription = self.create_subscription(
            Twist, CMD_VEL_TOPIC, self._cmd_vel_callback, CMD_VEL_QOS_DEPTH
        )

        tx_period_sec = 1.0 / self._tx_rate_hz
        self._tx_timer = self.create_timer(tx_period_sec, self._tx_timer_callback)

        self.get_logger().info(
            f"stm_serial_bridge 시작 — {CMD_VEL_TOPIC} 구독 중, "
            f"송신 타이머 {self._tx_rate_hz} Hz (주기 {tx_period_sec:.4f}s), "
            f"cmd_vel timeout {self._cmd_vel_timeout_sec}s "
            "(구현 단계 5c-1: PTY로만 실제 송신 검증, 실기 미연결)"
        )

    def _validate_drive_parameters(self) -> None:
        """Reject invalid drive parameters before anything is opened or created.

        `SerialLink`·포트·구독·타이머를 만들기 **전에** 호출된다 — 잘못된 설정으로
        장치를 점유했다가 되돌리는 일이 없도록 하기 위함이다.

        0 이하는 물론 NaN/Infinity도 거부한다. NaN은 `<= 0.0` 비교를 통과해 버려서,
        유한성 검사가 없으면 `tx_rate_hz`가 NaN일 때 타이머 주기가 NaN이 되고
        `max_wheel_rad_s`가 NaN일 때 제한 계산 전체가 NaN으로 오염된다.

        `differential_drive.py`와 `wheel_speed_limiter.py`의 자체 검증은 그대로
        유지된다 — 여기서 걸러도 각 순수 함수는 자신의 계약을 스스로 지킨다.

        Raises:
            ValueError: 검증 대상 중 하나라도 유한하지 않거나 0 이하일 때. 어느
                파라미터가 잘못됐는지와 실제 값을 메시지에 담는다.
        """
        checked: tuple[tuple[str, float], ...] = (
            ("wheel_radius_m", self._wheel_radius_m),
            ("wheel_separation_m", self._wheel_separation_m),
            ("tx_rate_hz", self._tx_rate_hz),
            ("cmd_vel_timeout_sec", self._cmd_vel_timeout_sec),
            ("max_wheel_rad_s", self._max_wheel_rad_s),
        )
        for name, value in checked:
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(
                    f"{name} must be a finite value greater than 0.0, got {value}"
                )

    def _connect_serial(self) -> None:
        """Create the SerialLink and open the port (`dry_run=false` only).

        Raises:
            SerialLinkError: 포트를 열 수 없을 때.
            ValueError: 파라미터 값이 유효하지 않을 때(빈 포트, 0 이하 baud_rate).
        """
        port = str(self._param_value("serial_port"))
        baud_rate = int(self._param_value("baud_rate"))

        link = SerialLink(port, baud_rate)
        link.open()
        # open()이 성공한 뒤에만 보관한다 — 실패한 링크를 들고 있으면 종료 정리에서
        # 열지도 않은 포트를 닫으려 하게 된다.
        self._serial_link = link

        self.get_logger().info(
            f"Serial connected: port={link.port}, baud_rate={link.baud_rate}"
        )
        self.get_logger().warning(TX_ENABLED_NOTICE)

    @property
    def tx_fatal_error(self) -> bool:
        """Serial write가 실패해 송신을 중단했으면 True. `main()`의 spin 루프가 읽는다."""
        return self._tx_fatal_error

    @property
    def requested_exit_code(self) -> int:
        """노드가 요청한 프로세스 종료 코드. `main()`이 그대로 반환한다."""
        return self._requested_exit_code

    def close_serial(self) -> None:
        """Close the serial port if one was opened.

        종료 경로에서 호출된다. `SerialLink`가 없는 dry-run에서도 안전하게 통과한다.
        `close()`가 실패해도 나머지 ROS 종료 정리를 막지 않도록 여기서 예외를 잡는다.

        Ctrl+C 경로에서는 이 시점에 rcl context가 이미 무효하다. `get_logger()`로 찍으면
        "Failed to publish log message to rosout: publisher's context is invalid" 경고가
        따라붙으므로, 종료 안내는 rcl을 거치지 않는 print로 출력한다(2026-08-02 실측 확인).
        """
        if self._serial_link is None:
            return

        try:
            self._serial_link.close()
        except Exception as error:  # noqa: BLE001 - 종료 정리를 막지 않는 것이 우선
            print(
                f"[stm_serial_bridge] Serial 포트 닫기 실패(무시하고 계속): {error}",
                flush=True,
            )
        else:
            print("[stm_serial_bridge] Serial 포트를 닫았다", flush=True)
        finally:
            self._serial_link = None

    def _log_parameters(self) -> None:
        """Log every declared parameter once at startup.

        `wheel_radius_m`/`wheel_separation_m`/`dry_run` 외에는 아직 동작에 쓰이지
        않으므로, 값이 의도대로 들어왔는지 확인할 수 있는 유일한 수단이다.
        """
        logger = self.get_logger()
        logger.info("파라미터:")
        logger.info(f"  serial_port         = {self._param_value('serial_port')}")
        logger.info(f"  baud_rate           = {self._param_value('baud_rate')}")
        logger.info(f"  wheel_radius_m      = {self._param_value('wheel_radius_m')}")
        logger.info(
            f"  wheel_separation_m  = {self._param_value('wheel_separation_m')}"
            "  <-- ⚠️ 조립 후 실측 필요한 임시값"
        )
        logger.info(f"  tx_rate_hz          = {self._param_value('tx_rate_hz')}")
        logger.info(
            f"  cmd_vel_timeout_sec = {self._param_value('cmd_vel_timeout_sec')}"
        )
        logger.info(f"  dry_run             = {self._param_value('dry_run')}")
        logger.info(
            f"  max_wheel_rad_s     = {self._param_value('max_wheel_rad_s')}"
            "  <-- ⚠️ 실제 모터 정격 확정 전 임시 벤치 제한"
        )

    def _param_value(self, name: str) -> object:
        """Return the current value of a declared parameter.

        Args:
            name: 선언된 파라미터 이름.

        Returns:
            파라미터의 현재 값.
        """
        return self.get_parameter(name).value

    def _send_command(
        self,
        command: str,
        *,
        state: str,
        tx_tick_count: int,
        force_log: bool = False,
    ) -> None:
        """Single exit point for every command going to the STM32.

        모든 STM 명령(향후 `STOP`/`ESTOP` 등 포함)은 반드시 이 메서드를 거친다.
        송신 여부 판단이 여기 한 곳에만 있으므로, 실제 write 호출 지점도 여기 하나뿐이다.

        동작:
        - `dry_run=true`: 포트가 없으므로 `DRY-RUN` 로그만.
        - `dry_run=false`: `SerialLink.write()`로 실제 전송하고, **성공한 뒤에만**
          `TX` 로그를 남긴다. 실패하면 로그를 남기지 않고 예외가 올라간다 —
          "보냈다"는 기록이 실제 전송과 어긋나면 실기 디버깅이 불가능해진다.

        Args:
            command: STM32로 보낼 명령 한 줄. CRLF 종단을 포함한다.
            state: 이 명령을 고른 watchdog 상태(`waiting`/`active`/`timed_out`).
            tx_tick_count: 송신 타이머 tick 번호. 타이머가 돌고 있음을 로그로 확인하는
                수단이며, throttle로 눌린 구간도 번호 증가로 드러난다.
            force_log: True면 throttle을 무시하고 무조건 남긴다. 상태가 바뀐 tick은
                안전상 반드시 보여야 하므로, 짧게 스쳐가는 상태(예: 0.5초짜리 active)가
                throttle에 묻히지 않게 하기 위함이다.

        Raises:
            SerialLinkError: `dry_run=false`에서 실제 전송이 실패했을 때. 호출자
                (`_tx_timer_callback`)가 잡아 치명적 오류로 처리한다.
        """
        if self._tx_fatal_error:
            # 이미 치명적 실패를 래치한 뒤라면 어떤 경로로 들어와도 write하지 않는다
            # (취소 직전 큐에 들어간 tick이 한 번 더 진입하는 경우 대비).
            return

        if self._dry_run:
            label = "DRY-RUN"
        else:
            # 이 지점에 도달했다면 start()에서 연결에 성공했다는 뜻이다. 그래도
            # None이면 조용히 넘어가지 않고 오류로 드러낸다.
            if self._serial_link is None:
                raise SerialLinkError(
                    "Serial write failed: reason=serial link is not initialised"
                )
            # write가 실패하면 예외가 올라가 아래 TX 로그에 도달하지 못한다 —
            # "보냈다"는 기록이 실제 전송과 어긋나지 않게 하는 것이 핵심이다.
            self._serial_link.write(command)
            label = "TX"

        # command는 CRLF로 끝나므로 그대로 찍으면 로그 한 줄이 여러 줄로 깨진다.
        # !r(repr)로 이스케이프해 한 줄 안에 '...\r\n' 형태로 보이게 한다.
        message = f"{label} tx#{tx_tick_count} state={state} command={command!r}"

        # rclpy 로거는 필터 설정을 **호출 지점(파일·함수·줄 번호)별로 캐시**하며, 같은
        # 지점에서 throttle_duration_sec를 바꿔 넘기면
        # "Requested logging filters cannot be changed between calls."로 죽는다
        # (2026-08-02 실측 확인). 따라서 throttle 있는 호출과 없는 호출을 서로 다른
        # 줄로 분리한다 — 한 호출에 값만 바꿔 넘기는 방식은 쓸 수 없다.
        if force_log:
            self.get_logger().info(message)
        else:
            self.get_logger().info(
                message, throttle_duration_sec=CMD_VEL_LOG_THROTTLE_SEC
            )

    def _cmd_vel_callback(self, message: Twist) -> None:
        """Store the latest wheel targets and arrival time. **송신하지 않는다.**

        이 콜백은 상태만 갱신하고, 명령 문자열 생성과 송신은 `_tx_timer_callback()`이
        담당한다 — `/cmd_vel` 도착 주기와 STM 송신 주기를 분리하기 위함이다.

        저장 전에 `limit_wheel_rad_s()`로 상한을 적용한다 — watchdog과 타이머는
        **제한된 값만** 보게 되므로, 상한을 넘는 목표가 어떤 경로로도 STM에 나가지 않는다.

        NaN/Infinity가 섞인 `/cmd_vel`은 최신 상태에 **저장하지 않는다.** 저장해 버리면
        이후 모든 타이머 tick이 그 값으로 실패하게 되므로, 마지막 유효 목표값과 수신
        시각을 그대로 유지하고(=timeout이 정상적으로 흘러 0,0으로 수렴) 이 메시지만
        버린다.

        Args:
            message: 수신한 Twist 명령. 차동구동에서는 linear.x와 angular.z만 쓴다.
        """
        self._cmd_vel_count += 1

        try:
            left_rad_s, right_rad_s = cmd_vel_to_wheel_rad_s(
                message.linear.x,
                message.angular.z,
                self._wheel_radius_m,
                self._wheel_separation_m,
            )
        except ValueError as error:
            # 선언된 기본값은 유효하지만, --ros-args -p 로 0이나 음수를 넘길 수 있다.
            # 콜백에서 예외가 그대로 올라가면 매 메시지마다 반복되므로 여기서 잡는다.
            self.get_logger().error(
                f"차동구동 변환 실패 — 파라미터를 확인하라: {error}",
                throttle_duration_sec=CMD_VEL_LOG_THROTTLE_SEC,
            )
            return

        if not math.isfinite(left_rad_s) or not math.isfinite(right_rad_s):
            # 발행자가 NaN/Infinity를 담은 /cmd_vel을 보내면 여기로 온다(차동구동
            # 변환은 의도적으로 linear.x/angular.z를 검증하지 않는다).
            self.get_logger().error(
                f"{CMD_VEL_TOPIC} #{self._cmd_vel_count} 무시 — 유한하지 않은 값: "
                f"left={left_rad_s} right={right_rad_s} "
                "(최신 목표값과 수신 시각을 갱신하지 않는다)",
                throttle_duration_sec=CMD_VEL_LOG_THROTTLE_SEC,
            )
            return

        try:
            limited_left_rad_s, limited_right_rad_s = limit_wheel_rad_s(
                left_rad_s, right_rad_s, self._max_wheel_rad_s
            )
        except ValueError as error:
            # start()에서 max_wheel_rad_s를 검증하고 위에서 유한성도 확인했으므로
            # 정상적으로는 도달하지 않는다. 도달하면 이전 유효 목표를 유지한 채
            # 이 메시지만 버린다(수신 시각도 갱신하지 않음 -> timeout이 흘러 0,0).
            self.get_logger().error(
                f"바퀴 속도 제한 실패 — 이 메시지를 건너뛴다: {error}",
                throttle_duration_sec=CMD_VEL_LOG_THROTTLE_SEC,
            )
            return

        # watchdog/타이머는 이 값만 읽는다 — 제한 전 값은 어디에도 보관하지 않는다.
        self._latest_left_rad_s = limited_left_rad_s
        self._latest_right_rad_s = limited_right_rad_s
        self._last_cmd_vel_time_sec = self._now_sec()

        was_limited = (
            limited_left_rad_s != left_rad_s or limited_right_rad_s != right_rad_s
        )
        # 제한이 걸린 경우와 아닌 경우를 서로 다른 호출 지점으로 분리한다 — rclpy
        # 로거는 필터 설정을 호출 지점별로 캐시하므로 한 지점에서 형식만 바꿔야 한다.
        if was_limited:
            self.get_logger().warning(
                f"{CMD_VEL_TOPIC} #{self._cmd_vel_count} 제한 후 저장: "
                f"raw left={left_rad_s:.3f} right={right_rad_s:.3f} -> "
                f"limited left={limited_left_rad_s:.3f} "
                f"right={limited_right_rad_s:.3f}, "
                f"max={self._max_wheel_rad_s:.3f} rad/s",
                throttle_duration_sec=CMD_VEL_LOG_THROTTLE_SEC,
            )
        else:
            self.get_logger().info(
                f"{CMD_VEL_TOPIC} #{self._cmd_vel_count} 저장: "
                f"linear.x={message.linear.x:.3f} angular.z={message.angular.z:.3f}"
                f" -> left={limited_left_rad_s:.3f} rad/s "
                f"right={limited_right_rad_s:.3f} rad/s",
                throttle_duration_sec=CMD_VEL_LOG_THROTTLE_SEC,
            )

    def _abort_on_tx_failure(self, error: SerialLinkError) -> None:
        """Latch a fatal TX failure and stop the timer. **종료는 하지 않는다.**

        Serial write 실패를 경고만 남기고 계속 진행하면, 사용자는 명령이 STM에 가고
        있다고 믿는데 실제로는 아무것도 가지 않는 상태가 된다 — 사람이 함께 있는
        환경에서 가장 위험한 실패 방식이다. 따라서 즉시 송신을 멈춘다.

        이 메서드는 **타이머 콜백 안에서 호출되므로** ROS context나 노드의 수명을
        직접 건드리지 않는다. `rclpy.shutdown()`/`destroy_node()`/`close_serial()`을
        여기서 호출하면 executor가 waitset을 돌고 있는 도중에 context가 파괴되어
        DDS 수신 스레드가 정리되지 못하고 프로세스가 남는다(2026-08-02 실측 확인).
        실제 종료 정리는 `main()`의 공통 경로가 담당한다.

        타이머를 취소하는 이유: 취소하지 않으면 종료 정리가 진행되는 동안에도 다음
        tick이 들어와 이미 실패한 포트에 다시 write를 시도한다.

        Args:
            error: 첫 write 실패 원인.
        """
        if self._tx_fatal_error:
            return  # 이미 래치됨(중복 로그·중복 종료 요청 방지)
        self._tx_fatal_error = True
        self._requested_exit_code = EXIT_FAILURE

        if self._tx_timer is not None:
            self._tx_timer.cancel()

        self.get_logger().error(f"Serial TX failed: {error}")
        self.get_logger().error(
            "송신을 중단하고 노드를 종료한다 (정리는 main의 공통 종료 경로에서 수행)"
        )

    def _tx_timer_callback(self) -> None:
        """Pick the command for this tick and hand it to the single send exit.

        `tx_rate_hz` 주기로 호출된다. `/cmd_vel` 도착과 무관하게 항상 돌기 때문에,
        상위가 멈춰도 `timed_out`으로 넘어가 0,0을 계속 내보낼 수 있다.
        """
        if self._tx_fatal_error:
            # 타이머는 취소했지만, 취소 직전에 이미 큐에 들어간 tick이 한 번 더
            # 실행될 수 있다. 실패한 포트에 다시 write하지 않도록 여기서 막는다.
            return

        self._tx_tick_count += 1

        try:
            left_rad_s, right_rad_s, state = select_wheel_command(
                now_sec=self._now_sec(),
                last_cmd_vel_time_sec=self._last_cmd_vel_time_sec,
                cmd_vel_timeout_sec=self._cmd_vel_timeout_sec,
                latest_left_rad_s=self._latest_left_rad_s,
                latest_right_rad_s=self._latest_right_rad_s,
            )
        except ValueError as error:
            # start()에서 파라미터를 검증하고 콜백이 유한값만 저장하므로 정상적으로는
            # 도달하지 않는다. 그래도 타이머가 예외로 죽어 송신이 조용히 멈추는 것보다
            # 로그를 남기고 다음 tick을 기다리는 편이 안전하다.
            self.get_logger().error(
                f"송신 목표 선택 실패 — 이 tick을 건너뛴다: {error}",
                throttle_duration_sec=CMD_VEL_LOG_THROTTLE_SEC,
            )
            return

        try:
            command = build_set_wheel_vel_command(left_rad_s, right_rad_s)
        except ValueError as error:
            self.get_logger().error(
                f"STM 명령 생성 실패 — 이 tick을 건너뛴다: {error}",
                throttle_duration_sec=CMD_VEL_LOG_THROTTLE_SEC,
            )
            return

        state_changed = state != self._last_watchdog_state
        if state_changed:
            if self._last_watchdog_state is None:
                self.get_logger().info(f"watchdog state: {state}")
            else:
                self.get_logger().info(
                    f"watchdog state: {self._last_watchdog_state} -> {state}"
                )
            self._last_watchdog_state = state

        try:
            self._send_command(
                command,
                state=state,
                tx_tick_count=self._tx_tick_count,
                force_log=state_changed,
            )
        except SerialLinkError as error:
            # 실제 전송 실패는 복구 시도 대상이 아니다 — 즉시 멈추고 종료한다.
            self._abort_on_tx_failure(error)


def _shutdown(node: StmSerialBridgeNode) -> None:
    """Close the serial port, then destroy the node and shut the context down.

    순서가 중요하다: 포트를 먼저 닫아야 노드가 사라진 뒤에도 장치가 잡혀 있는 상태가
    남지 않는다. `close_serial()`은 내부에서 예외를 잡으므로 아래 ROS 정리를 막지 않는다.

    Args:
        node: 정리할 노드.
    """
    node.close_serial()
    node.destroy_node()
    # ExternalShutdownException 경로에서는 context가 이미 닫혀 있어
    # shutdown()을 다시 호출하면 예외가 난다.
    if rclpy.ok():
        rclpy.shutdown()


def main(args: Sequence[str] | None = None) -> int:
    """Start the stm_serial_bridge node.

    Args:
        args: ROS2 인자. None이면 sys.argv를 사용한다.

    Returns:
        프로세스 종료 코드. 포트 연결 실패나 Serial TX 실패로 끝난 경우 `EXIT_FAILURE`.
    """
    rclpy.init(args=args)
    node = StmSerialBridgeNode()

    try:
        node.start()
    except (SerialLinkError, ValueError) as error:
        # 구독 전에 실패한 경우. traceback 없이 오류만 남기고 실패로 종료한다.
        # SerialLinkError 메시지에 port/baud_rate/원래 이유가 이미 담겨 있다.
        node.get_logger().error(f"노드를 시작할 수 없다: {error}")
        _shutdown(node)
        return EXIT_FAILURE

    try:
        # rclpy.spin() 대신 직접 루프를 돈다 — 치명적 TX 실패를 **콜백 밖에서**
        # 감지해 종료해야 하기 때문이다. 콜백 안에서 rclpy.shutdown()을 부르면
        # executor가 waitset을 사용하는 중에 context가 파괴되어 DDS 수신 스레드가
        # 정리되지 못하고 프로세스가 남는다(2026-08-02 실측 확인).
        # timeout_sec는 유한값이므로 콜백이 fatal을 래치하고 반환하면 최대 이 시간
        # 안에 while 조건을 다시 평가한다. busy loop가 아니다.
        while rclpy.ok() and not node.tx_fatal_error:
            rclpy.spin_once(node, timeout_sec=SPIN_TIMEOUT_SEC)
    except (KeyboardInterrupt, ExternalShutdownException):
        # Humble의 rclpy는 SIGINT를 받으면 context를 먼저 shutdown하므로,
        # KeyboardInterrupt가 아니라 ExternalShutdownException이 올라올 수 있다.
        # 둘 다 잡지 않으면 Ctrl+C마다 traceback이 남는다(2026-08-02 실측 확인).
        #
        # 이 시점에는 context가 이미 무효라 node.get_logger()로 찍으면
        # "Failed to publish log message to rosout: publisher's context is invalid"
        # 경고가 따라붙는다. 종료 안내는 rcl을 거치지 않는 print로 출력한다.
        print("[stm_serial_bridge] 종료 요청 수신 — 노드를 정리한다", flush=True)
    finally:
        # 공통 종료 정리: Serial close -> node destroy -> rclpy shutdown.
        _shutdown(node)

    exit_code = node.requested_exit_code
    if exit_code != EXIT_SUCCESS:
        print(
            f"[stm_serial_bridge] Serial TX 실패로 종료한다 (종료 코드 {exit_code})",
            flush=True,
        )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
