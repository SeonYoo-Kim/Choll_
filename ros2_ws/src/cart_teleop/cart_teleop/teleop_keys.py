"""키보드 수동 주행의 판정 로직 — ROS·터미널에 의존하지 않는 순수 모듈.

`rclpy`·`termios`·`tty`·`select`·pyserial·ROS 메시지 타입을 **import하지 않는다.**
시각도 인자로 받으므로 `time.monotonic()`을 호출하지 않는다 — 덕분에 특정 시각을
만들어 넣어 lease 경계를 결정적으로 테스트할 수 있다
(`stm_serial_bridge`의 `command_watchdog`과 같은 계약 형태).

## command lease 방식 (latch 아님)

터미널은 **키 릴리즈를 감지할 수 없다.** raw/cbreak 모드에서 얻는 것은 키 *누름*
문자뿐이고, 키를 누르고 있으면 OS 자동반복이 같은 문자를 반복 전달한다.

그래서 "키를 놓으면 정지"를 다음으로 구현한다:

- W/S/A/D 입력마다 **명령 유효시간(lease)** 을 `input_timeout_sec`만큼 갱신한다.
- 키를 계속 누르고 있으면 자동반복이 lease를 계속 갱신해 주행이 이어진다.
- 손을 떼면 자동반복이 끊기고, `input_timeout_sec`이 지나면 **zero로 전환**한다.
- lease가 만료되면 현재 동작을 **버린다** — 그래서 다시 움직이려면 새 키가 필요하다.

⚠️ 자동반복에는 초기 지연(전형적으로 약 0.5초)이 있다. `input_timeout_sec`을 그보다
   짧게 잡으면 "움직임 → 정지 → 움직임" 끊김이 생긴다. 기본값 1.0초는 그 지연보다
   충분히 크게 잡은 값이다.

## 안전 표현에 대한 주의

`Space`는 **정지 명령(zero Twist)** 이다. **ESTOP이 아니다.** 현재 Serial Bridge에는
STM `ESTOP`/`STOP` 명령 송신 인터페이스가 없고, 이 모듈이 만드는 것은 `/cmd_vel`에
실릴 0 값일 뿐이다. 실제 비상정지는 물리 전원 차단이 필요하다.
"""

import math
from dataclasses import dataclass
from enum import Enum

# ── 키 정의 ────────────────────────────────────────────────────────────────
KEY_FORWARD = "w"
KEY_BACKWARD = "s"
KEY_TURN_LEFT = "a"
KEY_TURN_RIGHT = "d"
KEY_STOP = " "
KEY_SPEED_UP = "+"
# `+` 는 대부분의 배열에서 Shift 가 필요해 주행 중 조작이 번거롭다. 같은 물리 키의
# Shift 없는 문자인 `=` 를 별칭으로 받아들인다 (동작은 `+` 와 완전히 동일).
KEY_SPEED_UP_ALIAS = "="
KEY_SPEED_DOWN = "-"
KEY_QUIT = "q"
KEY_ESCAPE = "\x1b"

# 속도 단계를 올리는 키 전체. `handle_key()` 는 이 집합으로 판정한다.
SPEED_UP_KEYS: frozenset[str] = frozenset({KEY_SPEED_UP, KEY_SPEED_UP_ALIAS})

# W/S/A/D — lease를 갱신하는 주행 키. 값은 (선속도 배율, 각속도 배율).
# 선속도와 각속도를 **동시에 섞지 않는다**: 직진/후진은 각속도 0, 제자리 회전은
# 선속도 0. 곡선 주행이 필요하면 Nav2 경로로 전환하는 것이 이 도구의 설계 의도다.
#
# 부호는 REP 103을 따른다 — `angular.z > 0`이 반시계(좌회전)다.
MOTION_KEYS: dict[str, tuple[float, float]] = {
    KEY_FORWARD: (1.0, 0.0),
    KEY_BACKWARD: (-1.0, 0.0),
    KEY_TURN_LEFT: (0.0, 1.0),
    KEY_TURN_RIGHT: (0.0, -1.0),
}

# 키 -> 화면에 표시할 라벨.
KEY_LABELS: dict[str, str] = {
    KEY_FORWARD: "W 전진",
    KEY_BACKWARD: "S 후진",
    KEY_TURN_LEFT: "A 제자리 좌회전",
    KEY_TURN_RIGHT: "D 제자리 우회전",
    KEY_STOP: "Space 정지",
    KEY_SPEED_UP: "+ 속도 단계 증가",
    KEY_SPEED_UP_ALIAS: "= 속도 단계 증가 (+ 별칭)",
    KEY_SPEED_DOWN: "- 속도 단계 감소",
    KEY_QUIT: "q 종료",
    KEY_ESCAPE: "Esc 종료",
}

# ── 기본값 ─────────────────────────────────────────────────────────────────
# 2026-08-08 실기 재배분: **전진은 절반으로, 회전은 2.5배로.**
# 사용자 실기 판단 — 전진 파워는 남고(절반이어도 충분) 회전이 너무 느렸다.
#
# 🔴 2026-08-09 후속 조정: 회전 1.50 -> **0.90** (직전 값의 60%).
#    1.50 은 실기에서 **너무 빨라 90도에서 멈추는 각을 맞추기 어려웠다.**
#    0.90 이면 90도 선회가 약 1.75초((pi/2)/0.9)로 늘어 키를 떼는 타이밍을
#    잡을 수 있다. 전진 0.26 은 손대지 않는다.
#
# 회전이 유독 느린 이유: 제자리 회전에서 바퀴가 내야 하는 각속도는
#   바퀴 rad/s = w * L / (2r) = w * 0.38 / 0.13 = w * 2.923
# 이라 같은 바퀴 속도로도 차체 각속도는 2.923 로 나눠진다. 여기에 제자리 회전은
# 타이어가 지면에서 비틀리는 스크럽 마찰까지 겹쳐 더 느려진다.
#
#   linear  0.26 m/s   = 바퀴 4.00 rad/s   (이전 0.13 -> 명령 경로 r=0.065 기준)
#   angular 0.90 rad/s = 바퀴 2.63 rad/s = PWM 약 26 — 실측 데드존(공중 20 /
#                                           바닥 10~12) 위라 회전은 확실히 시작된다
#                                           (0.60 = 바퀴 1.754 = PWM 17.5 는 데드존
#                                            언저리라 회전이 거의 시작되지 않았다)
#   전진+회전 동시(최악) = 6.63 rad/s
#
# 🔴 **`speed_profile:=slow`(max_wheel_rad_s 2.0)로는 이 값을 낼 수 없다.**
#    `limit_wheel_rad_s()`가 좌우 비율을 유지한 채 비례 축소하므로 조용히 깎인다
#    (예: w=0.9 요청 -> 바퀴 2.63 필요 -> 2.0 으로 축소 -> 실제 w 0.68 = 요청의 76%).
#    브리지를 **`max_wheel_rad_s:=6.7` 이상**으로 띄울 것. 6.7 은 복합 최악 6.63 을
#    무축소로 수용하는 최소값이다. 현재 실기에서 쓰는 8.5 는 그대로 둬도 되며
#    (펌웨어 하드웨어 최대 9.9 rad/s 안), 여유만 커진다.
#    (이전 주석은 "slow 상한 이내"를 전제로 값을 골랐다 — 그 전제는 이제 깨졌다.)
#
# 최종 상한 방어선은 여전히 이 모듈이 아니라 Bridge 의 `max_wheel_rad_s` 다.
DEFAULT_MAX_LINEAR_MPS = 0.26
DEFAULT_MAX_ANGULAR_RPS = 0.90
DEFAULT_INPUT_TIMEOUT_SEC = 1.0
DEFAULT_SPEED_STEP_COUNT = 5


class TeleopStatus(Enum):
    """현재 발행 상태. UI 표시와 테스트 판정에 함께 쓴다."""

    ARMED = "ARMED"
    """lease가 유효해 non-zero 명령을 발행하는 중."""

    STOPPED = "STOPPED"
    """아직 주행 키가 없거나 Space로 정지했다. zero 발행."""

    TIMEOUT = "TIMEOUT"
    """lease가 만료되어 zero로 전환했다. 다시 움직이려면 새 키가 필요하다."""

    DISARMED = "DISARMED"
    """외부 `/cmd_vel` Publisher가 감지되어 non-zero 발행을 차단했다."""

    QUIT = "QUIT"
    """종료 요청. zero를 발행하고 루프를 벗어난다."""


@dataclass(frozen=True)
class TeleopCommand:
    """한 tick에 발행할 명령과 화면에 표시할 정보.

    Attributes:
        linear_x: 발행할 선속도 (m/s).
        angular_z: 발행할 각속도 (rad/s). REP 103 — 양수가 반시계.
        status: 현재 상태.
        speed_step: 현재 속도 단계 (1..step_count).
        speed_step_count: 전체 단계 수.
        last_key_label: 마지막으로 처리한 키의 표시 라벨. 없으면 빈 문자열.
        lease_remaining_sec: lease 남은 시간(초). 유효한 lease가 없으면 None.
        external_publisher_count: 감지된 외부 `/cmd_vel` Publisher 수.
    """

    linear_x: float
    angular_z: float
    status: TeleopStatus
    speed_step: int
    speed_step_count: int
    last_key_label: str
    lease_remaining_sec: float | None
    external_publisher_count: int

    @property
    def is_zero(self) -> bool:
        """발행값이 정확히 0인지."""
        return self.linear_x == 0.0 and self.angular_z == 0.0


def _require_positive_finite(name: str, value: float) -> None:
    """양수 유한값인지 검사한다.

    Args:
        name: 오류 메시지에 넣을 파라미터 이름.
        value: 검사할 값.

    Raises:
        ValueError: 유한하지 않거나 0 이하일 때.
    """
    if not math.isfinite(value):
        msg = f"{name} must be finite, got {value}"
        raise ValueError(msg)
    if value <= 0.0:
        msg = f"{name} must be greater than 0.0, got {value}"
        raise ValueError(msg)


class TeleopState:
    """키 입력과 시각으로부터 발행할 명령을 결정하는 상태 기계.

    ROS·터미널 무의존. 시각은 항상 인자로 받는다.

    상태 전이 요약::

        (시작)            -> STOPPED
        W/S/A/D           -> ARMED, lease 갱신
        Space             -> STOPPED, 동작 폐기
        lease 만료        -> TIMEOUT, 동작 폐기 (새 키 필요)
        외부 Publisher 감지 -> DISARMED, 동작 폐기 (해제 후에도 새 키 필요)
        q / Esc           -> QUIT
    """

    def __init__(
        self,
        *,
        max_linear_mps: float = DEFAULT_MAX_LINEAR_MPS,
        max_angular_rps: float = DEFAULT_MAX_ANGULAR_RPS,
        input_timeout_sec: float = DEFAULT_INPUT_TIMEOUT_SEC,
        speed_step_count: int = DEFAULT_SPEED_STEP_COUNT,
    ) -> None:
        """상태를 초기화한다. 속도 단계는 **최대 단계에서 시작**한다.

        Args:
            max_linear_mps: 선속도 상한 (m/s). 최대 단계에서의 값이다.
            max_angular_rps: 각속도 상한 (rad/s). 최대 단계에서의 값이다.
            input_timeout_sec: command lease 유효시간 (초).
            speed_step_count: 속도 단계 수. 1 이상.

        Raises:
            ValueError: 속도·timeout이 0 이하/비유한이거나 `speed_step_count`가
                1 미만일 때.
        """
        _require_positive_finite("max_linear_mps", max_linear_mps)
        _require_positive_finite("max_angular_rps", max_angular_rps)
        _require_positive_finite("input_timeout_sec", input_timeout_sec)
        if speed_step_count < 1:
            msg = f"speed_step_count must be at least 1, got {speed_step_count}"
            raise ValueError(msg)

        self._max_linear_mps = max_linear_mps
        self._max_angular_rps = max_angular_rps
        self._input_timeout_sec = input_timeout_sec
        self._speed_step_count = speed_step_count

        # 기본값은 최대 단계 — 요구된 기본 속도(0.26 / 0.90)가 곧 상한값이다.
        self._speed_step = speed_step_count

        self._motion_key: str | None = None
        self._lease_start_sec: float | None = None
        self._last_key_label = ""
        self._quit_requested = False
        self._external_publisher_count = 0

    # ── 조회 ───────────────────────────────────────────────────────────────

    @property
    def input_timeout_sec(self) -> float:
        """command lease 유효시간 (초)."""
        return self._input_timeout_sec

    @property
    def speed_step(self) -> int:
        """현재 속도 단계 (1..speed_step_count)."""
        return self._speed_step

    @property
    def speed_step_count(self) -> int:
        """전체 속도 단계 수."""
        return self._speed_step_count

    @property
    def quit_requested(self) -> bool:
        """`q`/`Esc`로 종료가 요청됐는지."""
        return self._quit_requested

    @property
    def external_publisher_count(self) -> int:
        """감지된 외부 `/cmd_vel` Publisher 수."""
        return self._external_publisher_count

    @property
    def disarmed(self) -> bool:
        """외부 Publisher 충돌로 non-zero 발행이 차단된 상태인지."""
        return self._external_publisher_count > 0

    def speed_scale(self) -> float:
        """현재 단계의 배율 (0 초과 1 이하)."""
        return self._speed_step / self._speed_step_count

    # ── 입력 ───────────────────────────────────────────────────────────────

    def handle_key(self, key: str, now_sec: float) -> None:
        """키 하나를 처리한다.

        주행 키(W/S/A/D)만 lease를 갱신한다. 속도 단계 키는 lease를 갱신하지
        않는다 — "주행 의도 표시"는 방향 키에만 부여한다.

        **DISARMED 상태에서는 주행 키를 받아들이지 않는다.** 외부 Publisher가
        있는 동안 움직이려는 의도를 저장해 두면, 충돌이 해제되는 순간 사용자가
        누르지도 않은 명령으로 갑자기 출발할 수 있기 때문이다.

        알 수 없는 키는 아무 상태도 바꾸지 않는다(마지막 키 라벨도 유지).

        Args:
            key: 입력 문자 한 글자. 대소문자를 구분하지 않는다.
            now_sec: 현재 시각(초). 단조 증가 시계 기준.

        Raises:
            ValueError: `now_sec`가 유한하지 않을 때.
        """
        if not math.isfinite(now_sec):
            msg = f"now_sec must be finite, got {now_sec}"
            raise ValueError(msg)

        # Space와 Esc는 대소문자 개념이 없고, 문자 키만 정규화한다.
        normalized = key.lower() if len(key) == 1 else key

        if normalized in (KEY_QUIT, KEY_ESCAPE):
            self._quit_requested = True
            self._motion_key = None
            self._lease_start_sec = None
            self._last_key_label = KEY_LABELS[normalized]
            return

        if normalized == KEY_STOP:
            self._motion_key = None
            self._lease_start_sec = None
            self._last_key_label = KEY_LABELS[KEY_STOP]
            return

        if normalized in SPEED_UP_KEYS:
            self._speed_step = min(self._speed_step + 1, self._speed_step_count)
            self._last_key_label = KEY_LABELS[normalized]
            return

        if normalized == KEY_SPEED_DOWN:
            self._speed_step = max(self._speed_step - 1, 1)
            self._last_key_label = KEY_LABELS[KEY_SPEED_DOWN]
            return

        if normalized in MOTION_KEYS:
            self._last_key_label = KEY_LABELS[normalized]
            if self.disarmed:
                # 충돌 중에는 의도를 저장하지 않는다 (해제 시 갑작스러운 출발 방지).
                return
            self._motion_key = normalized
            self._lease_start_sec = now_sec
            return

        # 알 수 없는 키 — 상태를 바꾸지 않는다.

    def set_external_publisher_count(self, count: int) -> None:
        """외부 `/cmd_vel` Publisher 수를 갱신한다.

        0보다 크면 즉시 현재 동작을 폐기한다. 이후 수가 0으로 돌아와도
        **자동으로 재가동하지 않는다** — 동작이 비워졌으므로 사용자가 새
        W/S/A/D를 눌러야 다시 움직인다.

        Args:
            count: 감지된 외부 Publisher 수. 음수는 0으로 취급한다.
        """
        self._external_publisher_count = max(0, count)
        if self._external_publisher_count > 0:
            self._motion_key = None
            self._lease_start_sec = None

    def request_quit(self) -> None:
        """외부 신호(SIGINT 등)로 종료를 요청한다."""
        self._quit_requested = True
        self._motion_key = None
        self._lease_start_sec = None

    # ── 판정 ───────────────────────────────────────────────────────────────

    def evaluate(self, now_sec: float) -> TeleopCommand:
        """이 tick에 발행할 명령을 결정한다.

        판정 순서 (앞선 조건이 이긴다):

        1. 종료 요청 -> `QUIT`, zero
        2. 외부 Publisher 존재 -> `DISARMED`, zero
        3. 활성 동작 없음 -> `STOPPED`, zero
        4. 경과 >= `input_timeout_sec` (**경계값 포함**) -> `TIMEOUT`, zero,
           동작 폐기
        5. 그 외 -> `ARMED`, 현재 단계의 속도

        경계값을 `TIMEOUT`으로 두는 것은 의도적이다 — 애매한 순간에는 정지를
        택한다(`command_watchdog.select_wheel_command()`와 같은 규칙).

        Args:
            now_sec: 현재 시각(초). 단조 증가 시계 기준.

        Returns:
            발행할 명령과 표시 정보.

        Raises:
            ValueError: `now_sec`가 유한하지 않을 때.
        """
        if not math.isfinite(now_sec):
            msg = f"now_sec must be finite, got {now_sec}"
            raise ValueError(msg)

        if self._quit_requested:
            return self._zero_command(TeleopStatus.QUIT, lease_remaining_sec=None)

        if self.disarmed:
            return self._zero_command(TeleopStatus.DISARMED, lease_remaining_sec=None)

        if self._motion_key is None or self._lease_start_sec is None:
            return self._zero_command(TeleopStatus.STOPPED, lease_remaining_sec=None)

        elapsed_sec = now_sec - self._lease_start_sec
        if elapsed_sec >= self._input_timeout_sec:
            self._motion_key = None
            self._lease_start_sec = None
            return self._zero_command(TeleopStatus.TIMEOUT, lease_remaining_sec=None)

        linear_ratio, angular_ratio = MOTION_KEYS[self._motion_key]
        scale = self.speed_scale()
        return TeleopCommand(
            linear_x=linear_ratio * self._max_linear_mps * scale,
            angular_z=angular_ratio * self._max_angular_rps * scale,
            status=TeleopStatus.ARMED,
            speed_step=self._speed_step,
            speed_step_count=self._speed_step_count,
            last_key_label=self._last_key_label,
            lease_remaining_sec=self._input_timeout_sec - elapsed_sec,
            external_publisher_count=self._external_publisher_count,
        )

    def _zero_command(
        self,
        status: TeleopStatus,
        *,
        lease_remaining_sec: float | None,
    ) -> TeleopCommand:
        """zero Twist 명령을 만든다.

        Args:
            status: 표시할 상태.
            lease_remaining_sec: 남은 lease. 정지 상태에서는 None.

        Returns:
            선속도·각속도가 0인 명령.
        """
        return TeleopCommand(
            linear_x=0.0,
            angular_z=0.0,
            status=status,
            speed_step=self._speed_step,
            speed_step_count=self._speed_step_count,
            last_key_label=self._last_key_label,
            lease_remaining_sec=lease_remaining_sec,
            external_publisher_count=self._external_publisher_count,
        )
