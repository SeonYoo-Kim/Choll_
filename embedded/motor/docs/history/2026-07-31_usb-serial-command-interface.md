# USB Serial 명령 인터페이스 구현

- 날짜: 2026-07-31
- 관련 요약: [../current.md](../current.md)

## 구현 목적

기존 `motor-control` 프로젝트는 B1 버튼 입력과 자동 Forward/Backward/Turn 테스트
시퀀스(`AppTest_Process`)로만 모터를 구동했다. Jetson Orin이 `SET_WHEEL_VEL` /
`STOP` / `ESTOP` 세 명령을 USB Serial로 보내 원격 제어할 수 있도록, 기존
비블로킹 Event Loop(`App_Run` → `App_ProcessEvents` → `AppEventQueue`) 구조를
그대로 확장하는 형태로 통신 계층을 추가했다.

## 설계 이유

### 계층 분리 (SerialRx / CommandParser / Communication)
- ISR은 byte 하나를 ring buffer에 넣고 즉시 return해야 한다는 기존 원칙(B1 EXTI
  콜백과 동일 패턴)을 그대로 따르기 위해, byte 저장(`SerialRx`)과 파싱
  (`CommandParser`)과 조립/이벤트 등록(`Communication`)을 분리했다.
- `CommandParser`는 Motor/Controller/HAL을 전혀 몰라야 한다는 요구사항에 따라
  순수 문자열 → 구조체 변환만 담당한다. `sscanf` 대신 `strtof` + bounded
  parsing을 사용해 코드 크기와 입력 안전성(NaN/Infinity 거부, 여분 토큰 거부,
  `SET_WHEEL_VELOCITY`처럼 프리픽스만 비슷한 오입력 거부)을 확보했다.

### AppEvent payload와 SET_WHEEL_VELOCITY coalescing
- `AppEvent_t`에 `union { AppWheelVelocity_t wheel_velocity; } data`를 추가해
  기존 이벤트 큐 구조를 그대로 재사용했다.
- Orin이 20~30Hz로 `SET_WHEEL_VEL`을 반복 전송할 예정이므로, 큐에 이미 대기 중인
  동일 타입 이벤트가 있으면 새 슬롯을 늘리지 않고 값만 덮어쓰도록 했다(coalescing).
  이렇게 하면 큐 크기 16 중 대부분이 항상 비어 있어 STOP/ESTOP 이벤트가 밀려
  유실될 가능성이 구조적으로 낮아지므로, 별도의 "Emergency 우선 축출" 로직 같은
  복잡한 정책은 추가하지 않았다.

### StopController 3단계 분리 (Operational / Latched Safe / Emergency)
기존 `StopController`는 Normal/Emergency 두 단계만 있었고, `stopped` 플래그가
한 번 세팅되면 영구 래치되는 구조였다(B1 정지 후 재부팅 전까지 재구동 불가).
USB `STOP`은 "재이동 가능한 정지"여야 하므로 기존 구조를 그대로 쓸 수 없었다.
그래서 세 단계로 분리했다.

| 레벨 | 트리거 | Motor 호출 | 해제 |
|---|---|---|---|
| Operational Stop | USB `STOP`, 통신 Timeout | `Motor_NormalStop()` | 새 `SET_WHEEL_VEL` 수신 시 자동 해제 |
| Latched Safe Stop | B1 | `Motor_NormalStop()` | 재부팅 전까지 불가 |
| Emergency Stop | USB `ESTOP` | `Motor_EmergencyStop()`(PWM 0 + Driver Disable) | 재부팅 전까지 불가, `SET_WHEEL_VEL`도 무시 |

우선순위는 Emergency > Latched Safe > Operational이며, 상위 레벨 요청 시 대기 중인
하위 레벨 요청은 폐기한다(기존 "Emergency가 Normal보다 우선" 정책을 그대로 확장).
이벤트 이름도 `APP_EVENT_NORMAL_STOP` → `APP_EVENT_LATCHED_SAFE_STOP`으로 바꿔
B1과 USB `STOP`을 이름으로도 혼동하지 않도록 했다.

### MotionController와 Motor의 경계
`Motor_SetTargetWheelVelocity(left_rad_s, right_rad_s)`는 목표값을 저장만 하고
PWM에는 반영하지 않는다. Wheel Velocity PID가 아직 없는 상태에서 rad/s를 임의
비율로 PWM에 매핑하면 근거 없는 동작이 되므로, 사용자 지시에 따라 저장 단계까지만
구현했다. `MOTION_CONTROLLER_MAX_WHEEL_RAD_S` 상수와 clamp 적용 위치는
`motion_controller.c`에 TODO로 남겨두고, 하드웨어(기어비/바퀴 반지름/최대 RPM)가
확정되기 전까지는 값을 채우지 않기로 했다(사용자 명시적 결정).

### 통신 Timeout
`MotionController`가 마지막 유효 `SET_WHEEL_VEL` 수신 시각을 저장하고,
`HAL_GetTick()` 부호 없는 뺄셈으로 오버플로우에 안전하게 300ms 경과를 검사한다.
Timeout은 `APP_EVENT_COMMUNICATION_TIMEOUT`으로 큐에 1회만 발행되도록 래치했고,
새 유효 명령이 오면 래치가 풀린다. 부팅 직후(첫 명령 수신 전)에는 검사하지 않는다.

### App Mode 분리
기존 `AppTest_Process()`(자동 주행 테스트 시퀀스)가 USB 명령과 동시에 Motor를
제어하면 서로 덮어쓰는 문제가 있어, `APP_MODE_CURRENT`(기본값
`APP_MODE_REMOTE_CONTROL`, 빌드 옵션 `-DAPP_MODE_CURRENT=APP_MODE_SELF_TEST`로
재정의 가능)로 분리했다. 테스트 코드는 삭제하지 않고 게이팅만 추가했다.

### USART2 활성화 경위
`.ioc`에는 PA2/PA3가 `USART2_TX`/`USART2_RX`로 핀만 예약되어 있었고(Nucleo 보드
기본 ST-LINK VCP 핀), `Mcu.IP` 목록에는 USART2가 없어 실제로는 비활성 상태였다.
`Drivers/STM32F4xx_HAL_Driver`에도 UART HAL 드라이버 소스가 전혀 없었고
`stm32f4xx_hal_conf.h`의 `HAL_UART_MODULE_ENABLED`도 꺼져 있었다(CubeMX가 활성
IP에 대해서만 드라이버를 포함하는 방식이라 발생한 상태). 벤더 드라이버를 로컬
캐시(`STM32Cube_FW_F4_V1.28.3`)에서 수동 복사하는 방법도 있었지만, 사용자가
"표준 방식(CubeMX Generate Code)을 우선하고 싶다"고 명시해 사용자가 직접 CubeMX에서
USART2를 Asynchronous + NVIC 인터럽트로 활성화하고 코드를 재생성했다. 이후 그
결과물(`huart2`, `MX_USART2_UART_Init()`가 `usart.c/h` 분리 없이 `main.c`에 생성됨)
위에 통신 계층을 올렸다.

## 구현한 모듈

- `Application/Communication/serial_rx.h/.c` (신규)
- `Application/Communication/command_parser.h/.c` (신규)
- `Application/Communication/communication.h/.c` (신규)
- `Application/Controller/motion_controller.h/.c` (신규)
- `Application/Controller/stop_controller.h/.c` (수정 — 3단계 분리)
- `Application/Motor/motor.h/.c` (수정 — `Motor_SetTargetWheelVelocity` 추가)
- `Application/App/app_event.h/.c` (수정 — payload, coalescing, 이벤트 타입 확장)
- `Application/App/app.h/.c` (수정 — App Mode, App_Run 순서, 이벤트 라우팅)
- `Core/Src/main.c` (USER CODE 영역만 수정 — RX 초기 등록, `HAL_UART_RxCpltCallback`,
  `HAL_UART_ErrorCallback`, B1 콜백을 새 이벤트 payload 구조에 맞게 갱신)
- `motor_control.ioc` 및 CubeMX 자동 생성 파일 일체(USART2 관련) — 사용자가 CubeIDE에서 직접 생성

## 실제 검증 과정

1. 정적 코드 리뷰: `Read`로 각 파일을 직접 확인.
2. IDE 진단(CDT 인덱서) 오류 다수 발생 — `uint16_t`/`GPIOA` 등 파일 전역의
   기존 코드에도 나타나는 것으로 보아 인덱서 캐시 지연으로 판단하고, 실제
   구문 오류가 아님을 코드 재확인으로 교차 검증.
3. 사용자 요청에 따라 `arm-none-eabi-gcc`(CubeIDE 번들) 기반 커맨드라인
   syntax check는 **수행하지 않음** — 사용자가 CubeIDE에서 직접 빌드하기로 함.
4. UART RX 인터럽트 경로 재점검(사용자 요청): `HAL_UART_Receive_IT()` 최초
   무장 위치, `HAL_UART_RxCpltCallback()`의 재무장 여부, `huart2` 사용 일치
   여부를 `stm32f4xx_hal_uart.c` 소스와 대조해 확인.
   - 정상 수신 경로는 문제없음을 확인.
   - **버그 발견**: HAL은 UART 에러(프레이밍/패리티/노이즈/오버런) 발생 시
     `RxState`를 `READY`로 되돌리고 `HAL_UART_ErrorCallback()`을 호출하는데,
     이 콜백을 구현하지 않아 에러가 한 번이라도 발생하면 재부팅 전까지 수신이
     영구 중단되는 문제가 있었음. `HAL_UART_ErrorCallback()`을 추가해 에러 시에도
     `HAL_UART_Receive_IT()`를 재무장하도록 수정.

## 테스트 결과

### 코드 레벨

✓ 구현 완료

### 실기 검증

✓ CubeIDE Build 성공

✓ Tera Term를 통한 USB Serial 송신 확인

✓ CommandParser에서

SET_WHEEL_VEL,1.0,1.0

→ left=1.0

→ right=1.0

정상 파싱 확인

✓ AppEventQueue 전달 확인

✓ MotionController 전달 확인

✓ Motor_SetTargetWheelVelocity() 전달 확인

### 미검증

- PID
- PWM 출력
- 실제 모터 회전
- Timeout
- STOP
- ESTOP

## 다음 작업

1. CubeIDE 빌드(경고 포함 확인)
2. 실기 USB Serial 테스트 — 정상 주행(A/B), STOP 후 재개(C), ESTOP 래치(D),
   300ms Timeout(E), B1 Latched Stop(F), 잘못된 입력 방어(G)
3. Wheel Velocity PID 구현 및 `Motor_Process()`에 연결
4. 하드웨어 실측 후 `MOTION_CONTROLLER_MAX_WHEEL_RAD_S` 확정