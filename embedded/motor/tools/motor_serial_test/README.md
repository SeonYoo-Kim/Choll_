# motor_serial_test

STM32 모터 제어 보드(USB Virtual COM Port)에 `SET_WHEEL_VEL,<left_rad_s>,<right_rad_s>\r\n`
명령을 키보드로 수동 전송하고, STM32가 UART Protocol v1([../../docs/serial_protocol.md](../../docs/serial_protocol.md))에
따라 보내는 STATUS Packet(목표/실제 속도, PWM, 엔코더)을 실시간으로 표시하는 Windows 전용
테스트 도구입니다. `G` 키로 `SET_PI_GAINS,<kp>,<ki>`를 전송해 PI 게인을 Build/Flash 없이
튜닝할 수도 있고(응답 파싱/화면 표시/CSV 로깅 포함), `[`/`]` 키로는 입력 모드 없이 Kp만
±0.05씩 즉시 증감시켜 반복 튜닝을 더 빠르게 할 수 있습니다. Tera Term을 매번 수동으로 설정하고
명령을 타이핑하는 번거로움을 줄이고, STM 내부 상태를 콘솔에서 바로 확인하기 위해 만들었습니다.

STM32 쪽 통신 타임아웃이 약 5초이므로, 정지 상태가 아닌 동안에는 기본 20Hz로 명령을 계속
반복 전송합니다.

## 설치

Windows PowerShell 또는 cmd에서:

```powershell
pip install -r requirements.txt
```

`msvcrt`는 Windows Python 표준 라이브러리에 포함되어 있어 별도 설치가 필요 없습니다.
이 도구는 `msvcrt` 기반이므로 Windows에서만 동작합니다.

## 실행

```powershell
python motor_test.py --port COM6
python motor_test.py --port COM6 --speed 2.0 --rate 20
```

STM32가 어떤 COM 포트로 열리는지는 Windows 장치 관리자의
"포트(COM & LPT)" 항목에서 확인할 수 있습니다.

### 명령행 인자

| 인자 | 기본값 | 설명 |
|---|---|---|
| `--port` | (필수) | STM32 Virtual COM Port, 예: `COM6` |
| `--baud` | `115200` | Baud rate |
| `--rate` | `20` | 명령 전송 주기(Hz) |
| `--speed` | `1.0` | 키 입력에 사용할 목표 각속도(rad/s) |
| `--log` | (없음) | STATUS Packet을 `logs/날짜_시간.csv`에 기록(Kp/Ki 튜닝용, 아래 "CSV 로깅" 참고) |

## 키 조작

| 키 | 동작 |
|---|---|
| `W` | 전진 (left=speed, right=speed) |
| `S` | 후진 (left=-speed, right=-speed) |
| `A` | 제자리 좌회전 (left=-speed, right=speed) |
| `D` | 제자리 우회전 (left=speed, right=-speed) |
| `Space` | 정지 — `SET_WHEEL_VEL,0,0`을 20Hz 주기로 반복 전송 (left=0, right=0) |
| `X` | **STOP** 명령을 즉시 1회 전송 (Operational Stop) |
| `E` | **ESTOP** 명령을 즉시 1회 전송 (Emergency Stop, 재부팅 전까지 해제 안 됨) |
| `G` | **Kp/Ki 입력 모드** 진입(비블로킹, 아래 "Kp/Ki 입력 모드(G)" 참고) |
| `[` | Kp를 **-0.05**하고 즉시 `SET_PI_GAINS` 전송(Ki는 유지, 아래 "Kp 빠른 증감([/])" 참고) |
| `]` | Kp를 **+0.05**하고 즉시 `SET_PI_GAINS` 전송(Ki는 유지, 아래 "Kp 빠른 증감([/])" 참고) |
| `Q` 또는 `Ctrl+C` | 프로그램 종료 |

W/S/A/D/Space는 한 번 누르면 다른 키를 누르기 전까지 해당 명령이 계속 지정한
주기로 반복 전송됩니다. 종료 시 `SET_WHEEL_VEL,0,0` 정지 명령을 여러 번 전송한
뒤 포트를 닫습니다.

`X`/`E`는 W/A/S/D/Space와 근본적으로 다릅니다 — `SET_WHEEL_VEL`의 좌우 속도
계산을 거치지 않고, UART Protocol v1의 `STOP`/`ESTOP` 문자열을 키를 누른 그
순간 딱 한 번만 전송합니다([../../docs/serial_protocol.md](../../docs/serial_protocol.md) 참고).
`E`(ESTOP)를 보내면 화면의 요청 속도도 즉시 0으로 초기화되지만, 이는 표시용일
뿐입니다 — 실제로 STM32가 재부팅 전까지 모터를 재활성화하지 않는 것은 STM 쪽
StopController가 보장합니다. 이후 `W`/`A`/`S`/`D`를 눌러도(Python Tool은 계속
`SET_WHEEL_VEL`을 전송하지만) STM이 이를 무시하므로 실제로 움직이지 않습니다.

### ESTOP 실기 테스트 순서

1. `python motor_test.py --port COM6`로 실행하고 `W` 등으로 모터를 움직여 정상
   동작을 확인합니다.
2. `E`를 눌러 ESTOP을 전송합니다. 모터가 즉시 멈추고(PWM 0 + BTS7960 Enable
   차단), 화면 Command 줄이 `Emergency Stop`으로 바뀌는지 확인합니다.
3. `W`/`A`/`S`/`D`를 눌러도 모터가 움직이지 않는지 확인합니다(Python Tool은
   `SET_WHEEL_VEL`을 계속 보내지만 STM이 무시해야 정상입니다).
4. STM32 보드를 재부팅(또는 리셋 버튼)한 뒤에만 다시 정상 동작하는지 확인합니다.

### Kp/Ki 입력 모드 (G)

`G`를 누르면 `SET_PI_GAINS,<kp>,<ki>` 명령([../../docs/serial_protocol.md](../../docs/serial_protocol.md)
SET_PI_GAINS 절 참고)을 보내기 위한 입력 모드로 들어갑니다. `input()`처럼 프로그램
전체가 멈추는 방식이 아니라, 기존 `msvcrt` 기반 non-blocking 폴링 구조 그대로 한
글자씩 입력을 받는 상태 기반(state machine) 모드입니다 — 이 모드 중에도 20Hz
`SET_WHEEL_VEL` 전송과 STATUS Packet 수신/화면 갱신은 계속 동작합니다.

1. `G`를 누르면 화면 하단 `PI Gains` 블록이 `Input Kp: _`로 바뀝니다. 숫자/`.`/`-`를
   입력하면 그 자리에 그대로 표시되고, `Backspace`로 마지막 글자를 지울 수 있습니다.
2. `Enter`를 누르면 Kp가 확정되고 `Input Ki: _`로 넘어갑니다. 입력한 문자열이 올바른
   숫자가 아니면(예: 빈 입력, `-`만 입력) 조용히 무시되고 같은 자리에서 계속 수정할
   수 있습니다.
3. Ki도 `Enter`로 확정하면 그 즉시 `SET_PI_GAINS,<kp>,<ki>\r\n`을 1회 전송하고
   입력 모드가 종료됩니다(`SET_WHEEL_VEL`처럼 반복 전송하지 않습니다).
4. STM32 응답에 따라 `PI Gains` 블록이 갱신됩니다:
   - `PI_GAINS,<kp>,<ki>` 응답 → `Applied : Kp=... Ki=...`에 반영
   - `ERROR,SET_PI_GAINS,<reason>` 응답(`INVALID_FORMAT`/`OUT_OF_RANGE`) → `Error : <reason>`으로 표시,
     `Applied` 값은 바뀌지 않습니다(적용 실패했으므로).

입력 모드 중에도 `E`는 예외적으로 그 자리에서 즉시 동작합니다 — 입력하던 내용을
버리고 **ESTOP을 전송 + 입력 모드를 취소**합니다(실기 안전 우선). `Ctrl+C`도 언제나
프로그램을 즉시 종료시킵니다(`msvcrt` 폴링과 무관하게 OS 시그널로 처리되기 때문).
그 외 `W`/`A`/`S`/`D`/`X`/`Q` 등은 입력 모드 중에는 숫자 입력으로 취급되지 않는 한
아무 동작도 하지 않습니다(모드를 벗어난 뒤 다시 사용 가능).

### Kp 빠른 증감 ([/])

`G` 입력 모드로 매번 두 값을 다 타이핑하지 않아도, `[`/`]`를 누르면 **Kp만** 0.05씩
바꿔 그 자리에서 바로 `SET_PI_GAINS`를 전송합니다 — Kp를 조금씩 여러 번 반복
조정하는 실기 튜닝 상황을 더 빠르게 하기 위한 단축키입니다. `G` 입력 모드와는
독립적인 별개의 기능이며 둘 다 그대로 사용할 수 있습니다.

- `]`: 현재 Kp + 0.05, `[`: 현재 Kp - 0.05. Ki는 항상 직전 값을 그대로 실어
  보냅니다(바뀌지 않습니다).
- "현재 Kp/Ki"는 이 세션에서 마지막으로 `PI_GAINS` ACK를 받은 값(아직 응답을
  기다리는 중이면 그 요청값)을 기준으로 삼습니다. 이 세션에서 `SET_PI_GAINS`를
  한 번도 보낸 적이 없으면 STM 기본값인 `0.0`을 기준으로 계산합니다.
- Kp는 STM이 허용하는 범위(`MOTOR_PI_KP_MIN`~`MOTOR_PI_KP_MAX` = `0.0`~`50.0`,
  [../../docs/serial_protocol.md](../../docs/serial_protocol.md) SET_PI_GAINS 절 참고)를
  벗어나지 않도록 전송 전에 Python 쪽에서도 clamp합니다. 이미 한계값이면 계속 눌러도
  같은 값을 다시 보낼 뿐 범위를 벗어나지 않습니다.
- 응답 처리는 `G` 입력과 완전히 동일합니다: `PI_GAINS,<kp>,<ki>` ACK를 받으면
  `PI Gains` 블록의 `Applied`와(`--log` 사용 시) CSV의 `kp`/`ki` 컬럼이 갱신되고,
  `ERROR,SET_PI_GAINS,<reason>`을 받으면 `Error : <reason>`만 표시될 뿐 Kp 값은
  바뀌지 않습니다.
- `[`/`]`는 `G` 입력 모드 **중에는** 동작하지 않습니다(그 안에서는 숫자 버퍼 문자로
  취급되지 않아 무시됩니다) — 입력 모드를 벗어난 뒤 다시 사용할 수 있습니다.

## STATUS Packet 표시

명령 전송 주기(`--rate`)에 맞춰 화면 한 자리에 아래와 같은 블록을 갱신합니다
(STM32가 아직 STATUS Packet을 보내지 않았다면 값 자리에 `--`가 표시됩니다):

```
Command     FORWARD    L=+1.00 R=+1.00
--------------------------------------------------
Target
  L : 2.00
  R : 2.00

Actual
  L : 1.95
  R : 1.97

Error
  L : +0.05
  R : +0.03

PWM
  L : 36
  R : 37

Encoder
  L : 15231
  R : 15188

PI Gains
  Applied : Kp=0.5000 Ki=0.0000
  (G:Kp/Ki 직접 입력  [/]:Kp ±0.05)
--------------------------------------------------
```

`Error = Target - Actual`이며 Python Tool에서만 계산해 표시합니다(STM은 Error를
사용/전송하지 않습니다). `Actual`은 STM32가 엔코더 실측값으로 계산해 보내는
값입니다([../../docs/serial_protocol.md](../../docs/serial_protocol.md) 참고).

`PI Gains` 블록의 `Applied`는 이 Python Tool 세션이 `PI_GAINS` ACK를 마지막으로
받은 값입니다. 프로그램을 새로 시작한 직후처럼 이 세션에서 ACK를 한 번도 받은 적이
없으면 `--`로 표시됩니다 — STM32의 실제 현재 Kp/Ki를 조회하는 명령(`GET_PI_GAINS`)은
아직 없어서, Tera Term 등 다른 경로로 이미 바뀐 값을 Python Tool이 알 방법이 없기
때문입니다(임의로 `0.0`을 가정해 표시하지 않습니다).

## CSV 로깅 (Kp/Ki 튜닝용)

`--log`를 주면 실행 시 `logs/날짜_시간.csv`(스크립트 위치 기준 상대경로, 폴더가
없으면 자동 생성)를 만들고, STATUS Packet을 받을 때마다(화면 갱신 주기와 무관하게)
한 줄씩 기록합니다.

컬럼: `timestamp, left_target, left_actual, left_error, left_pwm, right_target,
right_actual, right_error, right_pwm, kp, ki`

- `timestamp`는 로깅 시작 시점부터의 경과 초(모노토닉)입니다.
- `kp`/`ki`는 그 STATUS 행 시점에 마지막으로 `PI_GAINS` ACK를 받은 적용값입니다.
  이 세션에서 아직 `SET_PI_GAINS` ACK를 한 번도 못 받았으면 빈 칸으로 남습니다 —
  ACK를 받은 **이후의 STATUS 행부터** 값이 채워지기 시작합니다.

```powershell
python motor_test.py --port COM6 --log
```

## 코드 구조

추후 ROS2 Serial Bridge 패키지에서 재사용하기 쉽도록 역할별로 분리되어 있습니다
(`motor_test.py`):

- `SerialConnection`: 시리얼 포트 연결/해제 + 비블로킹 수신, 예외를 `ConnectionError`로 정규화
- `build_wheel_vel_command()`: `SET_WHEEL_VEL` 명령 문자열 생성
- `build_stop_command()` / `build_estop_command()`: `STOP`/`ESTOP` 명령 문자열 생성(X/E 키 전용)
- `build_set_pi_gains_command()`: `SET_PI_GAINS` 명령 문자열 생성(G 입력 모드 전용)
- `StatusPacket` / `parse_status_packet()`: STATUS Packet 한 줄을 파싱하는 순수 함수
- `PiGainsAck` / `parse_pi_gains_ack()`, `parse_pi_gains_error()`: `PI_GAINS`/`ERROR,SET_PI_GAINS,...`
  응답 한 줄을 파싱하는 순수 함수
- `StatusReceiver`: 수신 바이트를 줄 단위로 조립해 최신 STATUS Packet을 보관하고,
  STATUS/`PI_GAINS`/`ERROR,SET_PI_GAINS` 각각에 대해 콜백을 호출(CSV 로깅, PI Gains 상태 갱신)
- `StatusDisplay`: Command 상태 + 최신 STATUS Packet(+ Error 계산) + PI Gains 상태를 콘솔에 보기 좋게 갱신
- `StatusLogger` / `make_log_path()`: `--log` CSV 로깅(`logs/날짜_시간.csv`, kp/ki 컬럼 포함)
- `MotionState`: 현재 목표 동작(좌우 rad/s)을 스레드 안전하게 보관. `set_action()`은 W/A/S/D/Space 전용,
  `force_zero()`는 X/E 전송 직후 좌우를 0으로 강제하고 임의의 라벨(Operational/Emergency Stop)을 표시하는 용도
- `GainInputState`: G 입력 모드의 상태 기계(Kp 입력 중 / Ki 입력 중 / 비활성). 한 글자씩 들어오는
  키를 버퍼에 누적하고, Kp/Ki가 모두 확정되면 `(kp, ki)`를 반환
- `PiGainsState`: `SET_PI_GAINS`의 적용됨(Applied)/응답 대기(Pending)/오류(Error) 상태를 보관,
  화면 표시와 CSV 로깅이 함께 참조. `best_known_kp()`/`best_known_ki()`는 `[`/`]` 단축키가 증감의
  기준으로 삼는 "현재 값"을 계산(Pending > Applied > STM 기본값 0.0 우선순위)
- `KeyboardReader`: `msvcrt` 기반 non-blocking 키 입력 폴링. `poll()`은 `PROTOCOL_COMMAND_KEYS`(X/E),
  `KEY_ACTIONS`(W/A/S/D/Space), G(`start_gain_input`), `[`/`]`(`kp_nudge`)를 구분해 반환하고,
  `read_raw()`는 G 입력 모드 중 키 매핑 해석 없이 원본 문자를 그대로 반환
- `run()`: 20Hz(기본) 반복 전송 + STATUS Packet 수신 + 키 입력 처리 메인 루프. X/E는 이 루프의
  20Hz 주기를 기다리지 않고 즉시 전송. G 입력 모드 중에는 `KeyboardReader.poll()` 대신 `read_raw()`로
  분기하지만, 20Hz 전송/STATUS 수신/화면 갱신은 그대로 계속된다. `[`/`]`는 G 모드 밖(`poll()` 경로)에서만
  처리되며, `PiGainsState.best_known_kp()`에 ±`GAIN_KP_STEP`을 적용해 `MOTOR_PI_KP_MIN/MAX`로
  clamp한 뒤 즉시 전송한다(응답 처리는 G 입력과 동일한 `pi_gains` 콜백 경로 공유)
- `safe_stop()`: 종료 시 정지 명령(`SET_WHEEL_VEL,0,0`) 반복 전송 — X/E와는 별개의 기존 로직
- `main()`: 인자 파싱, 연결, 예외 처리, 종료 정리

## 오류 처리

- 포트를 열 수 없거나 다른 프로그램이 점유 중이면 실행 시작 시 명확한 오류
  메시지를 출력하고 종료 코드 1로 종료합니다.
- 실행 중 케이블 분리 등으로 연결이 끊기면 오류 메시지를 출력하고 정지 명령
  전송을 시도한 뒤 안전하게 종료합니다.
