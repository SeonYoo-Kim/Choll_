"""수신 bytes → 완성된 줄 조립 — 버퍼 상태만 갖는 순수 모듈.

책임 분리:

- `SerialLink`               : 포트 I/O, raw bytes read/write
- **`LineDecoder`(이 모듈)** : 부분 수신 bytes 누적 → 완성된 줄
- `packet_parser.parse_packet()` : 완성된 str 한 줄 → 의미

pyserial·`rclpy`·ROS 메시지에 의존하지 않으며 포트를 직접 읽지도 않는다. 입력은
호출자가 넘겨주는 `bytes`뿐이므로 하드웨어 없이 단위 테스트할 수 있다.

USB Serial은 줄 경계를 지켜주지 않는다. STM이 `STATUS,...\r\n` 한 줄을 한 번에 써도
수신 측에서는 앞의 12byte만 먼저 오고 나머지가 다음 read에 올 수 있으며, 반대로 두 줄이
한 번에 붙어 올 수도 있다. 그래서 줄 조립은 반드시 상태를 가진 이 계층이 담당한다.

STM 통신 프로토콜 정본: embedded/motor/docs/serial_protocol.md
"""

# 줄 종단. STM은 CRLF로 보내지만(`status_reporter.c`) LF만 오는 경우도 받아들인다.
LINE_FEED = b"\n"
CARRIAGE_RETURN = b"\r"

# 디코딩 인코딩. 프로토콜이 ASCII 텍스트이므로 고정한다. 손상된 바이트는 예외를
#던지지 않고 U+FFFD로 치환해 "손상됐다"는 사실이 문자열에 남게 한다 — 수신 루프가
# 한 줄 때문에 죽으면 그 뒤의 정상 줄도 전부 잃는다.
LINE_ENCODING = "ascii"
DECODE_ERRORS = "replace"

# 한 줄이 가질 수 있는 최대 바이트 수(종단 LF 제외). STM의 가장 긴 줄인 STATUS가
# 최악의 경우 72byte(`status_reporter.c`의 버퍼 계산 근거)이므로 256이면 3배 이상
# 여유가 있다. 상한을 두는 이유는 종단 문자가 오지 않는 고장 상황에서 버퍼가
# 무한히 커지는 것을 막기 위함이다.
DEFAULT_MAX_LINE_BYTES = 256


class LineDecoder:
    """Accumulate received bytes and hand out complete lines.

    한 줄의 크기 상한을 넘기면 그 줄을 **폐기**하고, 그 줄의 다음 LF까지 버리는
    discard 상태로 들어간다. 단순히 버퍼만 비우면 남아 있던 뒷부분이 새 줄의 앞부분으로
    붙어 엉뚱한 줄이 만들어지기 때문이다 — 예를 들어 300byte 쓰레기 뒤에
    `STATUS,...`가 이어지면 `쓰레기잔여 + STATUS,...`가 한 줄로 조립돼 조용히
    잘못 파싱될 수 있다. LF를 만나면 discard를 풀고 그 다음 줄부터 정상 처리한다.

    상한 판정은 **LF 앞까지 버퍼에 쌓인 raw 바이트 수** 기준이다. 따라서 CRLF로 끝나는
    줄에서는 종단 CR도 한 바이트로 계산된다(내용 255byte + CR = 256 → 허용,
    내용 256byte + CR = 257 → 폐기). 실제 STM 줄은 73byte 이하라 이 차이가 문제되지 않는다.
    """

    def __init__(self, max_line_bytes: int = DEFAULT_MAX_LINE_BYTES) -> None:
        """Create a decoder with an empty buffer.

        Args:
            max_line_bytes: 한 줄의 최대 바이트 수(종단 LF 제외). 0보다 커야 한다.

        Raises:
            ValueError: `max_line_bytes`가 0 이하일 때.
        """
        if max_line_bytes <= 0:
            raise ValueError(
                f"max_line_bytes must be greater than 0, got {max_line_bytes}"
            )
        self._max_line_bytes = max_line_bytes
        self._buffer = bytearray()
        self._discarding = False

    @property
    def max_line_bytes(self) -> int:
        """한 줄의 최대 바이트 수."""
        return self._max_line_bytes

    @property
    def pending_bytes(self) -> int:
        """아직 완성되지 않은 줄로 보관 중인 바이트 수. 진단·테스트용."""
        return len(self._buffer)

    @property
    def is_discarding(self) -> bool:
        """상한 초과로 다음 LF까지 버리는 중이면 True. 진단·테스트용."""
        return self._discarding

    def reset(self) -> None:
        """Drop the partial line and clear the discard state.

        포트를 다시 열었을 때처럼 이전 스트림의 잔여물을 이어붙이면 안 되는 상황에서
        호출한다.
        """
        self._buffer.clear()
        self._discarding = False

    def feed(self, data: bytes) -> list[str]:
        """Accumulate bytes and return every line completed by this chunk.

        한 번의 호출에 여러 줄이 들어오면 **받은 순서대로 모두** 반환한다. 마지막 줄이
        LF로 끝나지 않으면 다음 `feed()`까지 보관한다.

        반환 문자열에는 CR/LF가 없다. 줄 끝의 CR은 **하나만** 제거하므로, 내용에 포함된
        CR(예: `A\\r\\r`)은 하나만 벗겨지고 나머지는 남는다.

        빈 줄도 `""`로 반환한다 — 버리지 않고 넘겨 `parse_packet()`이 `BLANK`로
        분류하게 한다. 조용히 삼키면 프레이밍 이상을 관측할 수 없다.

        어떤 바이트 내용에도 예외를 던지지 않는다(비ASCII 포함). 손상된 바이트는
        U+FFFD로 치환된다.

        Args:
            data: 방금 읽은 raw 바이트. `SerialLink.read_available()`의 반환값.

        Returns:
            이번 호출로 완성된 줄들. 완성된 것이 없으면 빈 리스트.

        Raises:
            TypeError: `data`가 bytes가 아닐 때. 호출 규약 위반이므로 조용히 넘기지 않는다.
        """
        if not isinstance(data, bytes):
            raise TypeError(f"data must be bytes, got {type(data).__name__}")

        lines: list[str] = []
        position = 0
        length = len(data)

        while position < length:
            if self._discarding:
                # 상한을 넘긴 줄의 잔여물을 버리는 중. 다음 LF를 찾으면 그 뒤부터
                # 같은 feed 호출 안에서 정상 처리를 재개한다.
                newline_index = data.find(LINE_FEED, position)
                if newline_index == -1:
                    return lines  # 이 chunk 전체가 버릴 잔여물이었다
                self._discarding = False
                position = newline_index + 1
                continue

            newline_index = data.find(LINE_FEED, position)
            if newline_index == -1:
                # 완성된 줄이 없다. 남은 바이트를 보관하되 상한을 넘으면 폐기로 전환한다.
                self._buffer.extend(data[position:])
                if len(self._buffer) > self._max_line_bytes:
                    self._buffer.clear()
                    self._discarding = True
                return lines

            self._buffer.extend(data[position:newline_index])
            position = newline_index + 1

            if len(self._buffer) > self._max_line_bytes:
                # 이미 LF를 소비했으므로 이 줄만 버리면 된다. discard 상태로 들어가지
                # 않고 다음 줄부터 곧바로 정상 처리한다.
                self._buffer.clear()
                continue

            lines.append(self._decode_line(bytes(self._buffer)))
            self._buffer.clear()

        return lines

    def _decode_line(self, raw_line: bytes) -> str:
        """Strip one trailing CR and decode the line as ASCII.

        Args:
            raw_line: LF를 제외한 한 줄의 raw 바이트.

        Returns:
            CR/LF가 없는 문자열. 디코딩할 수 없는 바이트는 U+FFFD로 치환된다.
        """
        if raw_line.endswith(CARRIAGE_RETURN):
            raw_line = raw_line[:-1]
        return raw_line.decode(LINE_ENCODING, errors=DECODE_ERRORS)
