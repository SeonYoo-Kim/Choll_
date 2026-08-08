"""stm_serial_bridge_node — /cmd_vel을 STM32 모터 제어 보드로 중계하는 브리지 노드.

**송신 경로(TX)**: `/cmd_vel` 구독 → 최신 좌우 목표값과 수신 시각만 **저장** →
독립적인 `tx_rate_hz`(기본 20Hz) 타이머가 cmd_vel timeout을 검사해 보낼 목표를
고르고 → `SET_WHEEL_VEL` 명령 문자열 생성 → **송신 단일 출구 `_send_command()`** 가
`dry_run=false`일 때 실제 Serial write를 수행한다.
→ **2026-08-02 실기 검증 완료** (실제 STM32 + 모터로 전진/후진/좌우회전 및 watchdog 정지 확인).

**수신 경로(RX, 구현 단계 8c — 현재 작업)**: `rx_poll_hz`(기본 50Hz) 전용 타이머 →
`SerialLink.read_available()` → `LineDecoder.feed()` → `parse_packet()` → 종류별 처리 →
`/stm/*` 상태 토픽 발행.
⚠️ **수신 경로는 아직 실기 미검증이다.** PTY로만 확인했다.

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
  `serial_port`가 존재하지 않는 경로여도 정상 실행된다. 명령은 `DRY-RUN` 로그만이며
  **RX 타이머도 만들지 않는다**(읽을 포트가 없다). 단 `/stm/*` Publisher는 생성해
  `connected=false`·`fault=NONE` 초기 상태를 발행한다.
- `dry_run=false`: `SerialLink`를 만들어 포트를 연다. 연결에 성공한 뒤에야 구독·TX/RX
  타이머를 시작하고, 매 tick의 명령을 실제로 write한 뒤 **성공한 경우에만** `TX` 로그를
  남긴다. 연결 실패 시 아무 타이머도 시작하지 않고 0이 아닌 종료 코드로 끝낸다.

Serial 오류(write/read 어느 쪽이든)는 경고만 남기고 계속하지 않는다 — 사용자가 "명령이
가고 있다"고 믿는데 실제로는 가지 않는 상태가 가장 위험하다. 타이머 콜백은 fatal 상태만
래치하고 TX/RX 타이머를 모두 취소한 뒤 정상 반환하며(`_abort_on_serial_failure()`),
실제 종료 정리(포트 close → node destroy → rclpy shutdown)와 종료 코드 1은 `main()`의
공통 경로가 담당한다.

이 단계에서는 **아직 구현하지 않은 것**:
- `STOP`/`ESTOP`/`RESET_STALL`/`SET_PI_GAINS` 명령 송신
- Serial 자동 재연결
- STATUS 수신 경로의 실기 검증(현재 PTY만), 좌우 물리 엔코더 매핑 확정

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
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool, Float32MultiArray, Int16MultiArray, Int32MultiArray, String

from stm_serial_bridge.command_watchdog import select_wheel_command
from stm_serial_bridge.differential_drive import cmd_vel_to_wheel_rad_s
from stm_serial_bridge.line_decoder import LineDecoder
from stm_serial_bridge.packet_parser import (
    FaultPacket,
    PacketKind,
    PiGainsPacket,
    StallCause,
    StatusPacket,
    parse_packet,
)
from stm_serial_bridge.protocol import build_set_wheel_vel_command
from stm_serial_bridge.serial_link import SerialLink, SerialLinkError
from stm_serial_bridge.wheel_speed_limiter import limit_wheel_rad_s

# 로그 최소 간격(초). 20Hz 타이머와 teleop 스트림으로 콘솔이 넘치지 않게 억제하되,
# 단발 메시지는 첫 호출에서 바로 통과한다. 억제되는 동안에도 수신 카운터와 tx tick은
# 계속 증가하므로, 로그의 `#N`/`tx#N`으로 실제 건수를 확인할 수 있다.
CMD_VEL_LOG_THROTTLE_SEC = 0.5

CMD_VEL_TOPIC = "/cmd_vel"
CMD_VEL_QOS_DEPTH = 10

# STATUS 데이터 토픽. 값이 계속 바뀌는 스트림이라 일반 depth 10으로 발행한다.
WHEEL_TARGET_TOPIC = "/stm/wheel_target_rad_s"
WHEEL_ACTUAL_TOPIC = "/stm/wheel_actual_rad_s"
PWM_TOPIC = "/stm/pwm"
ENCODER_TOTAL_TOPIC = "/stm/encoder_total"
STATUS_DATA_QOS_DEPTH = 10

# 상태 토픽. 최신 값 하나만 의미가 있으므로 depth=1 + TRANSIENT_LOCAL로 발행해
# 늦게 붙은 구독자도 곧바로 현재 상태를 받게 한다.
CONNECTED_TOPIC = "/stm/connected"
FAULT_TOPIC = "/stm/fault"

# /stm/fault 값. STM의 Stall Fault는 latched 상태이므로 "현재 상태"로 표현한다
# (단발 이벤트 로그가 아니다).
FAULT_NONE = "NONE"
FAULT_STALL_LEFT = "STALL_LEFT"
FAULT_STALL_RIGHT = "STALL_RIGHT"
FAULT_STALL_BOTH = "STALL_BOTH"

_STALL_CAUSE_TO_FAULT = {
    StallCause.LEFT: FAULT_STALL_LEFT,
    StallCause.RIGHT: FAULT_STALL_RIGHT,
    StallCause.BOTH: FAULT_STALL_BOTH,
}

EXIT_SUCCESS = 0
EXIT_FAILURE = 1

# main()의 spin 루프가 한 번에 대기하는 시간(초). 유한값이어야 한다 — 콜백이 치명적
# 실패를 래치하고 반환하면 최대 이 시간 안에 루프 조건이 다시 평가되어 종료로 넘어간다.
SPIN_TIMEOUT_SEC = 0.1

# dry_run=false로 포트를 연 직후, 실제 전송이 시작됨을 사용자에게 알리는 문구.
# 송신 경로는 2026-08-02 실기 검증을 마쳤고, 아직 검증되지 않은 것은 수신 경로다.
TX_ENABLED_NOTICE = (
    "TX is ENABLED: every timer tick will be written to the serial port. "
    "The TX path was verified on real hardware (2026-08-02); the RX/STATUS path "
    "is still PTY-only, so treat /stm/* topics as unverified."
)


class StmSerialBridgeNode(Node):
    """Convert /cmd_vel into STM32 wheel-velocity commands.

    향후 이 노드가 `/cmd_vel`을 좌우 바퀴 목표 각속도로 변환해 USB Serial로
    STM32에 전달하고(TX), STM이 보내는 `STATUS`를 읽어 `/stm/*` 상태 토픽으로
    발행한다(RX).

    생성은 두 단계로 나뉜다: `__init__`은 파라미터만 준비하고, `start()`가 실행 모드를
    확정(필요하면 포트 연결)한 뒤에야 구독과 타이머를 시작한다. 이렇게 하면
    "연결 실패 시 구독하지 않는다"가 호출 순서에 의존하지 않고 구조적으로 보장된다.
    """

    def __init__(self) -> None:
        """Declare and log parameters. 연결·구독·타이머는 모두 `start()`에서 한다."""
        super().__init__("stm_serial_bridge")

        self.declare_parameter("serial_port", "/dev/ttyACM0")
        self.declare_parameter("baud_rate", 115200)
        self.declare_parameter("wheel_radius_m", 0.065)
        # 좌우 구동 바퀴 트레드 중심선 간 거리.
        # 🔴 2026-08-07 실측 정정: 0.38 -> 0.265 (줄자 26~27cm). 0.38이면 실제
        #   회전율이 명령의 1.43배가 되어 Nav2가 좌우로 진동한다 (TEST_LOG 참조).
        # 이 값이 틀리면 angular.z -> 좌우 속도 차 변환이 어긋나 회전량이 맞지 않는다.
        # config/stm_serial_bridge.yaml 과 같은 값을 유지할 것 — launch 를 거치지 않고
        # `ros2 run` 으로 직접 띄우면 이 기본값이 쓰인다.
        self.declare_parameter("wheel_separation_m", 0.265)
        self.declare_parameter("tx_rate_hz", 20.0)
        self.declare_parameter("cmd_vel_timeout_sec", 0.5)
        self.declare_parameter("dry_run", True)
        # ⚠️ 실제 모터 정격 최대속도가 아니라 첫 벤치 테스트용 임시 안전 제한이다.
        # STM32에는 목표 각속도 상한 clamp가 아직 없으므로(MOTION_CONTROLLER_MAX_
        # WHEEL_RAD_S 미적용) 현재 상한 방어는 브리지 쪽에만 존재한다.
        self.declare_parameter("max_wheel_rad_s", 1.0)
        # RX 폴링 주기. STATUS는 10Hz로 오므로 50Hz면 한 줄이 도착한 뒤 최대 20ms 안에
        # 읽힌다. TX 타이머(20Hz)와 분리한 이유는 두 주기가 서로 다른 이유로 바뀔 수
        # 있기 때문이다(송신 주기는 STM timeout, 수신 주기는 상태 신선도가 기준).
        self.declare_parameter("rx_poll_hz", 50.0)
        # 마지막 유효 STATUS 이후 이 시간 이상 지나면 /stm/connected를 false로 내린다.
        self.declare_parameter("status_timeout_sec", 0.5)

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
        self._rx_poll_hz = float(self._param_value("rx_poll_hz"))
        self._status_timeout_sec = float(self._param_value("status_timeout_sec"))

        self._cmd_vel_count = 0
        self._subscription: object | None = None
        self._tx_timer: object | None = None
        self._rx_timer: object | None = None

        # --- RX 상태 ---
        # 줄 조립은 LineDecoder가, 의미 해석은 parse_packet()이 담당한다.
        self._decoder = LineDecoder()
        # /stm/connected는 **포트 open 여부가 아니라 유효한 STATUS 수신 여부**다.
        # 포트가 열려 있어도 STM이 조용하면 데이터는 신선하지 않으므로 false여야 한다.
        self._connected = False
        # None = 아직 유효한 STATUS를 한 번도 받지 않음.
        self._last_status_time_sec: float | None = None
        # Stall Fault는 STM에서 latched 상태이므로 브리지도 상태로 들고 간다.
        # 연결이 끊겨도 임의로 NONE으로 되돌리지 않는다(마지막 확인값 유지).
        self._fault_state = FAULT_NONE
        self._status_count = 0
        self._malformed_count = 0
        # 마지막으로 발행한 상태값. 50Hz마다 같은 값을 다시 쏘지 않도록 비교에 쓴다.
        # None = 아직 한 번도 발행하지 않음(시작 시 강제 발행으로 채워진다).
        self._last_published_connected: bool | None = None
        self._last_published_fault: str | None = None

        # --- 타이머가 읽는 최신 목표 상태 ---
        # 콜백은 여기에만 쓰고, 송신은 타이머가 이 값을 읽어서 한다.
        self._latest_left_rad_s = 0.0
        self._latest_right_rad_s = 0.0
        # None = 아직 유효한 /cmd_vel을 한 번도 받지 않음(watchdog의 waiting 조건).
        self._last_cmd_vel_time_sec: float | None = None
        self._tx_tick_count = 0
        self._last_watchdog_state: str | None = None
        # Serial I/O(write 또는 read)가 한 번이라도 실패하면 True로 래치된다. 이후
        # 어떤 tick도 write/read를 시도하지 않으며, main()의 spin 루프가 이 값을 보고
        # 빠져나온다. TX/RX를 하나의 상태로 합친 이유: 포트가 고장 나면 방향과 무관하게
        # 브리지 전체를 멈춰야 한다.
        self._serial_fatal_error = False
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
        """Validate parameters, connect if required, then create publishers and timers.

        순서가 중요하다: 파라미터를 **포트를 열기 전에** 검증하고, 연결에 성공한 뒤에야
        구독과 타이머를 만든다. 어느 단계에서든 실패하면 예외가 올라가므로 구독·타이머가
        생성되지 않고, 노드가 살아 있는 채로 명령을 조용히 버리는 상태가 만들어지지 않는다.

        `/stm/*` Publisher는 `dry_run` 여부와 무관하게 만들고 초기 상태
        (`connected=false`, `fault=NONE`)를 발행한다 — 구독자가 "아직 아무 상태도 없음"과
        "연결되지 않음"을 구분할 수 없으면 안 되기 때문이다. 반면 **RX 타이머는
        `dry_run=false`에서만** 만든다(읽을 포트가 없으면 폴링할 이유가 없다).

        Raises:
            ValueError: 검증 대상 파라미터가 0 이하/비유한이거나, `serial_port`/
                `baud_rate` 값이 유효하지 않을 때.
            SerialLinkError: `dry_run=false`인데 포트를 열 수 없을 때.
        """
        self._validate_parameters()

        # 연결 시도보다 먼저 만든다 — 연결이 실패해도 connected=false가 발행되어
        # 구독자가 상태를 알 수 있다.
        self._create_status_publishers()
        self._publish_connected(force=True)
        self._publish_fault(force=True)

        if self._dry_run:
            self.get_logger().info(
                "dry_run=true — SerialLink를 생성하지 않는다 "
                "(포트를 열지 않으므로 serial_port 값은 사용되지 않고, RX 타이머도 없다)"
            )
        else:
            self._connect_serial()

        self._subscription = self.create_subscription(
            Twist, CMD_VEL_TOPIC, self._cmd_vel_callback, CMD_VEL_QOS_DEPTH
        )

        tx_period_sec = 1.0 / self._tx_rate_hz
        self._tx_timer = self.create_timer(tx_period_sec, self._tx_timer_callback)

        rx_description = "없음(dry_run)"
        if not self._dry_run:
            rx_period_sec = 1.0 / self._rx_poll_hz
            self._rx_timer = self.create_timer(rx_period_sec, self._rx_timer_callback)
            rx_description = f"{self._rx_poll_hz} Hz (주기 {rx_period_sec:.4f}s)"

        self.get_logger().info(
            f"stm_serial_bridge 시작 — {CMD_VEL_TOPIC} 구독 중, "
            f"송신 타이머 {self._tx_rate_hz} Hz (주기 {tx_period_sec:.4f}s), "
            f"cmd_vel timeout {self._cmd_vel_timeout_sec}s, "
            f"수신 타이머 {rx_description}, "
            f"STATUS timeout {self._status_timeout_sec}s"
        )

    def _create_status_publishers(self) -> None:
        """Create the six `/stm/*` publishers.

        STATUS 데이터 4개는 값이 계속 바뀌는 스트림이라 일반 depth 10으로 둔다.
        `connected`/`fault`는 최신 값 하나만 의미가 있는 상태라 depth=1 +
        RELIABLE + TRANSIENT_LOCAL로 두어, 늦게 붙은 구독자도 곧바로 현재 상태를 받는다.
        """
        self._wheel_target_publisher = self.create_publisher(
            Float32MultiArray, WHEEL_TARGET_TOPIC, STATUS_DATA_QOS_DEPTH
        )
        self._wheel_actual_publisher = self.create_publisher(
            Float32MultiArray, WHEEL_ACTUAL_TOPIC, STATUS_DATA_QOS_DEPTH
        )
        self._pwm_publisher = self.create_publisher(
            Int16MultiArray, PWM_TOPIC, STATUS_DATA_QOS_DEPTH
        )
        self._encoder_publisher = self.create_publisher(
            Int32MultiArray, ENCODER_TOTAL_TOPIC, STATUS_DATA_QOS_DEPTH
        )

        state_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._connected_publisher = self.create_publisher(
            Bool, CONNECTED_TOPIC, state_qos
        )
        self._fault_publisher = self.create_publisher(String, FAULT_TOPIC, state_qos)

    def _validate_parameters(self) -> None:
        """Reject invalid parameters before anything is opened or created.

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
            ("rx_poll_hz", self._rx_poll_hz),
            ("status_timeout_sec", self._status_timeout_sec),
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
    def serial_fatal_error(self) -> bool:
        """Serial I/O가 실패해 송수신을 중단했으면 True. `main()`의 spin 루프가 읽는다."""
        return self._serial_fatal_error

    @property
    def connected(self) -> bool:
        """유효한 STATUS를 최근에 받았으면 True. 포트 open 여부와는 다르다."""
        return self._connected

    @property
    def fault_state(self) -> str:
        """현재 fault 상태 문자열(`NONE`/`STALL_LEFT`/`STALL_RIGHT`/`STALL_BOTH`)."""
        return self._fault_state

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
            "  <-- 2026-08-04 좌우 구동 바퀴 트레드 중심선 간 실측값"
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
        logger.info(f"  rx_poll_hz          = {self._param_value('rx_poll_hz')}")
        logger.info(
            f"  status_timeout_sec  = {self._param_value('status_timeout_sec')}"
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
        if self._serial_fatal_error:
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

    # ------------------------------------------------------------------
    # RX: STATUS 수신 및 상태 토픽 발행
    # ------------------------------------------------------------------

    def _publish_connected(self, *, force: bool = False) -> None:
        """Publish `/stm/connected` when the value changed (or when forced).

        50Hz마다 같은 값을 다시 쏘지 않는다 — TRANSIENT_LOCAL depth=1이라 늦게 붙은
        구독자도 마지막 값을 받으므로 변화 시점만 발행하면 충분하다.

        Args:
            force: 값이 바뀌지 않아도 발행한다. 시작 시 초기 상태 발행에 쓴다.
        """
        if not force and self._last_published_connected == self._connected:
            return
        self._connected_publisher.publish(Bool(data=self._connected))
        self._last_published_connected = self._connected

    def _publish_fault(self, *, force: bool = False) -> None:
        """Publish `/stm/fault` when the state changed (or when forced).

        Args:
            force: 값이 바뀌지 않아도 발행한다. 시작 시 초기 상태 발행에 쓴다.
        """
        if not force and self._last_published_fault == self._fault_state:
            return
        self._fault_publisher.publish(String(data=self._fault_state))
        self._last_published_fault = self._fault_state

    def _set_connected(self, connected: bool) -> None:
        """Update the connected state and publish/log only on change.

        Args:
            connected: 새 연결 상태.
        """
        if self._connected == connected:
            return
        self._connected = connected
        if connected:
            self.get_logger().info(
                f"{CONNECTED_TOPIC}: true — 유효한 STATUS 수신 시작"
            )
        else:
            self.get_logger().warning(
                f"{CONNECTED_TOPIC}: false — 마지막 유효 STATUS 이후 "
                f"{self._status_timeout_sec}s 이상 경과 "
                f"(fault 상태 {self._fault_state}는 마지막 확인값을 유지)"
            )
        self._publish_connected()

    def _set_fault_state(self, fault_state: str) -> None:
        """Update the fault state and publish only on change.

        Args:
            fault_state: 새 fault 상태 문자열.
        """
        if self._fault_state == fault_state:
            return
        self._fault_state = fault_state
        self._publish_fault()

    def _publish_status(self, status: StatusPacket) -> None:
        """Publish one STATUS packet to the four data topics.

        모든 배열은 `[left, right]` 순서다. STATUS 와이어 순서는 `LT,LA,RT,RA`(좌우
        교차)이므로 여기서 좌우로 다시 묶는다 — 순서를 잘못 묶으면 목표와 실측이
        서로 섞인다.

        Args:
            status: 파싱된 STATUS 패킷.
        """
        self._wheel_target_publisher.publish(
            Float32MultiArray(
                data=[status.left_target_rad_s, status.right_target_rad_s]
            )
        )
        self._wheel_actual_publisher.publish(
            Float32MultiArray(
                data=[status.left_actual_rad_s, status.right_actual_rad_s]
            )
        )
        self._pwm_publisher.publish(
            Int16MultiArray(data=[status.left_pwm, status.right_pwm])
        )
        self._encoder_publisher.publish(
            Int32MultiArray(
                data=[status.left_encoder_total, status.right_encoder_total]
            )
        )

    def _handle_status(self, status: StatusPacket) -> None:
        """Publish the STATUS data and mark the link as fresh.

        Args:
            status: 파싱된 STATUS 패킷.
        """
        self._status_count += 1
        self._last_status_time_sec = self._now_sec()
        self._publish_status(status)
        self._set_connected(True)

        self.get_logger().info(
            f"STATUS #{self._status_count}: "
            f"target L={status.left_target_rad_s:.2f} R={status.right_target_rad_s:.2f}, "
            f"actual L={status.left_actual_rad_s:.2f} R={status.right_actual_rad_s:.2f}, "
            f"pwm L={status.left_pwm} R={status.right_pwm}, "
            f"enc L={status.left_encoder_total} R={status.right_encoder_total}",
            throttle_duration_sec=CMD_VEL_LOG_THROTTLE_SEC,
        )

    def _handle_fault(self, fault: FaultPacket) -> None:
        """Latch the stall fault state reported by the STM32.

        Args:
            fault: 파싱된 FAULT 패킷.
        """
        fault_state = _STALL_CAUSE_TO_FAULT[fault.cause]
        self.get_logger().error(
            f"STM Stall Fault: {fault.cause.value} -> {FAULT_TOPIC}={fault_state}. "
            "STM은 이 상태를 latch하므로 RESET_STALL 없이는 해제되지 않는다 "
            "(RESET_STALL 송신은 아직 구현되지 않았다)"
        )
        self._set_fault_state(fault_state)

    def _handle_line(self, line: str) -> None:
        """Parse one received line and dispatch by packet kind.

        Args:
            line: `LineDecoder`가 조립한 완성된 한 줄.
        """
        packet = parse_packet(line)
        kind = packet.kind

        if kind is PacketKind.STATUS and isinstance(packet.payload, StatusPacket):
            self._handle_status(packet.payload)
        elif kind is PacketKind.FAULT and isinstance(packet.payload, FaultPacket):
            self._handle_fault(packet.payload)
        elif kind is PacketKind.FAULT_CLEARED:
            self.get_logger().info(
                f"STM Stall Fault 해제됨 -> {FAULT_TOPIC}={FAULT_NONE}"
            )
            self._set_fault_state(FAULT_NONE)
        elif kind is PacketKind.PI_GAINS and isinstance(
            packet.payload, PiGainsPacket
        ):
            self.get_logger().info(
                f"STM PI gains applied: kp={packet.payload.kp} ki={packet.payload.ki}"
            )
        elif kind is PacketKind.STALL_RESET_ACK:
            # ACK는 "Fault가 해제됐다"는 뜻이 아니다. 해제는 FAULT_CLEARED로 통보되므로
            # 여기서 fault 상태를 NONE으로 바꾸지 않는다(프로토콜 정본 RESET_STALL 절).
            self.get_logger().info(
                "STM RESET_STALL 수락 — fault 해제는 FAULT_CLEARED로 별도 통보된다"
            )
        elif kind is PacketKind.ERROR:
            self.get_logger().warning(f"STM 오류 응답: {packet.raw}")
        elif kind is PacketKind.MALFORMED:
            self._malformed_count += 1
            self.get_logger().warning(
                f"손상된 수신 줄 #{self._malformed_count} "
                f"({packet.token}: {packet.reason}): {packet.raw!r}",
                throttle_duration_sec=CMD_VEL_LOG_THROTTLE_SEC,
            )
        elif kind is PacketKind.UNKNOWN:
            self.get_logger().debug(f"알 수 없는 수신 줄(무시): {packet.raw!r}")
        # BLANK는 조용히 무시한다(빈 줄은 오류가 아니다).

    def _update_connected_timeout(self) -> None:
        """Drop `/stm/connected` to false when STATUS has gone stale.

        경계값(정확히 `status_timeout_sec` 경과)에서도 false로 내린다 — 애매한 순간에는
        "데이터가 낡았다"고 보는 편이 안전하다. `command_watchdog`의 timeout 판정과
        같은 규칙이다.
        """
        if self._last_status_time_sec is None:
            return  # 아직 한 번도 받지 않았다 -> 이미 false
        elapsed_sec = self._now_sec() - self._last_status_time_sec
        if elapsed_sec >= self._status_timeout_sec:
            self._set_connected(False)

    def _rx_timer_callback(self) -> None:
        """Read available bytes, dispatch complete lines, then check the STATUS timeout.

        `rx_poll_hz` 주기로 호출된다. 읽을 데이터가 없어도(`b""`) timeout 검사는 반드시
        수행한다 — STM이 조용해지는 것이 바로 감지해야 할 상황이기 때문이다.
        """
        if self._serial_fatal_error:
            # 타이머는 취소했지만 취소 직전에 큐에 들어간 tick이 한 번 더 실행될 수 있다.
            return
        if self._serial_link is None:
            return  # dry_run에서는 RX 타이머를 만들지 않으므로 도달하지 않는다

        try:
            data = self._serial_link.read_available()
        except SerialLinkError as error:
            self._abort_on_serial_failure(error, direction="RX")
            return

        for line in self._decoder.feed(data):
            self._handle_line(line)

        self._update_connected_timeout()

    # ------------------------------------------------------------------
    # 치명적 Serial 오류
    # ------------------------------------------------------------------

    def _abort_on_serial_failure(
        self, error: SerialLinkError, *, direction: str
    ) -> None:
        """Latch a fatal serial failure and stop both timers. **종료는 하지 않는다.**

        Serial 오류를 경고만 남기고 계속 진행하면, 사용자는 명령이 STM에 가고(또는
        상태가 올라오고) 있다고 믿는데 실제로는 아무것도 오가지 않는 상태가 된다 —
        사람이 함께 있는 환경에서 가장 위험한 실패 방식이다. 따라서 즉시 멈춘다.

        TX/RX를 하나의 상태로 합친 이유: 포트가 고장 나면 방향과 무관하게 브리지 전체를
        멈춰야 한다. 두 타이머를 모두 취소하지 않으면 남은 쪽이 계속 실패한 포트를 두드린다.

        이 메서드는 **타이머 콜백 안에서 호출되므로** ROS context나 노드의 수명을
        직접 건드리지 않는다. `rclpy.shutdown()`/`destroy_node()`/`close_serial()`을
        여기서 호출하면 executor가 waitset을 돌고 있는 도중에 context가 파괴되어
        DDS 수신 스레드가 정리되지 못하고 프로세스가 남는다(2026-08-02 실측 확인).
        실제 종료 정리는 `main()`의 공통 경로가 담당한다.

        Args:
            error: 첫 실패 원인.
            direction: 실패한 방향(`TX`/`RX`). 로그 문구에만 쓴다.
        """
        if self._serial_fatal_error:
            return  # 이미 래치됨(중복 로그·중복 종료 요청 방지)
        self._serial_fatal_error = True
        self._requested_exit_code = EXIT_FAILURE

        for timer in (self._tx_timer, self._rx_timer):
            if timer is not None:
                timer.cancel()

        # 데이터가 더 이상 갱신되지 않으므로 연결이 끊긴 것으로 알린다.
        # fault 상태는 마지막 확인값을 그대로 유지한다(임의로 NONE으로 되돌리지 않는다).
        self._set_connected(False)

        self.get_logger().error(f"Serial {direction} failed: {error}")
        self.get_logger().error(
            "송수신을 중단하고 노드를 종료한다 (정리는 main의 공통 종료 경로에서 수행)"
        )

    def _tx_timer_callback(self) -> None:
        """Pick the command for this tick and hand it to the single send exit.

        `tx_rate_hz` 주기로 호출된다. `/cmd_vel` 도착과 무관하게 항상 돌기 때문에,
        상위가 멈춰도 `timed_out`으로 넘어가 0,0을 계속 내보낼 수 있다.
        """
        if self._serial_fatal_error:
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
            self._abort_on_serial_failure(error, direction="TX")


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
        while rclpy.ok() and not node.serial_fatal_error:
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
