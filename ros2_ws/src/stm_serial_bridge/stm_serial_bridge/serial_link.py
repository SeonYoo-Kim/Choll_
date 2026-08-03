"""USB Serial 담당 모듈 — 포트 열기/닫기와 raw bytes 송수신만 책임진다.

pyserial을 import하는 유일한 모듈이다. `rclpy`·ROS 메시지·ROS 파라미터에 의존하지
않으므로, 하드웨어 없이 Linux PTY(`pty.openpty()`)만으로 단위 테스트할 수 있다.

구현 단계 8b 범위: **연결(open/close) + 송신(write) + 수신(read_available)까지.**
수신은 **raw bytes만** 다룬다 — 줄 조립은 `line_decoder.LineDecoder`, 한 줄의 의미
해석은 `packet_parser.parse_packet()`이 담당한다. 수신 스레드나 별도 write 스레드는
만들지 않는다(호출자가 ROS2 타이머에서 폴링한다).

    SerialLink        : 포트 I/O, raw bytes read/write
    LineDecoder       : 부분 수신 bytes 누적 → 완성된 줄
    parse_packet()    : 완성된 str 한 줄 → 의미

STM 통신 프로토콜 정본: embedded/motor/docs/serial_protocol.md
"""

import serial

# STM32 CommandParser는 ASCII 텍스트 줄만 파싱한다. 인코딩을 고정해 두면 어떤
# 로케일에서 실행해도 같은 바이트가 나간다.
COMMAND_ENCODING = "ascii"

# STM32와의 UART 설정. 프로토콜 정본의 "115200 8N1"에 맞춘다.
# baud_rate만 호출자가 지정하고 나머지 프레이밍은 여기서 고정한다.
SERIAL_BYTESIZE = serial.EIGHTBITS
SERIAL_PARITY = serial.PARITY_NONE
SERIAL_STOPBITS = serial.STOPBITS_ONE

# 비블로킹 동작을 위해 0.0으로 둔다. 5a에는 read/write가 없지만, 이후 단계에서
# ROS2 타이머 콜백을 이 값 때문에 블로킹시키지 않기 위한 설정이다.
SERIAL_TIMEOUT_SEC = 0.0

# Hardware flow control은 사용하지 않는다(STM32 쪽 USART2도 RTS/CTS를 쓰지 않는다).
SERIAL_RTSCTS = False
SERIAL_DSRDTR = False
SERIAL_XONXOFF = False


class SerialLinkError(RuntimeError):
    """Serial 포트 연결에 실패했을 때 발생한다.

    pyserial의 예외(`serial.SerialException`, `OSError` 등)를 호출자에게 그대로
    흘리지 않고 이 타입으로 감싼다 — 호출자가 pyserial을 import하지 않고도 오류를
    처리할 수 있게 하기 위함이다.
    """


class SerialLink:
    """Own the lifetime of a single pyserial connection.

    생성자는 포트를 열지 않는다. 설정값만 검증해 보관하고, `open()`을 호출할 때만
    실제 장치를 연다 — 객체를 만드는 것과 하드웨어를 점유하는 것을 분리해, 호출자가
    "열지 않기로 결정"할 수 있게 하기 위함이다(dry-run 모드).
    """

    def __init__(self, port: str, baud_rate: int) -> None:
        """Validate and store the connection settings without opening the port.

        Args:
            port: Serial 장치 경로 (예: `/dev/ttyACM0`).
            baud_rate: 통신 속도 (bps). STM32는 115200을 사용한다.

        Raises:
            ValueError: `port`가 비어 있거나 공백뿐일 때, 또는 `baud_rate`가 0 이하일 때.
        """
        if not port or not port.strip():
            raise ValueError(f"port must be a non-empty path, got {port!r}")
        if baud_rate <= 0:
            raise ValueError(f"baud_rate must be greater than 0, got {baud_rate}")

        self._port = port
        self._baud_rate = baud_rate
        self._serial: serial.Serial | None = None

    @property
    def port(self) -> str:
        """Serial 장치 경로."""
        return self._port

    @property
    def baud_rate(self) -> int:
        """통신 속도 (bps)."""
        return self._baud_rate

    @property
    def is_open(self) -> bool:
        """포트가 현재 열려 있으면 True."""
        return self._serial is not None and self._serial.is_open

    def open(self) -> None:
        """Open the serial port.

        이미 열려 있으면 아무 것도 하지 않는다(멱등) — 중복 open으로 기존 연결을
        잃거나 장치를 두 번 점유하지 않게 하기 위함이다.

        Raises:
            SerialLinkError: 포트를 열 수 없을 때. 메시지에 port·baud_rate와 원래
                실패 이유를 함께 담는다.
        """
        if self.is_open:
            return

        try:
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baud_rate,
                bytesize=SERIAL_BYTESIZE,
                parity=SERIAL_PARITY,
                stopbits=SERIAL_STOPBITS,
                timeout=SERIAL_TIMEOUT_SEC,
                write_timeout=SERIAL_TIMEOUT_SEC,
                rtscts=SERIAL_RTSCTS,
                dsrdtr=SERIAL_DSRDTR,
                xonxoff=SERIAL_XONXOFF,
            )
        except (serial.SerialException, OSError, ValueError) as error:
            # 실패한 객체를 들고 있으면 is_open 판정이 애매해지므로 참조를 지운다.
            self._serial = None
            raise SerialLinkError(
                f"Serial port open failed: port={self._port}, "
                f"baud_rate={self._baud_rate}, reason={error}"
            ) from error

    def write(self, data: str) -> None:
        """Write exactly one command frame to the already-open serial port.

        전달받은 문자열을 **그대로** ASCII 인코딩해 보낸다 — CRLF를 붙이거나 내용을
        바꾸지 않는다. 종단 문자는 호출자(`protocol.build_*`)가 이미 포함시킨다.

        `flush()`는 호출하지 않는다. pyserial의 `write()`는 OS 송신 버퍼까지 넘기고,
        `write_timeout`이 설정돼 있어 버퍼가 막히면 예외로 드러난다 — 20Hz 타이머
        콜백에서 굳이 드레인을 기다릴 이유가 없다.

        Args:
            data: 보낼 명령 한 줄. CRLF 종단을 포함한 ASCII 문자열이어야 한다.

        Raises:
            TypeError: `data`가 str이 아닐 때.
            ValueError: `data`가 빈 문자열이거나 ASCII로 인코딩할 수 없을 때.
            SerialLinkError: 포트가 열려 있지 않을 때, pyserial이 실패했을 때,
                또는 기록된 바이트 수가 payload 길이보다 적을 때(partial write).
        """
        if not isinstance(data, str):
            raise TypeError(f"data must be str, got {type(data).__name__}")
        if not data:
            raise ValueError("data must not be empty")

        try:
            payload = data.encode(COMMAND_ENCODING)
        except UnicodeEncodeError as error:
            raise ValueError(
                f"data must be {COMMAND_ENCODING}-encodable, got {data!r}"
            ) from error

        # 포트 상태 확인은 pyserial 호출 전에 한다 — self._serial이 None이면
        # AttributeError가 나고, 닫힌 포트면 pyserial 예외 종류가 버전마다 달라진다.
        if not self.is_open:
            raise SerialLinkError(
                f"Serial write failed: port={self._port}, "
                f"baud_rate={self._baud_rate}, reason=port is not open"
            )

        try:
            written = self._serial.write(payload)
        except (serial.SerialTimeoutException, serial.SerialException, OSError) as error:
            raise SerialLinkError(
                f"Serial write failed: port={self._port}, "
                f"baud_rate={self._baud_rate}, reason={error}"
            ) from error

        # pyserial은 write_timeout이 걸리면 보통 예외를 던지지만, 구현/플랫폼에 따라
        # 기록한 바이트 수만 반환할 수도 있다. 명령이 절반만 나가면 STM 쪽 줄 조립이
        # 깨져 엉뚱한 목표 속도로 해석될 수 있으므로 반드시 길이를 확인한다.
        if written is None or written < len(payload):
            raise SerialLinkError(
                f"Serial write failed: port={self._port}, "
                f"baud_rate={self._baud_rate}, "
                f"reason=partial write ({written} of {len(payload)} bytes)"
            )

    def read_available(self) -> bytes:
        """Read whatever bytes are already waiting on the port. Non-blocking.

        **raw bytes만 다룬다.** 디코딩·줄 조립·패킷 해석을 하지 않는다 — 줄 조립은
        `line_decoder.LineDecoder`, 의미 해석은 `packet_parser.parse_packet()`의 책임이다.
        이 계층을 섞으면 부분 수신 처리와 포트 오류 처리가 한 덩어리가 되어 테스트가
        어려워진다.

        대기 중인 데이터가 없으면 `b""`를 반환한다(오류가 아니다). 20Hz 타이머 콜백에서
        호출되므로 절대 블로킹하지 않아야 하며, 포트를 `timeout=0.0`으로 열어 이를 보장한다.

        **부분 read는 오류가 아니다.** `in_waiting`이 알려준 만큼 다 읽히지 않아도 읽힌
        바이트만 그대로 반환하고, 나머지는 다음 호출에서 읽는다. STM은 27~73byte 줄을
        10Hz로 보내므로 한 줄이 여러 호출에 걸쳐 도착하는 것이 정상이다.

        Returns:
            지금 읽어낸 바이트. 대기 중 데이터가 없으면 `b""`.

        Raises:
            SerialLinkError: 포트가 열려 있지 않을 때, 또는 `in_waiting` 조회나
                `read()`가 실패했을 때. 메시지에 port·baud_rate와 원래 이유를 담는다.
        """
        # 포트 상태 확인을 pyserial 호출 전에 한다 — write()와 같은 이유다.
        if not self.is_open:
            raise SerialLinkError(
                f"Serial read failed: port={self._port}, "
                f"baud_rate={self._baud_rate}, reason=port is not open"
            )

        try:
            pending = self._serial.in_waiting
        except (serial.SerialException, OSError) as error:
            raise SerialLinkError(
                f"Serial read failed: port={self._port}, "
                f"baud_rate={self._baud_rate}, reason={error}"
            ) from error

        if not pending:
            return b""

        try:
            received = self._serial.read(pending)
        except (serial.SerialException, OSError) as error:
            raise SerialLinkError(
                f"Serial read failed: port={self._port}, "
                f"baud_rate={self._baud_rate}, reason={error}"
            ) from error

        # pyserial은 bytes를 반환하지만, timeout=0.0에서 아무것도 못 읽으면 None을
        # 돌려주는 구현도 있어 방어한다. 부분 read와 마찬가지로 오류로 보지 않는다.
        if received is None:
            return b""
        return bytes(received)

    def close(self) -> None:
        """Close the serial port if it is open.

        열려 있지 않거나 이미 닫힌 상태에서 호출해도 안전하다(멱등). 종료 경로에서
        호출되므로 여기서 예외를 새로 만들지 않고, pyserial의 close 예외만 그대로
        올려보낸다 — 호출자가 종료 정리를 계속할 수 있도록 감싸는 책임은 호출자에게 둔다.
        """
        if self._serial is None:
            return

        try:
            if self._serial.is_open:
                self._serial.close()
        finally:
            self._serial = None
