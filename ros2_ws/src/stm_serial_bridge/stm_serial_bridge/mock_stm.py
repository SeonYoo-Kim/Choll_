"""STM32 대역 mock — PTY 한쪽을 잡고 STATUS 패킷을 주기적으로 내보낸다.

하드웨어 없이 `stm_serial_bridge` 노드의 수신 경로를 돌리기 위한 테스트 도구다.
실제 `/dev/ttyACM*`를 쓰지 않고 Linux PTY(`pty.openpty()`)만 사용한다.

동작:

1. PTY 쌍을 만들고 slave 경로(`/dev/pts/N`)에 대한 **symlink**를 고정 경로로 걸어 둔다.
   브리지는 이 고정 경로를 `serial_port`로 열면 되므로, 매번 바뀌는 `/dev/pts/N`을
   몰라도 된다.
2. master 쪽으로 STM32 펌웨어와 **같은 형식**의 STATUS 패킷을 주기적으로 쓴다.
3. 브리지가 보낸 `SET_WHEEL_VEL`을 읽어 target 으로 반영한다(버퍼가 차는 것도 막는다).

⚠️ 이것은 모터 모델이 아니다. `actual = target`을 그대로 돌려주는 **스텁**이며 관성·
   부하·제어기(PI)를 흉내내지 않는다. 따라서 mock 의 actual 값으로 제어 성능이나
   엔코더 스케일 정확도를 판단할 수 없다 — 검증 대상은 **경로와 형식**뿐이다.

⚠️ STM 펌웨어와 STATUS 패킷 형식은 이 파일에서 절대 바꾸지 않는다. 여기는 펌웨어를
   **모방**하는 쪽이므로, 형식이 어긋나면 펌웨어가 아니라 이 파일을 고쳐야 한다.

실행::

    # 무한히 STATUS 송신 (Ctrl+C 로 종료)
    ros2 run stm_serial_bridge mock_stm --link /tmp/stm_mock_pty

    # 3초 뒤 STATUS 송신을 멈춤 (connected=false 타임아웃 확인용, 포트는 계속 열려 있음)
    ros2 run stm_serial_bridge mock_stm --link /tmp/stm_mock_pty --stop-after-sec 3.0
"""

from __future__ import annotations

import argparse
import errno
import os
import pty
import signal
import sys
import time
from dataclasses import dataclass
from types import FrameType

# STM 펌웨어 `status_reporter.c`의 송신 주기(STATUS_REPORTER_INTERVAL_MS = 100u).
DEFAULT_STATUS_RATE_HZ = 10.0

# 바퀴 1회전당 엔코더 count — 펌웨어 `motor_config.h`의 **명목값**
# (MOTOR_ENCODER_CPR 380 × MOTOR_GEAR_RATIO 51 × QUADRATURE 4).
#
# ⚠️ 실측 평균은 명목값보다 약 12% 작다 — 2026-08-03 68162.5, 2026-08-08 68167
#    count/wheel-rev 로 두 차례 재현됐고, 그 원인은 아직 미확정이다.
#    ROS Wheel Odometry 는 실측 기준값 68160(`counts_per_wheel_rev` 파라미터)을 쓰지만
#    **이 mock 은 계속 명목값을 쓴다.** mock 이 흉내내는 대상은 odometry 가 아니라
#    "펌웨어가 믿고 있는 값"이기 때문이다. 펌웨어 상수가 바뀔 때만 이 값을 따라 바꾼다.
#    (형식만 검증하므로 이 숫자를 바꿔도 브리지 검증 결과 자체는 달라지지 않는다.)
DEFAULT_COUNTS_PER_WHEEL_REV = 380.0 * 51.0 * 4.0

# int32 래핑 — 펌웨어가 STATUS 에 `%ld`로 싣는 누적 count 의 자료형 범위.
_INT32_MIN = -2147483648
_INT32_MAX = 2147483647

# 명령 수신 버퍼 상한. 브리지는 한 줄이 40바이트 미만이므로 넉넉하다.
_COMMAND_BUFFER_LIMIT = 4096

_SET_WHEEL_VEL_PREFIX = "SET_WHEEL_VEL,"


def build_status_line(
    left_target_rad_s: float,
    left_actual_rad_s: float,
    right_target_rad_s: float,
    right_actual_rad_s: float,
    left_pwm: int,
    right_pwm: int,
    left_encoder_total: int,
    right_encoder_total: int,
) -> str:
    """STM32 펌웨어와 같은 형식의 STATUS 한 줄을 만든다.

    펌웨어 `status_reporter.c`의::

        snprintf(out, n, "STATUS,%s,%s,%s,%s,%d,%d,%ld,%ld\\r\\n", ...)

    를 그대로 따른다. 필드 순서는 **좌우 교차**(LT, LA, RT, RA)이며
    `target_L, target_R, actual_L, actual_R`이 아니다.

    Args:
        left_target_rad_s: 좌 목표 각속도 [rad/s].
        left_actual_rad_s: 좌 실측 각속도 [rad/s].
        right_target_rad_s: 우 목표 각속도 [rad/s].
        right_actual_rad_s: 우 실측 각속도 [rad/s].
        left_pwm: 좌 PWM (부호 = 방향).
        right_pwm: 우 PWM (부호 = 방향).
        left_encoder_total: 좌 누적 엔코더 count.
        right_encoder_total: 우 누적 엔코더 count.

    Returns:
        CRLF 로 끝나는 STATUS 한 줄.
    """
    return (
        f"STATUS,{left_target_rad_s:.2f},{left_actual_rad_s:.2f},"
        f"{right_target_rad_s:.2f},{right_actual_rad_s:.2f},"
        f"{int(left_pwm)},{int(right_pwm)},"
        f"{int(left_encoder_total)},{int(right_encoder_total)}\r\n"
    )


def wrap_int32(value: int) -> int:
    """int32 범위로 래핑한다 (펌웨어의 누적 count 오버플로 흉내).

    Args:
        value: 래핑할 값.

    Returns:
        `-2147483648..2147483647` 범위의 값.
    """
    span = _INT32_MAX - _INT32_MIN + 1
    return (value - _INT32_MIN) % span + _INT32_MIN


def advance_encoder(
    count: int,
    rad_s: float,
    dt_sec: float,
    counts_per_wheel_rev: float = DEFAULT_COUNTS_PER_WHEEL_REV,
) -> int:
    """각속도만큼 누적 엔코더 count 를 전진시킨다.

    Args:
        count: 현재 누적 count.
        rad_s: 바퀴 각속도 [rad/s]. 음수면 count 가 감소한다.
        dt_sec: 경과 시간 [초]. 0 이하면 변화 없음.
        counts_per_wheel_rev: 바퀴 1회전당 count.

    Returns:
        전진된 누적 count (int32 래핑 적용).

    Raises:
        ValueError: `counts_per_wheel_rev` 가 0 이하일 때.
    """
    if counts_per_wheel_rev <= 0.0:
        msg = f"counts_per_wheel_rev must be positive: {counts_per_wheel_rev}"
        raise ValueError(msg)
    if dt_sec <= 0.0:
        return wrap_int32(count)
    revolutions = (rad_s * dt_sec) / (2.0 * 3.141592653589793)
    return wrap_int32(count + int(revolutions * counts_per_wheel_rev))


def parse_set_wheel_vel(line: str) -> tuple[float, float] | None:
    """`SET_WHEEL_VEL,<left>,<right>` 한 줄에서 좌우 목표값을 뽑는다.

    브리지가 보낸 명령을 mock 이 target 으로 되비추기 위한 최소 파서다.
    브리지의 수신 파서(`packet_parser.py`)와는 방향이 반대이므로 별개다.

    Args:
        line: 개행이 제거된 한 줄.

    Returns:
        `(left_rad_s, right_rad_s)`. `SET_WHEEL_VEL` 이 아니거나 형식이
        어긋나면 `None`.
    """
    stripped = line.strip()
    if not stripped.startswith(_SET_WHEEL_VEL_PREFIX):
        return None
    payload = stripped[len(_SET_WHEEL_VEL_PREFIX) :]
    fields = payload.split(",")
    if len(fields) != 2:
        return None
    try:
        return (float(fields[0]), float(fields[1]))
    except ValueError:
        return None


@dataclass
class MockState:
    """mock STM 의 누적 상태."""

    left_target_rad_s: float = 0.0
    right_target_rad_s: float = 0.0
    left_encoder_total: int = 0
    right_encoder_total: int = 0


class _PtyEndpoint:
    """PTY 쌍 + 고정 경로 symlink 를 관리한다."""

    def __init__(self, link_path: str) -> None:
        """PTY 를 열고 `link_path` symlink 를 만든다.

        Args:
            link_path: 브리지가 열게 될 고정 경로.

        Raises:
            OSError: PTY 생성 또는 symlink 생성이 실패했을 때.
        """
        self._link_path = link_path
        self._master_fd, self._slave_fd = pty.openpty()
        os.set_blocking(self._master_fd, False)
        self._slave_name = os.ttyname(self._slave_fd)
        self._create_symlink()

    def _create_symlink(self) -> None:
        """기존 symlink 를 치우고 새로 만든다."""
        if os.path.islink(self._link_path):
            os.unlink(self._link_path)
        os.symlink(self._slave_name, self._link_path)

    @property
    def link_path(self) -> str:
        """브리지가 `serial_port` 로 쓸 고정 경로."""
        return self._link_path

    @property
    def slave_name(self) -> str:
        """실제 PTY slave 경로 (`/dev/pts/N`)."""
        return self._slave_name

    def write(self, text: str) -> None:
        """master 쪽으로 ASCII 를 쓴다. 버퍼가 차 있으면 조용히 넘긴다."""
        try:
            os.write(self._master_fd, text.encode("ascii"))
        except OSError as error:
            if error.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                raise

    def read(self) -> str:
        """master 쪽에 도착한 것을 모두 읽는다. 없으면 빈 문자열."""
        try:
            data = os.read(self._master_fd, _COMMAND_BUFFER_LIMIT)
        except OSError as error:
            if error.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                return ""
            raise
        return data.decode("ascii", errors="replace")

    def close(self) -> None:
        """fd 와 symlink 를 정리한다. 실패는 무시한다(종료 경로이므로)."""
        for file_descriptor in (self._slave_fd, self._master_fd):
            try:
                os.close(file_descriptor)
            except OSError:
                pass
        try:
            if os.path.islink(self._link_path):
                os.unlink(self._link_path)
        except OSError:
            pass


_stop_requested = False


def _request_stop(signum: int, frame: FrameType | None) -> None:  # noqa: ARG001
    """SIGINT/SIGTERM 을 받으면 루프를 정상 종료시킨다."""
    global _stop_requested  # noqa: PLW0603
    _stop_requested = True


def _build_arg_parser() -> argparse.ArgumentParser:
    """CLI 파서를 만든다."""
    parser = argparse.ArgumentParser(
        description="STM32 대역 mock — PTY 로 STATUS 패킷을 내보낸다.",
    )
    parser.add_argument(
        "--link",
        default="/tmp/stm_serial_bridge_mock_pty",  # noqa: S108
        help="브리지가 serial_port 로 열 고정 경로 (PTY slave 로의 symlink)",
    )
    parser.add_argument(
        "--rate-hz",
        type=float,
        default=DEFAULT_STATUS_RATE_HZ,
        help=f"STATUS 송신 주기 [Hz] (기본 {DEFAULT_STATUS_RATE_HZ} = 펌웨어와 동일)",
    )
    parser.add_argument(
        "--stop-after-sec",
        type=float,
        default=0.0,
        help=(
            "이 시간이 지나면 STATUS 송신만 멈춘다(포트는 열린 채 유지). "
            "connected=false 타임아웃 확인용. 0 이면 멈추지 않는다."
        ),
    )
    parser.add_argument(
        "--duration-sec",
        type=float,
        default=0.0,
        help="이 시간이 지나면 프로세스를 종료한다. 0 이면 무한.",
    )
    parser.add_argument(
        "--fault-after-sec",
        type=float,
        default=0.0,
        help=(
            "이 시간이 지난 뒤 `FAULT,STALL,LEFT` 를 한 번 보낸다. "
            "0 이면 보내지 않는다."
        ),
    )
    parser.add_argument(
        "--counts-per-wheel-rev",
        type=float,
        default=DEFAULT_COUNTS_PER_WHEEL_REV,
        help=(
            "바퀴 1회전당 엔코더 count "
            f"(기본 {DEFAULT_COUNTS_PER_WHEEL_REV:.0f} = 펌웨어 명목값)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """mock STM 을 실행한다.

    Args:
        argv: CLI 인자. `None` 이면 `sys.argv[1:]`.

    Returns:
        프로세스 종료 코드. 정상 종료 0, 인자·PTY 오류 1.
    """
    args = _build_arg_parser().parse_args(argv)

    if args.rate_hz <= 0.0:
        print(f"[mock_stm] --rate-hz must be positive: {args.rate_hz}", file=sys.stderr)
        return 1
    if args.counts_per_wheel_rev <= 0.0:
        print(
            "[mock_stm] --counts-per-wheel-rev must be positive: "
            f"{args.counts_per_wheel_rev}",
            file=sys.stderr,
        )
        return 1

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    try:
        endpoint = _PtyEndpoint(args.link)
    except OSError as error:
        print(f"[mock_stm] failed to create PTY at {args.link}: {error}", file=sys.stderr)
        return 1

    print(f"[mock_stm] PTY  : {endpoint.slave_name}", flush=True)
    print(f"[mock_stm] link : {endpoint.link_path}", flush=True)
    print(f"[mock_stm] rate : {args.rate_hz} Hz", flush=True)
    if args.stop_after_sec > 0.0:
        print(
            f"[mock_stm] STATUS 를 {args.stop_after_sec}s 뒤 중단한다 "
            "(connected=false 확인용)",
            flush=True,
        )

    state = MockState()
    period_sec = 1.0 / args.rate_hz
    started_at = time.monotonic()
    last_tick = started_at
    pending = ""
    status_stopped = False
    fault_sent = False

    try:
        while not _stop_requested:
            now = time.monotonic()
            elapsed = now - started_at

            if args.duration_sec > 0.0 and elapsed >= args.duration_sec:
                break

            pending += endpoint.read()
            while "\n" in pending:
                line, _, pending = pending.partition("\n")
                targets = parse_set_wheel_vel(line)
                if targets is not None:
                    state.left_target_rad_s, state.right_target_rad_s = targets
            if len(pending) > _COMMAND_BUFFER_LIMIT:
                pending = ""

            if args.stop_after_sec > 0.0 and elapsed >= args.stop_after_sec:
                if not status_stopped:
                    print("[mock_stm] STATUS 송신 중단", flush=True)
                    status_stopped = True
            elif now - last_tick >= period_sec:
                dt_sec = now - last_tick
                last_tick = now
                # 스텁: actual = target (모터 모델 아님)
                state.left_encoder_total = advance_encoder(
                    state.left_encoder_total,
                    state.left_target_rad_s,
                    dt_sec,
                    args.counts_per_wheel_rev,
                )
                state.right_encoder_total = advance_encoder(
                    state.right_encoder_total,
                    state.right_target_rad_s,
                    dt_sec,
                    args.counts_per_wheel_rev,
                )
                endpoint.write(
                    build_status_line(
                        state.left_target_rad_s,
                        state.left_target_rad_s,
                        state.right_target_rad_s,
                        state.right_target_rad_s,
                        0,
                        0,
                        state.left_encoder_total,
                        state.right_encoder_total,
                    )
                )

            if (
                args.fault_after_sec > 0.0
                and not fault_sent
                and elapsed >= args.fault_after_sec
            ):
                endpoint.write("FAULT,STALL,LEFT\r\n")
                fault_sent = True
                print("[mock_stm] FAULT,STALL,LEFT 송신", flush=True)

            time.sleep(0.005)
    finally:
        endpoint.close()
        print("[mock_stm] 종료", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
