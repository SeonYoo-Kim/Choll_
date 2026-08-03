"""LineDecoder의 bytes → 줄 조립 단위 테스트.

pyserial·ROS·하드웨어 없이 돌아간다(입력이 bytes뿐인 순수 모듈).

실행::

    cd ros2_ws
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 -m pytest src/stm_serial_bridge/test/test_line_decoder.py -v
"""

import pytest

from stm_serial_bridge.line_decoder import DEFAULT_MAX_LINE_BYTES, LineDecoder

STATUS_LINE = "STATUS,2.00,1.95,2.00,1.97,36,37,15231,15188"
FAULT_LINE = "FAULT,STALL,LEFT"


# ---------------------------------------------------------------------------
# 기본 조립
# ---------------------------------------------------------------------------


def test_single_complete_packet() -> None:
    """한 번에 완전한 줄이 들어오면 그 줄을 반환한다."""
    decoder = LineDecoder()

    lines = decoder.feed(f"{STATUS_LINE}\r\n".encode())

    assert lines == [STATUS_LINE]
    assert decoder.pending_bytes == 0


def test_split_across_two_chunks() -> None:
    """줄이 두 chunk로 나뉘어 와도 완성 시점에 한 번 반환된다."""
    decoder = LineDecoder()

    assert decoder.feed(b"STATUS,2.00,1.95,") == []
    assert decoder.pending_bytes == 17

    lines = decoder.feed(b"2.00,1.97,36,37,15231,15188\r\n")

    assert lines == [STATUS_LINE]
    assert decoder.pending_bytes == 0


def test_one_byte_at_a_time() -> None:
    """모든 바이트가 한 글자씩 들어와도 마지막 LF에서 한 줄이 완성된다."""
    decoder = LineDecoder()
    payload = f"{STATUS_LINE}\r\n".encode()
    collected: list[str] = []

    for index in range(len(payload)):
        collected.extend(decoder.feed(payload[index : index + 1]))

    assert collected == [STATUS_LINE]
    assert decoder.pending_bytes == 0


def test_multiple_packets_in_one_chunk() -> None:
    """한 chunk에 여러 줄이 있으면 받은 순서대로 모두 반환한다."""
    decoder = LineDecoder()

    lines = decoder.feed(f"{STATUS_LINE}\r\n{FAULT_LINE}\r\nSTALL_RESET,OK\r\n".encode())

    assert lines == [STATUS_LINE, FAULT_LINE, "STALL_RESET,OK"]


def test_mixed_crlf_and_lf() -> None:
    """CRLF와 LF가 섞여 와도 둘 다 종단으로 인식하고 CR/LF를 남기지 않는다."""
    decoder = LineDecoder()

    lines = decoder.feed(b"FIRST\r\nSECOND\nTHIRD\r\n")

    assert lines == ["FIRST", "SECOND", "THIRD"]


def test_only_one_trailing_cr_is_stripped() -> None:
    """줄 끝 CR은 하나만 제거한다 — 내용에 포함된 CR은 남는다."""
    decoder = LineDecoder()

    lines = decoder.feed(b"A\r\r\n")

    assert lines == ["A\r"]


def test_empty_lines_are_returned() -> None:
    """빈 줄도 ""로 반환한다 — 조용히 삼키지 않고 파서가 BLANK로 분류하게 한다."""
    decoder = LineDecoder()

    lines = decoder.feed(b"\r\n\n\r\nDATA\r\n")

    assert lines == ["", "", "", "DATA"]


def test_incomplete_last_line_is_held() -> None:
    """마지막 미완성 줄은 다음 feed까지 보관되고, 그 전에는 반환되지 않는다."""
    decoder = LineDecoder()

    lines = decoder.feed(f"{STATUS_LINE}\r\nFAULT,STALL".encode())

    assert lines == [STATUS_LINE]
    assert decoder.pending_bytes == len(b"FAULT,STALL")

    lines = decoder.feed(b",LEFT\r\n")

    assert lines == [FAULT_LINE]
    assert decoder.pending_bytes == 0


def test_empty_feed_returns_nothing() -> None:
    """빈 bytes를 넣어도 안전하며 보관 중인 내용이 바뀌지 않는다."""
    decoder = LineDecoder()
    decoder.feed(b"PARTIAL")

    assert decoder.feed(b"") == []
    assert decoder.pending_bytes == len(b"PARTIAL")


def test_lf_only_stream() -> None:
    """CR이 전혀 없는 LF 전용 스트림도 정상 처리된다."""
    decoder = LineDecoder()

    lines = decoder.feed(b"ONE\nTWO\nTHREE\n")

    assert lines == ["ONE", "TWO", "THREE"]


# ---------------------------------------------------------------------------
# 비ASCII / 손상 바이트
# ---------------------------------------------------------------------------


def test_non_ascii_bytes_do_not_raise() -> None:
    """비ASCII 바이트가 섞여도 예외 없이 줄을 반환한다(수신 루프 생존)."""
    decoder = LineDecoder()

    lines = decoder.feed(b"STAT\xffUS\r\n")

    assert len(lines) == 1
    assert "�" in lines[0]  # 손상 사실이 문자열에 남는다


def test_non_ascii_damage_does_not_break_following_lines() -> None:
    """손상된 줄 뒤의 정상 줄이 그대로 복원된다."""
    decoder = LineDecoder()

    lines = decoder.feed(b"\x80\x81\xfe\r\n" + f"{STATUS_LINE}\r\n".encode())

    assert len(lines) == 2
    assert lines[0] == "�" * 3
    assert lines[1] == STATUS_LINE


def test_null_bytes_are_decoded_not_dropped() -> None:
    """NUL 바이트도 예외 없이 처리된다(ASCII 범위이므로 그대로 남는다)."""
    decoder = LineDecoder()

    lines = decoder.feed(b"A\x00B\r\n")

    assert lines == ["A\x00B"]


# ---------------------------------------------------------------------------
# 최대 줄 크기 / overflow 복구
# ---------------------------------------------------------------------------


def test_default_max_line_bytes_is_256() -> None:
    """기본 최대 줄 크기는 256 bytes다."""
    assert DEFAULT_MAX_LINE_BYTES == 256
    assert LineDecoder().max_line_bytes == 256


def test_line_of_exactly_max_bytes_is_accepted() -> None:
    """정확히 256 bytes인 줄은 허용된다(경계값 포함)."""
    decoder = LineDecoder()
    line = "A" * 256

    lines = decoder.feed(line.encode() + b"\n")

    assert lines == [line]


def test_line_of_max_bytes_plus_one_is_discarded() -> None:
    """257 bytes인 줄은 폐기되어 반환되지 않는다."""
    decoder = LineDecoder()

    lines = decoder.feed(b"A" * 257 + b"\n")

    assert lines == []
    assert decoder.pending_bytes == 0


def test_oversized_line_does_not_leak_into_the_next_line() -> None:
    """★ 초과 줄의 잔여물이 다음 줄 앞에 붙지 않는다.

    단순히 버퍼만 비우면 `쓰레기잔여 + STATUS,...`가 한 줄로 조립돼 조용히 잘못
    파싱된다. 그래서 초과 시 다음 LF까지 버리는 discard 상태로 들어간다.
    """
    decoder = LineDecoder()

    # 상한을 넘기는 앞부분 (LF 없음) -> discard 상태 진입
    assert decoder.feed(b"B" * 300) == []
    assert decoder.is_discarding is True
    assert decoder.pending_bytes == 0

    # 잔여물 + LF 이후의 정상 줄
    lines = decoder.feed(b"GARBAGE_TAIL\r\n" + f"{STATUS_LINE}\r\n".encode())

    assert lines == [STATUS_LINE]  # 잔여 줄은 반환되지 않는다
    assert decoder.is_discarding is False


def test_discard_recovers_within_the_same_chunk() -> None:
    """★ 같은 feed 호출 안에서 초과 줄 뒤의 정상 줄이 복구된다."""
    decoder = LineDecoder()

    lines = decoder.feed(b"C" * 300 + b"\r\n" + f"{FAULT_LINE}\r\n".encode())

    assert lines == [FAULT_LINE]
    assert decoder.is_discarding is False
    assert decoder.pending_bytes == 0


def test_discard_spans_multiple_chunks_until_lf() -> None:
    """LF가 오기 전까지는 여러 chunk에 걸쳐 계속 버린다."""
    decoder = LineDecoder()

    assert decoder.feed(b"D" * 300) == []
    assert decoder.is_discarding is True
    assert decoder.feed(b"E" * 100) == []
    assert decoder.is_discarding is True
    assert decoder.feed(b"F" * 100) == []
    assert decoder.is_discarding is True

    lines = decoder.feed(b"TAIL\nOK_LINE\n")

    assert lines == ["OK_LINE"]
    assert decoder.is_discarding is False


def test_complete_oversized_line_does_not_enter_discard_state() -> None:
    """이미 LF까지 받은 초과 줄은 그 줄만 버리고 discard 상태로 들어가지 않는다."""
    decoder = LineDecoder()

    lines = decoder.feed(b"G" * 257 + b"\n" + b"NEXT\n")

    assert lines == ["NEXT"]
    assert decoder.is_discarding is False


def test_custom_max_line_bytes() -> None:
    """최대 줄 크기를 줄여도 같은 규칙(경계 허용 / 초과 폐기)이 적용된다."""
    decoder = LineDecoder(max_line_bytes=8)

    assert decoder.feed(b"12345678\n") == ["12345678"]
    assert decoder.feed(b"123456789\n") == []


def test_max_line_bytes_counts_trailing_cr() -> None:
    """상한은 LF 앞까지 쌓인 raw 바이트 기준이므로 종단 CR도 한 바이트로 센다.

    실제 STM 줄은 73byte 이하라 이 차이가 문제되지 않지만, 동작을 고정해 둔다.
    """
    accepted = LineDecoder(max_line_bytes=8)
    assert accepted.feed(b"1234567\r\n") == ["1234567"]  # 7 + CR = 8 -> 허용

    discarded = LineDecoder(max_line_bytes=8)
    assert discarded.feed(b"12345678\r\n") == []  # 8 + CR = 9 -> 폐기


# ---------------------------------------------------------------------------
# reset / 생성자·입력 검증
# ---------------------------------------------------------------------------


def test_reset_clears_partial_line() -> None:
    """reset()은 보관 중인 미완성 줄을 버린다."""
    decoder = LineDecoder()
    decoder.feed(b"PARTIAL_LINE")
    assert decoder.pending_bytes > 0

    decoder.reset()

    assert decoder.pending_bytes == 0
    # 이전 잔여물이 새 줄에 붙지 않는다
    assert decoder.feed(b"FRESH\r\n") == ["FRESH"]


def test_reset_clears_discard_state() -> None:
    """reset()은 discard 상태도 초기화한다."""
    decoder = LineDecoder()
    decoder.feed(b"H" * 300)
    assert decoder.is_discarding is True

    decoder.reset()

    assert decoder.is_discarding is False
    # discard가 풀렸으므로 LF 없이도 다음 줄이 정상 조립된다
    assert decoder.feed(b"FRESH\n") == ["FRESH"]


@pytest.mark.parametrize("max_line_bytes", [0, -1, -256])
def test_non_positive_max_line_bytes_raises_value_error(max_line_bytes: int) -> None:
    """생성자 최대 크기가 0 이하면 ValueError다."""
    with pytest.raises(ValueError, match="max_line_bytes"):
        LineDecoder(max_line_bytes=max_line_bytes)


@pytest.mark.parametrize("data", ["STATUS,1\r\n", 123, None, ["A"], 1.5, bytearray(b"A")])
def test_non_bytes_input_raises_type_error(data: object) -> None:
    """bytes가 아닌 입력은 TypeError다(str·bytearray를 그대로 넘기는 실수 포함)."""
    decoder = LineDecoder()

    with pytest.raises(TypeError, match="must be bytes"):
        decoder.feed(data)  # type: ignore[arg-type]


def test_decoder_module_imports_nothing_forbidden() -> None:
    """line_decoder.py가 pyserial·rclpy·ROS 메시지를 import하지 않는다(순수 모듈 보장).

    `sys.modules`를 보면 같은 프로세스의 다른 테스트가 rclpy를 올렸는지에 따라 결과가
    달라져 실행 순서에 의존한다. 그래서 **모듈 소스의 import 문 자체**를 검사한다.
    """
    import ast
    import pathlib

    import stm_serial_bridge.line_decoder as module

    source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    forbidden = {"serial", "rclpy", "std_msgs", "geometry_msgs", "stm_serial_bridge"}
    assert imported.isdisjoint(forbidden), f"금지된 import 발견: {imported & forbidden}"
