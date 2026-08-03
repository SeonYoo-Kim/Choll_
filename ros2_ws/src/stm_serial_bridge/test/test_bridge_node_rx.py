"""stm_serial_bridge 노드의 RX 경로(STATUS 수신 → /stm/* 발행) 테스트.

실제 STM32 없이 검증한다. 두 가지 방식을 쓴다:

- **fake SerialLink 주입**: 상태 전이·timeout 경계·패킷별 처리를 결정적으로 확인한다.
  실제 시각 대신 `_now_sec`을 대체해 경계값(정확히 `status_timeout_sec`)을 정확히 만든다.
- **PTY 통합**: `PTY master -> read_available() -> feed() -> parse_packet() -> Publisher`
  경로가 실제로 맞물려 도는지 확인한다.

발행 결과는 Publisher를 캡처용 fake로 바꿔 확인한다. 실제 DDS 왕복을 기다리면 테스트가
느리고 불안정해지는데, 여기서 검증하려는 것은 "어떤 값을 어떤 토픽에 넣는가"이므로
캡처가 더 정확한 도구다.

실행::

    cd ros2_ws
    export ROS_LOCALHOST_ONLY=1
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 -m pytest src/stm_serial_bridge/test/test_bridge_node_rx.py -v
"""

import os
import pty
import time
from collections.abc import Iterator
from typing import Any

import pytest
import rclpy

from stm_serial_bridge.serial_link import SerialLink, SerialLinkError
from stm_serial_bridge.stm_serial_bridge_node import (
    CONNECTED_TOPIC,
    ENCODER_TOTAL_TOPIC,
    FAULT_NONE,
    FAULT_STALL_BOTH,
    FAULT_STALL_LEFT,
    FAULT_STALL_RIGHT,
    FAULT_TOPIC,
    PWM_TOPIC,
    WHEEL_ACTUAL_TOPIC,
    WHEEL_TARGET_TOPIC,
    StmSerialBridgeNode,
)

STATUS_LINE = b"STATUS,1.00,2.00,3.00,4.00,5,6,7,8\r\n"
STATUS_TIMEOUT_SEC = 0.5


@pytest.fixture(scope="module", autouse=True)
def _ros_context() -> Iterator[None]:
    """Init/shutdown rclpy once for this module."""
    rclpy.init()
    try:
        yield
    finally:
        rclpy.shutdown()


class _CapturingPublisher:
    """Publisher 대체. 발행된 메시지를 순서대로 모아둔다."""

    def __init__(self) -> None:
        self.messages: list[Any] = []

    def publish(self, message: Any) -> None:  # noqa: ANN401 - 여러 메시지 타입을 받는다
        """Record the published message."""
        self.messages.append(message)

    @property
    def last(self) -> Any:  # noqa: ANN401
        """마지막으로 발행된 메시지."""
        return self.messages[-1]


class _FakeSerialLink:
    """SerialLink 대체. `read_available()`이 미리 넣어둔 chunk를 순서대로 돌려준다."""

    def __init__(self, chunks: list[bytes] | None = None) -> None:
        self.chunks = list(chunks or [])
        self.read_error: SerialLinkError | None = None
        self.read_count = 0
        self.written: list[str] = []
        self.closed = False

    def read_available(self) -> bytes:
        """Return the next queued chunk, or raise the configured error."""
        self.read_count += 1
        if self.read_error is not None:
            raise self.read_error
        if not self.chunks:
            return b""
        return self.chunks.pop(0)

    def write(self, data: str) -> None:
        """Record the written command."""
        self.written.append(data)

    def close(self) -> None:
        """Mark the fake link closed."""
        self.closed = True


def _make_node(
    *,
    dry_run: bool = False,
    status_timeout_sec: float = STATUS_TIMEOUT_SEC,
    serial_link: _FakeSerialLink | None = None,
) -> StmSerialBridgeNode:
    """Build a started node with capturing publishers and an injected fake link.

    `dry_run=false`인데 실제 포트를 열지 않기 위해, `start()` 전에 `_connect_serial`을
    fake 주입으로 대체한다.

    Args:
        dry_run: dry_run 파라미터.
        status_timeout_sec: STATUS timeout 파라미터.
        serial_link: 주입할 fake 링크. None이면 빈 fake를 만든다.

    Returns:
        `start()`까지 끝난 노드.
    """
    node = StmSerialBridgeNode()
    node.set_parameters(
        [
            rclpy.parameter.Parameter("dry_run", value=dry_run),
            rclpy.parameter.Parameter("status_timeout_sec", value=status_timeout_sec),
        ]
    )
    # set_parameters는 이미 __init__에서 읽어둔 캐시를 바꾸지 않으므로 직접 갱신한다.
    node._dry_run = dry_run  # noqa: SLF001
    node._status_timeout_sec = status_timeout_sec  # noqa: SLF001

    link = serial_link if serial_link is not None else _FakeSerialLink()
    if not dry_run:
        node._connect_serial = lambda: setattr(node, "_serial_link", link)  # noqa: SLF001

    node.start()

    # 실제 Publisher를 캡처용으로 교체하고, 시작 시 발행분을 지운 뒤 테스트를 시작한다.
    for attribute in (
        "_wheel_target_publisher",
        "_wheel_actual_publisher",
        "_pwm_publisher",
        "_encoder_publisher",
        "_connected_publisher",
        "_fault_publisher",
    ):
        setattr(node, attribute, _CapturingPublisher())
    return node


@pytest.fixture
def node_factory() -> Iterator[Any]:
    """Yield a factory that destroys every created node at teardown."""
    created: list[StmSerialBridgeNode] = []

    def factory(**kwargs: Any) -> StmSerialBridgeNode:  # noqa: ANN401
        node = _make_node(**kwargs)
        created.append(node)
        return node

    try:
        yield factory
    finally:
        for node in created:
            node.destroy_node()


def _set_clock(node: StmSerialBridgeNode, value: float) -> None:
    """Freeze the node's monotonic clock at a given value.

    `_now_sec()`은 staticmethod이므로 인스턴스 속성으로 덮어써 경계값을 정확히 만든다.

    Args:
        node: 대상 노드.
        value: 고정할 시각(초).
    """
    node._now_sec = lambda: value  # type: ignore[method-assign]  # noqa: SLF001


# ---------------------------------------------------------------------------
# 1. 파라미터 기본값과 유효성 검사
# ---------------------------------------------------------------------------


def test_rx_parameters_have_documented_defaults() -> None:
    """rx_poll_hz=50.0, status_timeout_sec=0.5가 기본값이다."""
    node = StmSerialBridgeNode()
    try:
        assert node.get_parameter("rx_poll_hz").value == pytest.approx(50.0)
        assert node.get_parameter("status_timeout_sec").value == pytest.approx(0.5)
    finally:
        node.destroy_node()


@pytest.mark.parametrize("name", ["rx_poll_hz", "status_timeout_sec"])
@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_rx_parameters_are_rejected(name: str, value: float) -> None:
    """rx_poll_hz/status_timeout_sec가 0 이하·비유한이면 start()가 ValueError다."""
    node = StmSerialBridgeNode()
    try:
        setattr(node, f"_{name}", value)
        with pytest.raises(ValueError, match=name):
            node.start()
        # 검증 실패 시 구독·타이머가 만들어지지 않는다
        assert node._subscription is None  # noqa: SLF001
        assert node._tx_timer is None  # noqa: SLF001
        assert node._rx_timer is None  # noqa: SLF001
    finally:
        node.destroy_node()


# ---------------------------------------------------------------------------
# 2. dry_run=true — RX 타이머·Serial read 없음
# ---------------------------------------------------------------------------


def test_dry_run_creates_no_rx_timer_and_no_serial_link(node_factory: Any) -> None:  # noqa: ANN401
    """dry_run=true에서는 RX 타이머도 SerialLink도 만들지 않는다."""
    node = node_factory(dry_run=True)

    assert node._rx_timer is None  # noqa: SLF001
    assert node._serial_link is None  # noqa: SLF001
    assert node._tx_timer is not None  # TX 타이머는 그대로 생성된다  # noqa: SLF001


def test_dry_run_publishes_initial_state(node_factory: Any) -> None:  # noqa: ANN401
    """dry_run=true에서도 Publisher는 만들어지고 초기 상태를 발행한다.

    캡처 교체 전에 이미 발행됐으므로, 노드 상태와 재발행으로 확인한다.
    """
    node = node_factory(dry_run=True)

    assert node.connected is False
    assert node.fault_state == FAULT_NONE

    node._publish_connected(force=True)  # noqa: SLF001
    node._publish_fault(force=True)  # noqa: SLF001

    assert node._connected_publisher.last.data is False  # noqa: SLF001
    assert node._fault_publisher.last.data == FAULT_NONE  # noqa: SLF001


def test_dry_run_rx_callback_does_not_read(node_factory: Any) -> None:  # noqa: ANN401
    """dry_run에서 RX 콜백이 어쩌다 불려도 Serial read를 시도하지 않는다."""
    link = _FakeSerialLink([STATUS_LINE])
    node = node_factory(dry_run=True)

    node._rx_timer_callback()  # noqa: SLF001

    assert link.read_count == 0
    assert node.connected is False


# ---------------------------------------------------------------------------
# 3~6. connected 상태 전이
# ---------------------------------------------------------------------------


def test_connected_is_false_before_any_status(node_factory: Any) -> None:  # noqa: ANN401
    """시작 상태는 false다(포트가 열려 있어도)."""
    node = node_factory()

    assert node.connected is False


def test_connected_becomes_true_after_valid_status(node_factory: Any) -> None:  # noqa: ANN401
    """유효한 STATUS를 받으면 connected=true가 되고 그때 한 번 발행된다."""
    link = _FakeSerialLink([STATUS_LINE])
    node = node_factory(serial_link=link)

    node._rx_timer_callback()  # noqa: SLF001

    assert node.connected is True
    assert node._connected_publisher.last.data is True  # noqa: SLF001


def test_connected_is_published_only_on_change(node_factory: Any) -> None:  # noqa: ANN401
    """같은 값을 50Hz마다 다시 발행하지 않는다(변화 시점에만 발행)."""
    link = _FakeSerialLink([STATUS_LINE, STATUS_LINE, STATUS_LINE])
    node = node_factory(serial_link=link)

    for _ in range(3):
        node._rx_timer_callback()  # noqa: SLF001

    assert node.connected is True
    assert len(node._connected_publisher.messages) == 1  # noqa: SLF001


def test_connected_drops_at_exact_timeout_boundary(node_factory: Any) -> None:  # noqa: ANN401
    """★ 정확히 status_timeout_sec 경과 시점에 false로 전환한다(경계값 포함)."""
    link = _FakeSerialLink([STATUS_LINE])
    node = node_factory(serial_link=link)

    _set_clock(node, 100.0)
    node._rx_timer_callback()  # noqa: SLF001
    assert node.connected is True

    # 경계 직전: 아직 true
    _set_clock(node, 100.0 + STATUS_TIMEOUT_SEC - 0.001)
    node._rx_timer_callback()  # noqa: SLF001
    assert node.connected is True

    # 정확히 경계: false
    _set_clock(node, 100.0 + STATUS_TIMEOUT_SEC)
    node._rx_timer_callback()  # noqa: SLF001
    assert node.connected is False
    assert node._connected_publisher.last.data is False  # noqa: SLF001


def test_timeout_is_checked_even_with_no_data(node_factory: Any) -> None:  # noqa: ANN401
    """read_available()이 b""를 돌려줘도 timeout 검사는 수행한다."""
    link = _FakeSerialLink([STATUS_LINE])
    node = node_factory(serial_link=link)

    _set_clock(node, 10.0)
    node._rx_timer_callback()  # noqa: SLF001
    assert node.connected is True

    _set_clock(node, 10.0 + STATUS_TIMEOUT_SEC + 0.1)
    assert link.chunks == []  # 더 이상 데이터 없음 -> b"" 반환
    node._rx_timer_callback()  # noqa: SLF001

    assert node.connected is False


# ---------------------------------------------------------------------------
# 5. STATUS 데이터 발행
# ---------------------------------------------------------------------------


def test_status_is_published_to_all_topics_in_left_right_order(  # noqa: ANN401
    node_factory: Any,
) -> None:
    """★ 4개 토픽에 [left, right] 순서로 정확히 발행된다.

    와이어 순서는 `LT,LA,RT,RA`(좌우 교차)이므로, 좌우로 다시 묶는 과정에서 목표와
    실측이 섞이면 이 테스트가 실패한다.
    """
    link = _FakeSerialLink([STATUS_LINE])
    node = node_factory(serial_link=link)

    node._rx_timer_callback()  # noqa: SLF001

    assert node._wheel_target_publisher.last.data == pytest.approx([1.00, 3.00])  # noqa: SLF001
    assert node._wheel_actual_publisher.last.data == pytest.approx([2.00, 4.00])  # noqa: SLF001
    assert list(node._pwm_publisher.last.data) == [5, 6]  # noqa: SLF001
    assert list(node._encoder_publisher.last.data) == [7, 8]  # noqa: SLF001


def test_status_negative_values_are_published(node_factory: Any) -> None:  # noqa: ANN401
    """음수 값(후진/역회전)도 부호를 유지해 발행된다."""
    link = _FakeSerialLink([b"STATUS,-1.0,-2.0,-3.0,-4.0,-5,-6,-7,-8\r\n"])
    node = node_factory(serial_link=link)

    node._rx_timer_callback()  # noqa: SLF001

    assert node._wheel_target_publisher.last.data == pytest.approx([-1.0, -3.0])  # noqa: SLF001
    assert list(node._pwm_publisher.last.data) == [-5, -6]  # noqa: SLF001
    assert list(node._encoder_publisher.last.data) == [-7, -8]  # noqa: SLF001


def test_topic_names_match_the_agreed_contract() -> None:
    """토픽 이름이 합의된 계약과 일치한다(오타 방지)."""
    assert WHEEL_TARGET_TOPIC == "/stm/wheel_target_rad_s"
    assert WHEEL_ACTUAL_TOPIC == "/stm/wheel_actual_rad_s"
    assert PWM_TOPIC == "/stm/pwm"
    assert ENCODER_TOTAL_TOPIC == "/stm/encoder_total"
    assert CONNECTED_TOPIC == "/stm/connected"
    assert FAULT_TOPIC == "/stm/fault"


# ---------------------------------------------------------------------------
# 7~8. 비STATUS 패킷과 connected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        b"FAULT,STALL,LEFT\r\n",
        b"ERROR,RESET_STALL,NO_STALL\r\n",
        b"PI_GAINS,0.5,0.0\r\n",
        b"STALL_RESET,OK\r\n",
        b"FAULT_CLEARED,STALL\r\n",
        b"SOME_NEW_MESSAGE,1\r\n",  # UNKNOWN
        b"STATUS,1.0\r\n",  # MALFORMED
        b"\r\n",  # BLANK
    ],
)
def test_non_status_packets_never_set_connected(  # noqa: ANN401
    node_factory: Any, line: bytes
) -> None:
    """★ 비STATUS 패킷만 받아서는 connected=true가 되지 않는다."""
    link = _FakeSerialLink([line])
    node = node_factory(serial_link=link)

    node._rx_timer_callback()  # noqa: SLF001

    assert node.connected is False
    assert node._last_status_time_sec is None  # noqa: SLF001


def test_non_status_traffic_does_not_refresh_the_timeout(node_factory: Any) -> None:  # noqa: ANN401
    """★ STATUS 이후 비STATUS만 계속 오면 결국 timeout으로 false가 된다."""
    link = _FakeSerialLink(
        [STATUS_LINE, b"FAULT,STALL,LEFT\r\n", b"PI_GAINS,0.5,0.0\r\n"]
    )
    node = node_factory(serial_link=link)

    _set_clock(node, 50.0)
    node._rx_timer_callback()  # noqa: SLF001
    assert node.connected is True

    # 비STATUS 줄이 도착해도 마지막 STATUS 시각은 갱신되지 않는다
    _set_clock(node, 50.0 + 0.3)
    node._rx_timer_callback()  # noqa: SLF001
    assert node.connected is True
    assert node._last_status_time_sec == pytest.approx(50.0)  # noqa: SLF001

    _set_clock(node, 50.0 + STATUS_TIMEOUT_SEC)
    node._rx_timer_callback()  # noqa: SLF001
    assert node.connected is False


# ---------------------------------------------------------------------------
# 9~11. fault 상태 전이
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (b"FAULT,STALL,LEFT\r\n", FAULT_STALL_LEFT),
        (b"FAULT,STALL,RIGHT\r\n", FAULT_STALL_RIGHT),
        (b"FAULT,STALL,BOTH\r\n", FAULT_STALL_BOTH),
    ],
)
def test_fault_states_are_mapped_and_published(  # noqa: ANN401
    node_factory: Any, line: bytes, expected: str
) -> None:
    """FAULT,STALL,<cause>가 STALL_LEFT/RIGHT/BOTH로 매핑되어 발행된다."""
    link = _FakeSerialLink([line])
    node = node_factory(serial_link=link)

    node._rx_timer_callback()  # noqa: SLF001

    assert node.fault_state == expected
    assert node._fault_publisher.last.data == expected  # noqa: SLF001


def test_fault_cleared_returns_to_none(node_factory: Any) -> None:  # noqa: ANN401
    """FAULT_CLEARED,STALL을 받으면 NONE으로 돌아간다."""
    link = _FakeSerialLink([b"FAULT,STALL,BOTH\r\n", b"FAULT_CLEARED,STALL\r\n"])
    node = node_factory(serial_link=link)

    node._rx_timer_callback()  # noqa: SLF001
    assert node.fault_state == FAULT_STALL_BOTH

    node._rx_timer_callback()  # noqa: SLF001

    assert node.fault_state == FAULT_NONE
    assert node._fault_publisher.last.data == FAULT_NONE  # noqa: SLF001


def test_stall_reset_ack_alone_does_not_clear_fault(node_factory: Any) -> None:  # noqa: ANN401
    """★ STALL_RESET,OK만으로는 fault가 NONE이 되지 않는다.

    프로토콜상 ACK는 "명령을 수락했다"는 뜻이고, 실제 해제는 FAULT_CLEARED로 통보된다.
    """
    link = _FakeSerialLink([b"FAULT,STALL,LEFT\r\n", b"STALL_RESET,OK\r\n"])
    node = node_factory(serial_link=link)

    node._rx_timer_callback()  # noqa: SLF001
    node._rx_timer_callback()  # noqa: SLF001

    assert node.fault_state == FAULT_STALL_LEFT


def test_fault_survives_connection_timeout(node_factory: Any) -> None:  # noqa: ANN401
    """★ 연결 timeout에서도 마지막 fault를 유지한다(임의로 NONE으로 되돌리지 않는다)."""
    link = _FakeSerialLink([STATUS_LINE, b"FAULT,STALL,RIGHT\r\n"])
    node = node_factory(serial_link=link)

    _set_clock(node, 5.0)
    node._rx_timer_callback()  # noqa: SLF001
    node._rx_timer_callback()  # noqa: SLF001
    assert node.fault_state == FAULT_STALL_RIGHT

    _set_clock(node, 5.0 + STATUS_TIMEOUT_SEC + 1.0)
    node._rx_timer_callback()  # noqa: SLF001

    assert node.connected is False
    assert node.fault_state == FAULT_STALL_RIGHT  # 유지


def test_fault_is_published_only_on_change(node_factory: Any) -> None:  # noqa: ANN401
    """같은 fault를 반복 수신해도 발행은 한 번뿐이다."""
    link = _FakeSerialLink([b"FAULT,STALL,LEFT\r\n"] * 3)
    node = node_factory(serial_link=link)

    for _ in range(3):
        node._rx_timer_callback()  # noqa: SLF001

    assert len(node._fault_publisher.messages) == 1  # noqa: SLF001


# ---------------------------------------------------------------------------
# 12~13. 여러 패킷 / 부분 수신
# ---------------------------------------------------------------------------


def test_multiple_packets_in_one_read_are_handled_in_order(node_factory: Any) -> None:  # noqa: ANN401
    """★ 한 read에 여러 줄이 들어오면 순서대로 처리된다.

    FAULT 뒤에 FAULT_CLEARED가 오므로, 순서를 지키지 않으면 최종 상태가 달라진다.
    """
    link = _FakeSerialLink(
        [STATUS_LINE + b"FAULT,STALL,BOTH\r\n" + b"FAULT_CLEARED,STALL\r\n"]
    )
    node = node_factory(serial_link=link)

    node._rx_timer_callback()  # noqa: SLF001

    assert node.connected is True
    assert node.fault_state == FAULT_NONE
    faults = [message.data for message in node._fault_publisher.messages]  # noqa: SLF001
    assert faults == [FAULT_STALL_BOTH, FAULT_NONE]


def test_partial_status_is_assembled_across_rx_ticks(node_factory: Any) -> None:  # noqa: ANN401
    """★ 부분 수신된 STATUS가 여러 RX tick에 걸쳐 조립된다."""
    link = _FakeSerialLink(
        [b"STATUS,1.00,2.00,", b"3.00,4.00,5,", b"6,7,8\r\n"]
    )
    node = node_factory(serial_link=link)

    node._rx_timer_callback()  # noqa: SLF001
    assert node.connected is False  # 아직 완성되지 않았다
    node._rx_timer_callback()  # noqa: SLF001
    assert node.connected is False
    node._rx_timer_callback()  # noqa: SLF001

    assert node.connected is True
    assert node._wheel_target_publisher.last.data == pytest.approx([1.00, 3.00])  # noqa: SLF001


# ---------------------------------------------------------------------------
# 14. Serial read 실패
# ---------------------------------------------------------------------------


def test_serial_read_failure_latches_fatal_and_cancels_both_timers(  # noqa: ANN401
    node_factory: Any,
) -> None:
    """★ read 실패는 치명적 오류로 래치되고 TX/RX 타이머가 모두 취소된다."""
    link = _FakeSerialLink([STATUS_LINE])
    node = node_factory(serial_link=link)

    node._rx_timer_callback()  # noqa: SLF001
    assert node.connected is True

    link.read_error = SerialLinkError("Serial read failed: reason=[Errno 5]")
    node._rx_timer_callback()  # noqa: SLF001

    assert node.serial_fatal_error is True
    assert node.requested_exit_code == 1
    assert node._tx_timer.is_canceled() is True  # noqa: SLF001
    assert node._rx_timer.is_canceled() is True  # noqa: SLF001
    # 데이터가 낡았음을 알린다
    assert node.connected is False
    assert node._connected_publisher.last.data is False  # noqa: SLF001


def test_fatal_error_blocks_further_reads_and_writes(node_factory: Any) -> None:  # noqa: ANN401
    """치명적 오류 래치 후에는 read도 write도 더 시도하지 않는다."""
    link = _FakeSerialLink()
    link.read_error = SerialLinkError("Serial read failed: reason=boom")
    node = node_factory(serial_link=link)

    node._rx_timer_callback()  # noqa: SLF001
    reads_at_failure = link.read_count

    node._rx_timer_callback()  # noqa: SLF001
    node._tx_timer_callback()  # noqa: SLF001

    assert link.read_count == reads_at_failure  # 추가 read 없음
    assert link.written == []  # 추가 write 없음


def test_read_failure_keeps_last_fault(node_factory: Any) -> None:  # noqa: ANN401
    """read 실패로 종료해도 마지막 fault는 유지된다."""
    link = _FakeSerialLink([b"FAULT,STALL,BOTH\r\n"])
    node = node_factory(serial_link=link)

    node._rx_timer_callback()  # noqa: SLF001
    link.read_error = SerialLinkError("Serial read failed: reason=boom")
    node._rx_timer_callback()  # noqa: SLF001

    assert node.serial_fatal_error is True
    assert node.fault_state == FAULT_STALL_BOTH


# ---------------------------------------------------------------------------
# PTY 통합: master -> read_available() -> feed() -> parse_packet() -> Publisher
# ---------------------------------------------------------------------------


@pytest.fixture
def pty_pair() -> Iterator[tuple[str, int]]:
    """Create a PTY pair and yield the slave path with the master fd."""
    master_fd, slave_fd = pty.openpty()
    os.set_blocking(master_fd, False)
    try:
        yield (os.ttyname(slave_fd), master_fd)
    finally:
        for file_descriptor in (slave_fd, master_fd):
            try:
                os.close(file_descriptor)
            except OSError:
                pass


def test_pty_status_and_fault_reach_the_publishers(pty_pair: tuple[str, int]) -> None:
    """★ 실제 PTY를 거쳐 STATUS/FAULT가 상태 토픽 값까지 도달한다."""
    slave_path, master_fd = pty_pair
    link = SerialLink(slave_path, 115200)
    link.open()

    node = StmSerialBridgeNode()
    node._dry_run = False  # noqa: SLF001
    node._connect_serial = lambda: setattr(node, "_serial_link", link)  # noqa: SLF001
    node.start()
    for attribute in (
        "_wheel_target_publisher",
        "_wheel_actual_publisher",
        "_pwm_publisher",
        "_encoder_publisher",
        "_connected_publisher",
        "_fault_publisher",
    ):
        setattr(node, attribute, _CapturingPublisher())

    try:
        os.write(master_fd, STATUS_LINE + b"FAULT,STALL,LEFT\r\n")

        for _ in range(200):
            node._rx_timer_callback()  # noqa: SLF001
            if node.connected and node.fault_state != FAULT_NONE:
                break
            time.sleep(0.005)
    finally:
        node.destroy_node()
        link.close()

    assert node.connected is True
    assert node.fault_state == FAULT_STALL_LEFT
    assert node._wheel_target_publisher.last.data == pytest.approx([1.00, 3.00])  # noqa: SLF001
    assert node._wheel_actual_publisher.last.data == pytest.approx([2.00, 4.00])  # noqa: SLF001
    assert list(node._pwm_publisher.last.data) == [5, 6]  # noqa: SLF001
    assert list(node._encoder_publisher.last.data) == [7, 8]  # noqa: SLF001
