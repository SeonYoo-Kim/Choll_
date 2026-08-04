"""`/stm/*` 토픽 발행을 자동 검증한다 — 사람이 `ros2 topic echo` 를 눈으로 읽는 대신.

브리지가 이미 돌고 있는 상태에서 실행한다. 6개 상태 토픽을 구독해 정해진 시간 안에
기대한 값이 오는지 확인하고, 결과 표를 찍고 **종료 코드로 합격/불합격을 알린다**
(합격 0, 불합격 1). CI 나 스크립트에서 쓸 수 있게 하려는 것이 목적이다.

두 가지 모드가 있다:

- **기본(연결 확인)**: `connected=true` + 4개 데이터 토픽 수신 + `fault` 수신을 요구한다.
- `--expect-disconnect`: `connected=true` 를 본 뒤 **`false` 로 떨어지는 것**까지 요구한다.
  STATUS 가 끊겼을 때 `status_timeout_sec` 이 동작하는지 하드웨어 없이 확인하는 용도다.

⚠️ 이 도구는 **경로와 형식**만 본다. `wheel_actual_rad_s` 의 **수치 정확도**는 검증하지
   않는다 (엔코더 스케일 12.1% 미확정 문제는 실기 측정으로만 판정 가능하다).

실행::

    # 브리지가 mock/하드웨어 어느 쪽으로 떠 있어도 동일
    ros2 run stm_serial_bridge check_stm_topics --timeout-sec 10

    # STATUS 중단 → connected=false 확인 (mock_stm --stop-after-sec 와 함께)
    ros2 run stm_serial_bridge check_stm_topics --expect-disconnect --timeout-sec 15
"""

from __future__ import annotations

import argparse
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import (
    Bool,
    Float32MultiArray,
    Int16MultiArray,
    Int32MultiArray,
    String,
)

from stm_serial_bridge.stm_serial_bridge_node import (
    CONNECTED_TOPIC,
    ENCODER_TOTAL_TOPIC,
    FAULT_TOPIC,
    PWM_TOPIC,
    STATUS_DATA_QOS_DEPTH,
    WHEEL_ACTUAL_TOPIC,
    WHEEL_TARGET_TOPIC,
)

# 상태 토픽(connected/fault)의 QoS — 노드 쪽과 반드시 맞아야 구독이 성립한다.
_STATE_QOS = QoSProfile(
    depth=1,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
)

# 데이터 토픽은 좌우 2개 원소로 온다.
_EXPECTED_ARRAY_LEN = 2

_POLL_TIMEOUT_SEC = 0.05


class _TopicChecker(Node):
    """`/stm/*` 수신 결과를 모으는 노드."""

    def __init__(self) -> None:
        """구독을 걸고 카운터를 초기화한다."""
        super().__init__("stm_topic_checker")

        self.counts: dict[str, int] = {
            WHEEL_TARGET_TOPIC: 0,
            WHEEL_ACTUAL_TOPIC: 0,
            PWM_TOPIC: 0,
            ENCODER_TOTAL_TOPIC: 0,
            CONNECTED_TOPIC: 0,
            FAULT_TOPIC: 0,
        }
        self.last_values: dict[str, object] = {}
        self.bad_lengths: list[str] = []
        self.saw_connected_true = False
        self.saw_connected_false_after_true = False

        self.create_subscription(
            Float32MultiArray,
            WHEEL_TARGET_TOPIC,
            lambda msg: self._on_array(WHEEL_TARGET_TOPIC, msg),
            STATUS_DATA_QOS_DEPTH,
        )
        self.create_subscription(
            Float32MultiArray,
            WHEEL_ACTUAL_TOPIC,
            lambda msg: self._on_array(WHEEL_ACTUAL_TOPIC, msg),
            STATUS_DATA_QOS_DEPTH,
        )
        self.create_subscription(
            Int16MultiArray,
            PWM_TOPIC,
            lambda msg: self._on_array(PWM_TOPIC, msg),
            STATUS_DATA_QOS_DEPTH,
        )
        self.create_subscription(
            Int32MultiArray,
            ENCODER_TOTAL_TOPIC,
            lambda msg: self._on_array(ENCODER_TOTAL_TOPIC, msg),
            STATUS_DATA_QOS_DEPTH,
        )
        self.create_subscription(
            Bool,
            CONNECTED_TOPIC,
            self._on_connected,
            _STATE_QOS,
        )
        self.create_subscription(
            String,
            FAULT_TOPIC,
            self._on_fault,
            _STATE_QOS,
        )

    def _on_array(self, topic: str, msg: object) -> None:
        """배열 토픽 수신 — 원소 수가 2인지도 함께 본다."""
        data = list(msg.data)  # type: ignore[attr-defined]
        self.counts[topic] += 1
        self.last_values[topic] = data
        if len(data) != _EXPECTED_ARRAY_LEN and topic not in self.bad_lengths:
            self.bad_lengths.append(topic)

    def _on_connected(self, msg: Bool) -> None:
        """connected 수신 — true→false 전이를 기록한다."""
        self.counts[CONNECTED_TOPIC] += 1
        self.last_values[CONNECTED_TOPIC] = msg.data
        if msg.data:
            self.saw_connected_true = True
        elif self.saw_connected_true:
            self.saw_connected_false_after_true = True

    def _on_fault(self, msg: String) -> None:
        """fault 수신."""
        self.counts[FAULT_TOPIC] += 1
        self.last_values[FAULT_TOPIC] = msg.data


def _all_topics_seen(checker: _TopicChecker) -> bool:
    """6개 토픽이 모두 최소 1번 왔는지."""
    return all(count > 0 for count in checker.counts.values())


def _goal_reached(checker: _TopicChecker, *, expect_disconnect: bool) -> bool:
    """현재 상태가 종료 조건을 만족하는지."""
    if not _all_topics_seen(checker):
        return False
    if expect_disconnect:
        return checker.saw_connected_false_after_true
    return checker.saw_connected_true


def _print_report(checker: _TopicChecker, *, expect_disconnect: bool) -> bool:
    """결과 표를 찍고 합격 여부를 돌려준다.

    Args:
        checker: 수신 결과를 담은 노드.
        expect_disconnect: `connected=false` 전이까지 요구하는지.

    Returns:
        합격이면 `True`.
    """
    print("")
    print("=" * 72)
    print("  /stm/* 토픽 검증 결과")
    print("=" * 72)
    print(f"  {'토픽':<30} {'수신':>6}  {'마지막 값':<24}")
    print("  " + "-" * 68)

    for topic, count in checker.counts.items():
        value = checker.last_values.get(topic, "-")
        mark = "OK " if count > 0 else "MISS"
        print(f"  {mark} {topic:<26} {count:>6}  {value!s:<24}")

    print("  " + "-" * 68)

    failures: list[str] = []
    missing = [topic for topic, count in checker.counts.items() if count == 0]
    if missing:
        failures.append(f"수신되지 않은 토픽: {', '.join(missing)}")
    if checker.bad_lengths:
        failures.append(
            f"원소 수가 2가 아닌 토픽: {', '.join(checker.bad_lengths)}",
        )
    if not checker.saw_connected_true:
        failures.append("connected=true 를 한 번도 보지 못했다")
    if expect_disconnect and not checker.saw_connected_false_after_true:
        failures.append("connected 가 true → false 로 떨어지지 않았다 (timeout 미동작)")

    if expect_disconnect:
        print("  모드: STATUS 중단 → connected=false 확인")
    else:
        print("  모드: 연결 및 전체 토픽 발행 확인")

    if failures:
        print("")
        for failure in failures:
            print(f"  FAIL  {failure}")
        print("")
        print("  결과: ❌ 불합격")
        print("=" * 72)
        return False

    print("")
    print("  결과: ✅ 합격")
    print("  ⚠️ 단, 이 검증은 경로·형식만 본다. wheel_actual_rad_s 의 수치 정확도는")
    print("     검증 대상이 아니다 (엔코더 스케일은 실기 측정으로만 판정 가능).")
    print("=" * 72)
    return True


def _build_arg_parser() -> argparse.ArgumentParser:
    """CLI 파서를 만든다."""
    parser = argparse.ArgumentParser(
        description="/stm/* 토픽 발행을 자동 검증한다.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=10.0,
        help="이 시간 안에 조건을 만족하지 못하면 불합격 (기본 10초)",
    )
    parser.add_argument(
        "--expect-disconnect",
        action="store_true",
        help="connected 가 true 를 거쳐 false 로 떨어지는 것까지 요구한다",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """검증을 실행한다.

    Args:
        argv: CLI 인자. `None` 이면 `sys.argv[1:]`.

    Returns:
        합격 0, 불합격 1.
    """
    args = _build_arg_parser().parse_args(argv)
    if args.timeout_sec <= 0.0:
        print(
            f"[check_stm_topics] --timeout-sec must be positive: {args.timeout_sec}",
            file=sys.stderr,
        )
        return 1

    rclpy.init()
    checker = _TopicChecker()
    deadline = time.monotonic() + args.timeout_sec
    passed = False

    try:
        print(
            f"[check_stm_topics] 최대 {args.timeout_sec}s 동안 /stm/* 수신을 기다린다...",
            flush=True,
        )
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(checker, timeout_sec=_POLL_TIMEOUT_SEC)
            if _goal_reached(checker, expect_disconnect=args.expect_disconnect):
                break
        passed = _print_report(checker, expect_disconnect=args.expect_disconnect)
    finally:
        checker.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
