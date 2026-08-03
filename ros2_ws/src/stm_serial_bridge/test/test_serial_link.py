"""SerialLink의 포트 열기/닫기/송신/수신 단위 테스트.

실제 하드웨어(`/dev/ttyACM*`) 없이 Linux 표준 라이브러리 `pty`로 검증한다.
파일 끝에는 `PTY master -> SerialLink.read_available() -> LineDecoder.feed()`
통합 테스트도 포함한다(8b).

실행::

    cd ros2_ws
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 -m pytest src/stm_serial_bridge/test/test_serial_link.py -v
"""

import os
import pty
import time
from collections.abc import Iterator

import pytest
import serial

from stm_serial_bridge.line_decoder import LineDecoder
from stm_serial_bridge.serial_link import SerialLink, SerialLinkError

BAUD_RATE = 115200

# 존재할 수 없는 경로. 실제 장치를 건드리지 않기 위해 /dev 밖을 쓴다.
MISSING_PORT = "/path/that/does/not/exist"

# 브리지가 실제로 만드는 프레임과 같은 형식(protocol.build_set_wheel_vel_command).
ACTIVE_FRAME = "SET_WHEEL_VEL,1.923,4.231\r\n"
STOP_FRAME = "SET_WHEEL_VEL,0.000,0.000\r\n"


@pytest.fixture
def pty_pair() -> Iterator[tuple[str, int]]:
    """Create a pseudo-terminal pair and yield the slave path with the master fd.

    master file descriptor는 테스트가 끝날 때까지 열어 둔다(닫으면 slave가 사라진다).
    write 테스트는 이 master fd에서 직접 읽어 실제로 나간 바이트를 확인한다.

    Yields:
        `(slave 장치 경로, master fd)`.
    """
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


@pytest.fixture
def pty_slave_path(pty_pair: tuple[str, int]) -> str:
    """Return only the slave device path (open/close 테스트용)."""
    return pty_pair[0]


def _read_all(master_fd: int) -> bytes:
    """Drain everything currently readable from the PTY master.

    Args:
        master_fd: non-blocking으로 설정된 master file descriptor.

    Returns:
        지금까지 누적된 바이트. 없으면 빈 바이트열.
    """
    received = bytearray()
    while True:
        try:
            chunk = os.read(master_fd, 4096)
        except (BlockingIOError, OSError):
            break
        if not chunk:
            break
        received.extend(chunk)
    return bytes(received)


def test_open_then_close_toggles_is_open(pty_slave_path: str) -> None:
    """유효한 PTY를 열고 닫으면 is_open이 True -> False로 바뀐다."""
    link = SerialLink(pty_slave_path, BAUD_RATE)

    assert link.is_open is False

    link.open()
    try:
        assert link.is_open is True
    finally:
        link.close()

    assert link.is_open is False


def test_constructor_does_not_open_the_port(pty_slave_path: str) -> None:
    """생성자는 포트를 열지 않는다 — open()을 부르기 전까지 is_open은 False다."""
    link = SerialLink(pty_slave_path, BAUD_RATE)

    assert link.is_open is False


def test_close_is_idempotent(pty_slave_path: str) -> None:
    """close()를 여러 번 호출해도 예외가 발생하지 않는다."""
    link = SerialLink(pty_slave_path, BAUD_RATE)
    link.open()

    link.close()
    link.close()
    link.close()

    assert link.is_open is False


def test_close_without_open_is_safe(pty_slave_path: str) -> None:
    """한 번도 열지 않은 상태에서 close()를 불러도 안전하다(종료 경로 방어)."""
    link = SerialLink(pty_slave_path, BAUD_RATE)

    link.close()

    assert link.is_open is False


def test_open_is_idempotent(pty_slave_path: str) -> None:
    """open()을 여러 번 호출해도 중복 연결 없이 열린 상태를 유지한다."""
    link = SerialLink(pty_slave_path, BAUD_RATE)

    link.open()
    try:
        assert link.is_open is True
        link.open()
        link.open()
        assert link.is_open is True
    finally:
        link.close()

    assert link.is_open is False


def test_reopen_after_close_works(pty_slave_path: str) -> None:
    """close() 후 다시 open()할 수 있다(close가 상태를 제대로 되돌리는지 확인)."""
    link = SerialLink(pty_slave_path, BAUD_RATE)

    link.open()
    link.close()
    link.open()
    try:
        assert link.is_open is True
    finally:
        link.close()


def test_missing_port_raises_serial_link_error() -> None:
    """존재하지 않는 경로를 열면 SerialLinkError이고, 메시지에 진단 정보가 담긴다."""
    link = SerialLink(MISSING_PORT, BAUD_RATE)

    with pytest.raises(SerialLinkError) as error_info:
        link.open()

    message = str(error_info.value)
    assert MISSING_PORT in message
    assert str(BAUD_RATE) in message
    assert "reason=" in message
    # 실패 후에도 상태가 열린 것으로 남지 않아야 한다.
    assert link.is_open is False


def test_serial_link_error_is_not_a_pyserial_exception() -> None:
    """SerialLinkError는 RuntimeError 계열이다 — 호출자가 pyserial 없이 잡을 수 있다."""
    assert issubclass(SerialLinkError, RuntimeError)


@pytest.mark.parametrize("port", ["", " ", "   ", "\t", "\n"])
def test_blank_port_raises_value_error(port: str) -> None:
    """빈 문자열이나 공백뿐인 port는 ValueError다."""
    with pytest.raises(ValueError, match="port"):
        SerialLink(port, BAUD_RATE)


@pytest.mark.parametrize("baud_rate", [0, -1, -115200])
def test_non_positive_baud_rate_raises_value_error(baud_rate: int) -> None:
    """baud_rate가 0 이하면 ValueError다."""
    with pytest.raises(ValueError, match="baud_rate"):
        SerialLink("/dev/example", baud_rate)


# ---------------------------------------------------------------------------
# write() — 5c-1에서 추가
# ---------------------------------------------------------------------------


def test_write_sends_exact_active_frame(pty_pair: tuple[str, int]) -> None:
    """열린 PTY에 active 프레임을 쓰면 master에서 정확히 같은 bytes가 읽힌다."""
    slave_path, master_fd = pty_pair
    link = SerialLink(slave_path, BAUD_RATE)
    link.open()
    try:
        link.write(ACTIVE_FRAME)
        assert _read_all(master_fd) == b"SET_WHEEL_VEL,1.923,4.231\r\n"
    finally:
        link.close()


def test_write_sends_exact_stop_frame(pty_pair: tuple[str, int]) -> None:
    """waiting/timed_out에서 쓰는 0,0 프레임도 정확히 전달된다."""
    slave_path, master_fd = pty_pair
    link = SerialLink(slave_path, BAUD_RATE)
    link.open()
    try:
        link.write(STOP_FRAME)
        assert _read_all(master_fd) == b"SET_WHEEL_VEL,0.000,0.000\r\n"
    finally:
        link.close()


def test_write_preserves_frame_order_and_crlf(pty_pair: tuple[str, int]) -> None:
    """여러 프레임을 순서대로 쓰면 누적 bytes가 정확한 연결 결과와 일치한다."""
    slave_path, master_fd = pty_pair
    link = SerialLink(slave_path, BAUD_RATE)
    link.open()
    try:
        link.write(STOP_FRAME)
        link.write(ACTIVE_FRAME)
        link.write(STOP_FRAME)
        received = _read_all(master_fd)
    finally:
        link.close()

    assert received == (
        b"SET_WHEEL_VEL,0.000,0.000\r\n"
        b"SET_WHEEL_VEL,1.923,4.231\r\n"
        b"SET_WHEEL_VEL,0.000,0.000\r\n"
    )
    # CRLF 중복/누락 없이 프레임 수만큼만 등장해야 한다.
    assert received.count(b"\r\n") == 3
    assert received.count(b"\n") == 3
    assert received.count(b"\r") == 3
    frames = received.split(b"\r\n")
    assert frames[-1] == b""  # 마지막 프레임도 CRLF로 끝난다
    assert [frame for frame in frames if frame] == [
        b"SET_WHEEL_VEL,0.000,0.000",
        b"SET_WHEEL_VEL,1.923,4.231",
        b"SET_WHEEL_VEL,0.000,0.000",
    ]


def test_write_before_open_raises_serial_link_error(pty_slave_path: str) -> None:
    """한 번도 열지 않은 링크에 write하면 SerialLinkError다."""
    link = SerialLink(pty_slave_path, BAUD_RATE)

    with pytest.raises(SerialLinkError, match="port is not open"):
        link.write(ACTIVE_FRAME)


def test_write_after_close_raises_serial_link_error(pty_slave_path: str) -> None:
    """열었다 닫은 뒤 write하면 SerialLinkError다."""
    link = SerialLink(pty_slave_path, BAUD_RATE)
    link.open()
    link.close()

    with pytest.raises(SerialLinkError, match="port is not open"):
        link.write(ACTIVE_FRAME)


def test_write_empty_string_raises_value_error(pty_slave_path: str) -> None:
    """빈 문자열 write는 ValueError다(보낼 프레임이 없다)."""
    link = SerialLink(pty_slave_path, BAUD_RATE)

    with pytest.raises(ValueError, match="empty"):
        link.write("")


@pytest.mark.parametrize("data", [b"SET_WHEEL_VEL,0,0\r\n", 123, None, 1.5, ["a"]])
def test_write_non_str_raises_type_error(pty_slave_path: str, data: object) -> None:
    """str이 아닌 값 write는 TypeError다(bytes를 그대로 넘기는 실수 포함)."""
    link = SerialLink(pty_slave_path, BAUD_RATE)

    with pytest.raises(TypeError, match="must be str"):
        link.write(data)  # type: ignore[arg-type]


@pytest.mark.parametrize("data", ["모터\r\n", "SET_WHEEL_VEL,1,1°\r\n", "ÿ"])
def test_write_non_ascii_raises_value_error(pty_slave_path: str, data: str) -> None:
    """ASCII로 인코딩할 수 없는 문자열 write는 ValueError다."""
    link = SerialLink(pty_slave_path, BAUD_RATE)

    with pytest.raises(ValueError, match="ascii"):
        link.write(data)


# "설정하지 않음"과 "None을 반환하도록 설정함"을 구분하기 위한 sentinel.
# None을 기본값으로 쓰면 pyserial이 None을 반환하는 경우를 테스트할 수 없다.
_UNSET = object()


class _FakeSerial:
    """pyserial 대체용 최소 fake. 실제 장치 없이 write 실패 경로를 검증한다."""

    def __init__(
        self, *, result: object = _UNSET, error: Exception | None = None
    ) -> None:
        self.is_open = True
        self._result = result
        self._error = error

    def write(self, payload: bytes) -> object:
        """Raise the configured error, or return the configured byte count."""
        if self._error is not None:
            raise self._error
        if self._result is _UNSET:
            return len(payload)
        return self._result

    def close(self) -> None:
        """Mark the fake port closed."""
        self.is_open = False


@pytest.mark.parametrize(
    "error",
    [
        serial.SerialTimeoutException("write timeout"),
        serial.SerialException("device disconnected"),
        OSError(5, "Input/output error"),
    ],
)
def test_write_converts_pyserial_errors_to_serial_link_error(
    pty_slave_path: str, error: Exception
) -> None:
    """pyserial write 예외는 SerialLinkError로 변환되고 진단 정보가 담긴다."""
    link = SerialLink(pty_slave_path, BAUD_RATE)
    link._serial = _FakeSerial(error=error)  # noqa: SLF001 - 실패 경로 주입용

    with pytest.raises(SerialLinkError) as error_info:
        link.write(ACTIVE_FRAME)

    message = str(error_info.value)
    assert "Serial write failed" in message
    assert pty_slave_path in message
    assert str(BAUD_RATE) in message
    assert "reason=" in message


@pytest.mark.parametrize("written", [0, 1, len(ACTIVE_FRAME) - 1, None])
def test_partial_write_raises_serial_link_error(
    pty_slave_path: str, written: object
) -> None:
    """기록된 바이트 수가 payload보다 적으면 partial write로 보고 실패시킨다."""
    link = SerialLink(pty_slave_path, BAUD_RATE)
    link._serial = _FakeSerial(result=written)  # noqa: SLF001 - 실패 경로 주입용

    with pytest.raises(SerialLinkError, match="partial write"):
        link.write(ACTIVE_FRAME)


def test_full_write_via_fake_does_not_raise(pty_slave_path: str) -> None:
    """전체 길이를 기록했다고 보고하면 성공으로 처리한다(partial 판정 기준 확인)."""
    link = SerialLink(pty_slave_path, BAUD_RATE)
    link._serial = _FakeSerial(result=len(ACTIVE_FRAME))  # noqa: SLF001

    link.write(ACTIVE_FRAME)


def test_write_does_not_append_or_modify_the_payload(pty_pair: tuple[str, int]) -> None:
    """전달한 문자열을 그대로 보낸다 — CRLF를 덧붙이거나 내용을 바꾸지 않는다."""
    slave_path, master_fd = pty_pair
    link = SerialLink(slave_path, BAUD_RATE)
    link.open()
    try:
        # 종단 문자가 없는 문자열도 그대로 나가야 한다(호출자 책임임을 고정).
        link.write("PING")
        assert _read_all(master_fd) == b"PING"
    finally:
        link.close()


# ---------------------------------------------------------------------------
# read_available() — 8b-1에서 추가
# ---------------------------------------------------------------------------


def _wait_for_bytes(link: SerialLink, expected_length: int) -> bytes:
    """Poll read_available() until enough bytes arrive (or attempts run out).

    PTY는 즉시 전달되는 편이지만 스케줄링에 따라 한 번의 호출로 다 안 읽힐 수 있다.
    부분 read는 오류가 아니므로 여러 번 호출해 모으는 것이 정상 사용법이다.

    Args:
        link: 열려 있는 링크.
        expected_length: 기대하는 총 바이트 수.

    Returns:
        모인 바이트(모자랄 수도 있다 — 호출자가 단정한다).
    """
    received = bytearray()
    for _ in range(200):
        received.extend(link.read_available())
        if len(received) >= expected_length:
            break
        time.sleep(0.005)
    return bytes(received)


def test_read_available_returns_empty_when_no_data(pty_pair: tuple[str, int]) -> None:
    """대기 중 데이터가 없으면 b""를 반환한다(오류가 아니다)."""
    slave_path, _master_fd = pty_pair
    link = SerialLink(slave_path, BAUD_RATE)
    link.open()
    try:
        assert link.read_available() == b""
        assert link.read_available() == b""  # 반복 호출도 안전
    finally:
        link.close()


def test_read_available_returns_exact_bytes(pty_pair: tuple[str, int]) -> None:
    """master가 보낸 bytes를 정확히 그대로 반환한다."""
    slave_path, master_fd = pty_pair
    payload = b"STATUS,2.00,1.95,2.00,1.97,36,37,15231,15188\r\n"
    link = SerialLink(slave_path, BAUD_RATE)
    link.open()
    try:
        os.write(master_fd, payload)
        assert _wait_for_bytes(link, len(payload)) == payload
    finally:
        link.close()


def test_read_available_accumulates_across_chunks(pty_pair: tuple[str, int]) -> None:
    """여러 번 나뉘어 도착한 bytes를 여러 호출로 모을 수 있다(부분 read 정상)."""
    slave_path, master_fd = pty_pair
    link = SerialLink(slave_path, BAUD_RATE)
    link.open()
    try:
        received = bytearray()
        for chunk in (b"STATUS,2.00,", b"1.95,2.00,1.97,", b"36,37,15231,15188\r\n"):
            os.write(master_fd, chunk)
            received.extend(_wait_for_bytes(link, 1))
        assert bytes(received) == b"STATUS,2.00,1.95,2.00,1.97,36,37,15231,15188\r\n"
    finally:
        link.close()


def test_read_available_does_not_decode_or_assemble(pty_pair: tuple[str, int]) -> None:
    """★ 디코딩·줄 조립을 하지 않는다 — raw bytes만 돌려준다.

    두 줄을 한 번에 보내도 줄 단위로 쪼개지 않고, CRLF도 벗기지 않으며, 반환형은
    항상 bytes다. 줄 조립은 LineDecoder의 책임이다.
    """
    slave_path, master_fd = pty_pair
    payload = b"FAULT,STALL,LEFT\r\nSTALL_RESET,OK\r\n"
    link = SerialLink(slave_path, BAUD_RATE)
    link.open()
    try:
        os.write(master_fd, payload)
        received = _wait_for_bytes(link, len(payload))

        assert isinstance(received, bytes)
        assert received == payload  # 두 줄이 한 덩어리로, CRLF 포함
        assert b"\r\n" in received
    finally:
        link.close()


def test_read_available_before_open_raises_serial_link_error(
    pty_slave_path: str,
) -> None:
    """한 번도 열지 않은 링크에서 읽으면 SerialLinkError다."""
    link = SerialLink(pty_slave_path, BAUD_RATE)

    with pytest.raises(SerialLinkError, match="port is not open"):
        link.read_available()


def test_read_available_after_close_raises_serial_link_error(
    pty_slave_path: str,
) -> None:
    """열었다 닫은 뒤 읽으면 SerialLinkError다."""
    link = SerialLink(pty_slave_path, BAUD_RATE)
    link.open()
    link.close()

    with pytest.raises(SerialLinkError, match="port is not open"):
        link.read_available()


class _FakeReadSerial:
    """읽기 실패 경로 주입용 fake. `in_waiting` 또는 `read()`에서 예외를 낸다."""

    def __init__(
        self,
        *,
        in_waiting_error: Exception | None = None,
        read_error: Exception | None = None,
        pending: int = 8,
        read_result: object = b"",
    ) -> None:
        self.is_open = True
        self._in_waiting_error = in_waiting_error
        self._read_error = read_error
        self._pending = pending
        self._read_result = read_result

    @property
    def in_waiting(self) -> int:
        """Raise the configured error, or report the pending byte count."""
        if self._in_waiting_error is not None:
            raise self._in_waiting_error
        return self._pending

    def read(self, size: int) -> object:  # noqa: ARG002 - fake는 size를 쓰지 않는다
        """Raise the configured error, or return the configured value."""
        if self._read_error is not None:
            raise self._read_error
        return self._read_result

    def close(self) -> None:
        """Mark the fake port closed."""
        self.is_open = False


@pytest.mark.parametrize(
    "error",
    [serial.SerialException("device disconnected"), OSError(5, "Input/output error")],
)
def test_in_waiting_error_becomes_serial_link_error(
    pty_slave_path: str, error: Exception
) -> None:
    """`in_waiting` 조회 예외가 SerialLinkError로 변환되고 진단 정보가 담긴다."""
    link = SerialLink(pty_slave_path, BAUD_RATE)
    link._serial = _FakeReadSerial(in_waiting_error=error)  # noqa: SLF001

    with pytest.raises(SerialLinkError) as error_info:
        link.read_available()

    message = str(error_info.value)
    assert "Serial read failed" in message
    assert pty_slave_path in message
    assert str(BAUD_RATE) in message
    assert "reason=" in message


@pytest.mark.parametrize(
    "error",
    [serial.SerialException("read failed"), OSError(5, "Input/output error")],
)
def test_read_error_becomes_serial_link_error(
    pty_slave_path: str, error: Exception
) -> None:
    """`read()` 예외가 SerialLinkError로 변환된다."""
    link = SerialLink(pty_slave_path, BAUD_RATE)
    link._serial = _FakeReadSerial(read_error=error)  # noqa: SLF001

    with pytest.raises(SerialLinkError, match="Serial read failed"):
        link.read_available()


def test_read_available_treats_none_result_as_empty(pty_slave_path: str) -> None:
    """pyserial이 None을 돌려주는 구현에서도 b""로 정규화한다(오류 아님)."""
    link = SerialLink(pty_slave_path, BAUD_RATE)
    link._serial = _FakeReadSerial(read_result=None)  # noqa: SLF001

    assert link.read_available() == b""


def test_read_available_returns_partial_read_without_error(
    pty_slave_path: str,
) -> None:
    """`in_waiting`보다 적게 읽혀도 오류가 아니다 — 읽힌 만큼만 반환한다."""
    link = SerialLink(pty_slave_path, BAUD_RATE)
    link._serial = _FakeReadSerial(pending=100, read_result=b"ABC")  # noqa: SLF001

    assert link.read_available() == b"ABC"


# ---------------------------------------------------------------------------
# 통합: PTY master -> SerialLink.read_available() -> LineDecoder.feed()
# ---------------------------------------------------------------------------


def test_pty_to_serial_link_to_line_decoder_restores_lines(
    pty_pair: tuple[str, int],
) -> None:
    """★ 실제 PTY를 거쳐 STATUS/FAULT 줄이 정확히 복원된다.

    SerialLink는 raw bytes만, LineDecoder는 줄 조립만 담당하는 구성이 실제로
    맞물려 동작하는지 확인한다.
    """
    slave_path, master_fd = pty_pair
    status_line = "STATUS,2.00,1.95,2.00,1.97,36,37,15231,15188"
    fault_line = "FAULT,STALL,BOTH"

    link = SerialLink(slave_path, BAUD_RATE)
    decoder = LineDecoder()
    link.open()
    try:
        os.write(master_fd, f"{status_line}\r\n{fault_line}\r\n".encode())

        lines: list[str] = []
        for _ in range(200):
            lines.extend(decoder.feed(link.read_available()))
            if len(lines) >= 2:
                break
            time.sleep(0.005)
    finally:
        link.close()

    assert lines == [status_line, fault_line]
    assert decoder.pending_bytes == 0


def test_pty_split_writes_are_reassembled_by_decoder(
    pty_pair: tuple[str, int],
) -> None:
    """한 줄을 조각내어 쓰면 LineDecoder가 다시 하나로 조립한다."""
    slave_path, master_fd = pty_pair
    status_line = "STATUS,-2.00,-1.95,-2.00,-1.97,-36,-37,-15231,-15188"

    link = SerialLink(slave_path, BAUD_RATE)
    decoder = LineDecoder()
    link.open()
    try:
        lines: list[str] = []
        for chunk in (b"STATUS,-2.00,-1.95,", b"-2.00,-1.97,-36,", b"-37,-15231,-15188\r\n"):
            os.write(master_fd, chunk)
            for _ in range(50):
                lines.extend(decoder.feed(link.read_available()))
                if lines:
                    break
                time.sleep(0.005)
    finally:
        link.close()

    assert lines == [status_line]
