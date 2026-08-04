# UART Protocol v1

USART2(ST-LINK VCP), 115200 8N1. 이 문서는 STM32 ↔ PC(현재는 `tools/motor_serial_test`,
향후 ROS2 Serial Bridge/Jetson/Logger/Debug Tool 포함) 사이의 공식 UART 명령/상태 형식이다.

## PC → STM

### 구현됨 (`Application/Communication/command_parser.c`에서 실제로 파싱)

```
SET_WHEEL_VEL,<left_rad_s>,<right_rad_s>
STOP
ESTOP
SET_PI_GAINS,<kp>,<ki>
RESET_STALL
```

### SET_PI_GAINS

```
SET_PI_GAINS,<kp>,<ki>
```

PI Speed Controller의 Kp/Ki를 Build/Flash 없이 런타임에 갱신한다(`Application/Motor/motor.c`의
`motor_pi_kp`/`motor_pi_ki` 전역 변수, [PI Speed Control](#pi-speed-control) 절 참고).

필드 의미:

| 필드 | 의미 | 허용 범위 |
|------|------|------|
| kp   | Proportional 게인 | `MOTOR_PI_KP_MIN`~`MOTOR_PI_KP_MAX` = `0.0`~`50.0` (`motor_config.h`) |
| ki   | Integral 게인 | `MOTOR_PI_KI_MIN`~`MOTOR_PI_KI_MAX` = `0.0`~`20.0` (`motor_config.h`) |

⚠️ **실기 튜닝 전 잠정값**: 위 상한은 실측 데이터가 아니라 Feedforward 게인
(`MOTOR_OPEN_LOOP_PWM_PER_RAD_S = 10.0f`)과 Anti-Windup Integral Clamp
(`MOTOR_PI_INTEGRAL_PWM_LIMIT`, `MOTOR_PWM_MAX`의 절반)를 근거로 한 보수적 추정치다
(선정 이유는 `motor_config.h`의 해당 매크로 주석 참고). 실기 튜닝 결과 부족하다고
판단되면 `motor_config.h`의 이 네 매크로만 조정한다.

- 음수 게인은 거부한다(피드백 발산 방지).
- 정상 적용 시 좌우 PI Integral 상태만 0으로 초기화된다(요청 속도/Speed Profile/Direction
  Change 상태는 그대로 유지). `Motor_SetPiGains()` 참고.
- 처리는 `AppEventQueue`를 거치지 않고 `Communication_HandleCompleteLine()`에서 즉시
  수행된다 — 재전송에 기대는 `SET_WHEEL_VEL`과 달리 1회성 명령이라 큐 드롭 시 응답
  없이 조용히 실패하는 것을 피하기 위함이다.

예시:

```
SET_PI_GAINS,0.5,0.0
```

응답 형식은 아래 [PI_GAINS Ack / Error](#pi_gains-ack--error) 절 참고.

### RESET_STALL

```
RESET_STALL
```

[Stall Detection](#stall-detection) 절에서 확정된 **Stall Fault만** 해제한다. STOP/ESTOP과
동일하게 필드 없이 문자열 전체가 일치해야 파싱된다.

- **Fault 해제 ≠ 재출발.** 성공해도 모터는 정지 상태(target 0)를 그대로 유지한다. Stall
  원인/디바운스 타이머만 초기화되며, 이전 requested/limited target 복원, Speed Controller
  자동 재활성화, PI Integral 복원은 전혀 하지 않는다(`Motor_ClearStall()`). 또한
  `MotionController_ResetTarget()`이 함께 호출되어 Stall 이전에 마지막으로 받은
  `SET_WHEEL_VEL` 목표값도 0으로 지워진다 — 그렇지 않으면 Fault가 풀리는 순간 오래된
  target이 그대로 Motor에 전달되어 자동으로 다시 가속될 수 있기 때문이다. **재출발은
  이 명령 이후 별도의 새 `SET_WHEEL_VEL`을 받아야만** 이뤄지며, 그 경우에도 Speed
  Profile을 거쳐 0부터 가속한다(`MOTOR_ACCEL_LIMIT_RAD_S2` 등 기존 제한 그대로 적용).
- **Emergency Stop 또는 Latched Safe Stop(NUCLEO B1)이 걸려 있으면 거부된다** — Stall만
  지워지고 그 두 상태는 그대로 유지된다(뒷문으로 풀리지 않음, `StopController_ClearStall()`).
  이 두 상태는 기존 정책대로 재부팅 또는 B1 하드웨어 동작으로만 해제된다.
- Stall이 아예 없는 상태에서 보내도(이미 해제됐거나 애초에 발생한 적이 없음) 안전하게
  ERROR로 응답할 뿐 다른 부작용은 없다.
- `SET_PI_GAINS`와 동일하게 `AppEventQueue`를 거치지 않고 `Communication_HandleCompleteLine()`에서
  즉시 처리된다(1회성 안전 명령이라 확정적인 ACK/ERROR가 필요하고, 큐 드롭 시 응답 없이
  조용히 실패하는 것을 피하기 위함).

응답 형식은 아래 [STALL_RESET Ack / Error](#stall_reset-ack--error) 절 참고.

### 예약됨 / 미구현 (Reserved / Not Implemented)

```
PING
```

`PING`은 Protocol v1 형식(명령어 이름)만 예약되어 있을 뿐, CommandParser에 구현되어
있지 않다. 현재 STM에 `PING`을 보내면 알 수 없는 명령으로 간주되어 형식 오류로
조용히 무시된다(응답 없음). PING 파싱 및 응답 형식(예: `PONG`) 구현은 별도 작업으로
남겨둔다.

향후 명령은 추가 가능하지만, 이미 구현된 명령의 형식은 변경하지 않는다.

## STM → PC

### STATUS Packet

형식:

```
STATUS,<LT>,<LA>,<RT>,<RA>,<LPWM>,<RPWM>,<LE>,<RE>
```

필드 의미:

| 필드 | 의미 | 자료형 / 범위 |
|------|------|------|
| LT   | Left Target (rad/s) | `float`, 소수점 둘째 자리까지 표시. 현재 `SET_WHEEL_VEL`에 상한 clamp가 없어(`motion_controller.c`의 `MOTION_CONTROLLER_MAX_WHEEL_RAD_S` TODO 참고) 이론상 범위가 정해져 있지 않음 |
| LA   | Left Actual (rad/s) | `float`. `Motor_GetActualWheelVelocity()`가 엔코더 ΔCount로 계산한 실측값(아래 "Actual Wheel Velocity 계산" 절 참고). PI Speed Controller의 입력으로도 쓰인다(아래 "PI Speed Control" 절 참고) |
| RT   | Right Target (rad/s) | `float`, LT와 동일 |
| RA   | Right Actual (rad/s) | `float`, LA와 동일 |
| LPWM | Left PWM | `int16_t`, **부호 있는 값**. `Motor_Process()`가 실제로 TIM3에 출력한 duty(0~99)에 방향을 부호로 실어 보낸다: **양수 = 전진 채널 구동, 음수 = 후진 채널 구동**(절댓값 0~99가 duty %), `0` = 정지. LT/RT가 양수(전진 요청)면 LPWM/RPWM도 양수가 되는 것이 정상 |
| RPWM | Right PWM | `int16_t`, LPWM과 동일한 부호 규칙 |
| LE   | Left Encoder Count (누적값) | `int32_t`(`motor1_encoder_total`). 이 프로젝트의 arm-none-eabi 빌드(ILP32)에서는 `long`도 32bit라 `status_reporter.c`가 `(long)` 캐스트 후 `%ld`로 출력해도 폭이 정확히 일치한다 |
| RE   | Right Encoder Count (누적값) | `int32_t`(`motor2_encoder_total`), LE와 동일 |

예시:

```
STATUS,2.00,1.95,2.00,1.97,36,37,15231,15188
```

필드 순서는 앞으로 변경하지 않는다.

### PI_GAINS Ack / Error

`SET_PI_GAINS` 명령(위 [PC → STM](#pc--stm) 절 참고)에 대한 응답. STATUS Packet과
달리 주기 송신이 아니라, 명령을 받을 때마다 `Communication_HandleCompleteLine()`이
그 자리에서 1회 송신한다(`StatusReporter_SendPiGainsAck()`/`StatusReporter_SendPiGainsError()`,
`Application/Communication/status_reporter.c`).

정상 적용 시:

```
PI_GAINS,<kp>,<ki>
```

- `kp`/`ki`: 실제로 적용된 값(`float`, 소수점 넷째 자리까지 표시). 요청값을 그대로
  반영한 것이며 반올림/clamp가 없다(범위를 벗어나면 애초에 아래 ERROR로 응답하고
  적용하지 않는다).

검증 실패 시:

```
ERROR,SET_PI_GAINS,<reason>
```

| reason | 의미 |
|--------|------|
| `INVALID_FORMAT` | 필드 개수가 2개가 아니거나, 숫자 파싱 실패, 여분의 토큰, NaN/Infinity 등 형식 오류 |
| `OUT_OF_RANGE` | 형식은 올바르나 kp/ki 중 하나 이상이 허용 범위(`MOTOR_PI_KP_MIN/MAX`, `MOTOR_PI_KI_MIN/MAX`)를 벗어남(음수 포함) |

예시:

```
SET_PI_GAINS,0.5,0.0     ->  PI_GAINS,0.5000,0.0000
SET_PI_GAINS,100,0.0     ->  ERROR,SET_PI_GAINS,OUT_OF_RANGE
SET_PI_GAINS,abc,0.0     ->  ERROR,SET_PI_GAINS,INVALID_FORMAT
```

### FAULT / FAULT_CLEARED (Stall)

[Stall Detection](#stall-detection)이 확정/해제될 때 STM이 먼저 PC로 보내는 1회성
알림(STATUS Packet과 달리 명령에 대한 응답이 아니라 STM이 자발적으로 보내는 이벤트).
`StopController_Process()`(Stall 확정 시)와 `StopController_ClearStall()`(해제 성공 시)이
각각 정확히 1회만 호출한다(`StatusReporter_SendStallFault()`/`StatusReporter_SendStallCleared()`,
`Application/Communication/status_reporter.c`) — 중복 송신 방지 방식은
[Stall Detection](#stall-detection) 절 참고.

Stall 확정 시:

```
FAULT,STALL,<cause>
```

| cause | 의미 |
|-------|------|
| `LEFT`  | 왼쪽 바퀴만 Stall 조건을 충족 |
| `RIGHT` | 오른쪽 바퀴만 Stall 조건을 충족 |
| `BOTH`  | 좌우 바퀴가 같은 판정 tick에서 동시에 Stall 조건을 충족 |

`RESET_STALL`로 해제 성공 시:

```
FAULT_CLEARED,STALL
```

예시:

```
FAULT,STALL,LEFT
(RESET_STALL 이후) FAULT_CLEARED,STALL
```

이를 통해 Python Tool/Jetson이 모터가 멈춘 이유(STOP/Timeout/ESTOP/Stall)를 STATUS
Packet의 LPWM/RPWM=0만으로는 구분할 수 없던 것과 달리 명시적으로 구분할 수 있다.
STATUS Packet 필드 자체는 이번 작업에서 변경하지 않았다(LPWM/RPWM이 0으로 떨어지는
것은 여전히 간접적으로 관측 가능).

### STALL_RESET Ack / Error

`RESET_STALL` 명령(위 [PC → STM](#pc--stm) 절 참고)에 대한 응답. `PI_GAINS`
Ack/Error와 동일하게 `Communication_HandleCompleteLine()`이 그 자리에서 1회
송신한다(`StatusReporter_SendResetStallAck()`/`StatusReporter_SendResetStallError()`).

정상 해제 시:

```
STALL_RESET,OK
```

**"Fault는 해제됐지만 모터는 여전히 정지 상태(target 0)"라는 의미**이며 재출발을
뜻하지 않는다(위 [RESET_STALL](#reset_stall) 절 참고).

거부/실패 시:

```
ERROR,RESET_STALL,<reason>
```

| reason | 의미 |
|--------|------|
| `ESTOP_ACTIVE` | Emergency Stop이 걸려 있어 거부(Stall 상태 불변) |
| `LATCHED_SAFE_ACTIVE` | Latched Safe Stop(B1)이 걸려 있어 거부(Stall 상태 불변) |
| `NO_STALL` | 해제할 Stall Fault가 없음(형식은 올바르나 아무 효과 없음) |

예시:

```
RESET_STALL  (Stall 상태, 다른 정지 없음) ->  STALL_RESET,OK
RESET_STALL  (ESTOP 활성 중)              ->  ERROR,RESET_STALL,ESTOP_ACTIVE
RESET_STALL  (Stall이 애초에 없음)         ->  ERROR,RESET_STALL,NO_STALL
```

### Actual Wheel Velocity 계산

`Application/Motor/motor.c`의 `Motor_UpdateActualVelocity()`가 다음 순서로 계산한다
(호출부: `Motor_Process()`, 계산 주기: 아래 Sampling 절 참고):

```
ΔEncoder Count = 현재 motor{1,2}_encoder_total - 직전 샘플 시점 값
rev/s          = (ΔEncoder Count / ENCODER_COUNTS_PER_WHEEL_REV) / 경과시간(s)
RPM            = rev/s x 60
rad/s          = (RPM / 60) x 2π x ENCODER_DIRECTION_SIGN
```

`ENCODER_COUNTS_PER_WHEEL_REV = MOTOR_ENCODER_CPR x MOTOR_GEAR_RATIO x MOTOR_ENCODER_QUADRATURE_MULTIPLIER`이며,
모든 상수는 `Application/Config/motor_config.h`에서 관리한다(코드에 숫자를 직접 쓰지 않음).

현재 하드웨어 상수(모터 PM36-3657-2465E, 24V, 2채널 AB 인크리멘탈 엔코더):

| 상수 | 값 | 비고 |
|------|----|------|
| `MOTOR_ENCODER_CPR` | 380 | 데이터시트 표기값 |
| `MOTOR_GEAR_RATIO` | 51 | **구매 사양 51:1** (2026-08-03 정정 — 이전에 100:1로 기재돼 있었으나 오기였다) |
| `MOTOR_ENCODER_QUADRATURE_MULTIPLIER` | 4 (⚠️ 미확정) | TIM2/TIM8이 `.ioc`에서 `TIM_ENCODERMODE_TI12`(x4 디코딩)로 설정되어 있음을 근거로 "380 CPR = x4 디코딩 이전(채널 1개당 라인 수)"라고 가정. 아래 실측 결과와 어긋나므로 확정 아님 |

따라서 명목 `ENCODER_COUNTS_PER_WHEEL_REV = 380 x 51 x 4 = **77520** count/wheel-rev`이다.
**이 값은 구매 사양 기준 명목값이며 실측 보정값이 아니다.**

#### ⚠️ 2026-08-03 출력축 Count 실측 — 명목값과 약 12.1% 차이 (원인 미확정)

바퀴(출력축)를 손으로 회전시켜 `encoder_total` 변화량을 측정했다(좌우 각 4회전, 총 8회전).

| 대상 | 평균 count/wheel-rev |
|------|----------------------|
| Left | 68107.75 |
| Right | 68217.25 |
| **좌우 전체 평균** | **68162.5** |

- 명목값 77520 대비 약 **-12.1%** (실측이 더 작다)
- 좌우 측정값은 서로 약 **0.16%** 차이로 매우 일관적이다 — 측정 오차나 한쪽 하드웨어 이상보다
  사양/설정 쪽 원인일 가능성이 높다는 간접 근거다

**원인은 아직 확정되지 않았다.** 아래 중 무엇인지 이 데이터만으로는 구분할 수 없다:

1. `MOTOR_ENCODER_CPR` 380의 정의 (채널당 라인 수인지, 이미 quadrature가 적용된 값인지)
2. Quadrature 해석 (`TIM_ENCODERMODE_TI12` = x4 가정이 맞는지)
3. 타이머 입력 필터 (`.ioc`의 `IC1Filter`/`IC2Filter` = 8)로 인한 edge 누락
4. 실제 감속비가 구매 사양(51:1)과 다름

**실측값 68162.5를 코드의 보정 상수로 강제 적용하지 않았다.** `motor_config.h`의
`MOTOR_ENCODER_COUNTS_PER_WHEEL_REV`는 기존 파생식(`CPR x GEAR x QUADRATURE`)을 그대로
유지한다 — 원인을 모른 채 숫자만 맞추면 다른 조건에서 다시 틀어진다.

> 참고로 380 CPR와 x4 배율이 정확하다고 가정하면 역산 감속비가 약 **44.84:1**이 되지만,
> 이는 **역산값일 뿐 실제 감속비로 확정한 것이 아니다.** 마찬가지로 감속비 51:1과 x4가
> 정확하다고 가정하면 유효 CPR이 약 334.1이 된다. 어느 쪽도 근거가 확보되지 않았다.

**후속 캘리브레이션이 필요하며, 그때까지 STATUS의 LA/RA(actual_rad_s)는 실제보다 약 12%
작게 보고된다는 점을 전제로 해석해야 한다.** 원인을 확정한 뒤 해당 매크로 **하나만** 고치면
되고 계산 로직/Protocol은 그대로 유지된다. 구분 방법 예: `.ioc`의 IC Filter를 낮춰 재측정,
모터축(감속 전) 1회전 카운트 측정, 데이터시트·주문 내역 재확인.

**엔코더 회전 방향**: `MOTOR_LEFT_ENCODER_DIRECTION_SIGN`/`MOTOR_RIGHT_ENCODER_DIRECTION_SIGN`(`motor_config.h`,
기본값 1)로 보정한다. PWM 출력 방향 보정(`MOTOR_LEFT_DIRECTION_SIGN` 등, 역시 `motor_config.h`)과는
독립적인 값이며(엔코더 A/B 배선 극성은 모터 +/- 배선과 무관), 바퀴를 손으로 전진 방향으로
돌렸을 때 LA/RA가 음수로 나오면 해당 매크로만 -1로 바꾼다.

**Sampling Time**: `MOTOR_SAMPLE_PERIOD_SEC = 0.1f`(100ms, `motor_config.h`).
`Motor_Process()`는 Main Loop 매 tick(수 ms 미만 간격 추정) 호출되므로 매 tick
계산하면 ΔCount가 너무 작아 양자화 오차가 지배적이게 된다. 이 값은 **STATUS Packet
송신 주기(`STATUS_REPORTER_INTERVAL_MS`)와 의도적으로 분리된 별개의 설정**이다 —
속도 계산(Motor, 향후 PID 입력)과 텔레메트리 송신 주기(Communication)는 서로 다른
이유로 바뀔 수 있는 독립적인 관심사이기 때문이다. 현재는 우연히 둘 다 100ms이지만,
PID 도입 후 제어 주기를 더 촘촘하게(예: 10~20ms) 가져가야 한다면
`MOTOR_SAMPLE_PERIOD_SEC`만 바꾸면 되고 STATUS 송신 주기는 그대로 유지할 수 있다.

### PI Speed Control

`Application/Motor/motor.c`의 `Motor_Process()`가 Feedforward + PI를 합산해 최종 PWM(LPWM/RPWM)을
만든다:

```
Feedforward = Motor_TargetVelocityToPwm(target)          (기존 Open-loop 변환, 변경 없음)
PI Correction = (Kp x Error) + Integral                  (Error = Target - Actual)
최종 PWM = (Feedforward + PI Correction) x 방향 보정, 이후 MOTOR_PWM_MAX로 saturation
```

- **Integral**: Ki가 이미 곱해진 **PWM 단위**로 누적한다(`integral += Ki * Error * dt`). 좌우 각각
  독립적으로 관리되며, `MOTOR_SAMPLE_PERIOD_SEC`(Actual Wheel Velocity와 동일 주기 — 새로운 Actual이
  있을 때만 적분 시간 기준이 맞기 때문)마다 갱신된다. P항(`Kp x Error`)은 Actual 갱신 여부와 무관하게
  Feedforward와 함께 매 tick 재계산되어, Target이 바뀌면 다음 tick에 바로 반영된다.
- **Anti-Windup**: Integral **상태 자체**를 `MOTOR_PI_INTEGRAL_PWM_LIMIT`로 clamp한다. 최종 PWM
  saturation(`MOTOR_PWM_MAX`)과는 목적이 다른 별개의 처리다 — 출력만 자르고 Integral 상태를 안
  자르면 화면에 안 보이는 곳에서 계속 누적되는 전형적인 windup이 재발하므로, 반드시 상태 자체를
  clamp한다.
- **Speed Controller Enable/Disable**: `motor_speed_control_enabled`가 0이면 Feedforward/PI 계산을
  모두 건너뛰고 PWM을 0으로 유지한다(엔코더 갱신/Actual 계산은 계속 수행). `Motor_NormalStop()`/
  `Motor_EmergencyStop()`이 Integral 리셋과 비활성화를 함께 수행하며(Normal Stop/통신 Timeout/Latched
  Safe Stop/Emergency Stop 4가지 정지 트리거가 전부 이 두 함수로 수렴), `MotionController_Process()`가
  `StopController_IsStopped() == false`일 때만 `Motor_EnableSpeedControl()`(멱등)로 재활성화한다.
  Motor는 StopController를 직접 참조하지 않는다(Controller -> Motor 단방향 의존성 유지).
- **Kp/Ki 기본값은 0.0f**(`motor_config.h`, 실기 튜닝 전 잠정값). 둘 다 0이면 PI 보정이 항상 0이 되어
  Feedforward만 동작하던 이전 Open-loop 동작과 완전히 동일하다.
- **런타임 변경**: `motor_pi_kp`/`motor_pi_ki`는 컴파일 타임 매크로가 아니라 전역 변수다
  (`Application/Config/motor_config.c`). Build/Flash 없이 위 [SET_PI_GAINS](#set_pi_gains)
  UART 명령으로 바꿀 수 있다. 재부팅하면 `motor_config.c`의 기본값(0.0f)으로 돌아간다 —
  EEPROM/Flash 저장은 아직 구현하지 않았다.

### Stall Detection

바퀴가 벽에 걸리거나 사람이 손으로 잡는 등 물리적으로 막혀 Actual이 거의 0인데도 PI가
Error를 계속 크게 판단해 PWM을 최대치까지 밀어붙이는 상황을, BTS7960 자체 보호(과전류/과열)
보다 먼저 소프트웨어 단에서 감지해 정지시키는 기능이다.

**⚠️ 한계**: 전류 센서/ADC 기반이 아니라 **PWM(명령값)과 Encoder(Actual Wheel Velocity)만으로
추정하는 간접 보호**다. 실제 모터 전류를 측정하지 않으므로, 예를 들어 무부하 공회전과 실제
저항이 큰 정지 상태를 전류 파형으로 구분하는 것 같은 정밀한 판단은 하지 못한다. 또한 **BTS7960
자체의 과전류/과열 보호(하드웨어)를 대체하지 않는다** — 그보다 더 이른 시점에, 더 낮은 문턱값으로
먼저 개입해 하드웨어 보호가 동작할 필요조차 없도록 하는 것이 목적이다.

**판정 조건** (`Application/Motor/motor.c`의 `Motor_UpdateActualVelocity()`, 기존 100ms
게이트 안에서 좌/우 각각 독립적으로 평가):

```
|motor_last_left/right_pwm|        >= MOTOR_STALL_PWM_THRESHOLD
AND |motor_limited_left/right_rad_s| >= MOTOR_STALL_TARGET_RAD_S
AND |motor_actual_left/right_rad_s|  <= MOTOR_STALL_ACTUAL_RAD_S
```

위 세 조건이 **끊김 없이 연속으로** `MOTOR_STALL_DURATION_MS` 이상 유지되어야 확정된다.
조건이 한 번이라도 깨지면(단발성 샘플, 일시적 부하 등) 해당 바퀴의 타이머는 즉시 0으로
리셋된다(누적이 아니라 연속 유지 조건).

다음 상태에서는 판정 자체를 진행하지 않는다(방향 전환 대기/정상 정지가 Stall로 오검출되지
않도록):

- `motor_speed_control_enabled == false`(STOP/ESTOP 등으로 이미 출력이 차단된 상태 포함)
- 방향 전환 보호의 `ZEROED_WAITING`/`HOLDING` 상태(0 근처에서 의도적으로 대기 중 — [PI Speed
  Control](#pi-speed-control) 절의 Speed Profile 설명 참고)

**Threshold 초기값** (`Application/Config/motor_config.h`, ⚠️ 모두 **실기 미검증 잠정값** —
다른 PI/Speed Profile 상수와 동일한 성격이며 실기 튜닝 필요):

| 상수 | 초기값 | 근거 |
|------|--------|------|
| `MOTOR_STALL_PWM_THRESHOLD` | 80 | `MOTOR_PWM_MAX`(99)의 약 80%선 — 일반 기동/가속 구간의 순간적으로 높은 PWM과 구분하되 실제로 막혔을 때의 근포화 영역은 포착 |
| `MOTOR_STALL_TARGET_RAD_S` | 0.2f | `MOTOR_TARGET_DEADBAND_RAD_S`(0.05f)보다 확실히 높게 잡아 사실상 정지 요청에 가까운 낮은 Target을 제외 |
| `MOTOR_STALL_ACTUAL_RAD_S` | 0.1f | `MOTOR_DIRECTION_ZERO_THRESHOLD_RAD_S`와 현재 값은 같지만, 방향 전환 Hold 판정과는 다른 관심사라 의도적으로 별도 매크로로 분리 |
| `MOTOR_STALL_DURATION_MS` | 500u | `MOTOR_SAMPLE_PERIOD_SEC`(100ms)의 5배 — 최소 5회의 독립된 Actual 샘플이 연속으로 조건을 만족해야 확정되어 단발성 오검출을 줄임 |

**좌/우 원인 보존**: `MotorStallCause_t`(`Application/Motor/motor.h`) 비트 플래그로
`MOTOR_STALL_LEFT`/`MOTOR_STALL_RIGHT`/`MOTOR_STALL_BOTH`를 구분해 보존한다. 좌/우가 같은
판정 tick에서 동시에 확정되면 `BOTH`(예: 정면 충돌로 양쪽이 동시에 막히는 경우). 이미 Stall이
확정된 상태(`Motor_ClearStall()` 호출 전)에서는 다시 판정하지 않으므로 최초 원인이 덮어써지지
않는다.

**확정 시 동작** (같은 tick 안에서 순서대로 수행):

1. `Motor_SetLeftPwm(0)` / `Motor_SetRightPwm(0)`으로 좌우 PWM을 그 tick 안에서 즉시 0으로
2. `Motor_ResetSpeedController()` 재사용 — PI Integral 초기화 + Speed Controller 비활성화 +
   requested/limited/방향 전환 상태 초기화(Normal Stop/ESTOP과 동일한 함수, 새 로직 없음)
3. Stall 원인(좌/우/양쪽)을 래치

한쪽 바퀴만 Stall이어도 좌우 모두 정지한다(차동 구동 로봇에서 한쪽만 세우면 반대쪽으로
꺾이며 긁힐 수 있어 안전을 위해 전체를 세운다).

**StopController 연동**: Motor는 StopController를 호출하지 않는다(Controller → Motor
단방향 의존성 유지). 대신 `StopController_Process()`가 매 tick `Motor_IsStalled()`를
폴링해, 새로 확정된 순간(rising edge)에만 자신의 `stall_stopped` 상태를 래치하고
`StopController_IsStopped()`/`StopController_IsLatched()`에 반영한다. Stall Fault는
Latched Safe Stop/Emergency Stop과 마찬가지로 **자동 해제되지 않는 Latched 상태**로
취급되며(`StopController_IsLatched()`에 포함), `RESET_STALL` UART 명령으로만 해제된다
(위 [RESET_STALL](#reset_stall) 절 참고). `MotionController_Process()`는 기존
`StopController_IsStopped()` 게이트를 그대로 재사용하므로 수정되지 않았다.

**송신 주기**: 10Hz (`STATUS_REPORTER_INTERVAL_MS`, `Application/Communication/status_reporter.c`).
매크로 하나로 관리하며 10Hz/20Hz 중 선택 가능하다.

**송신 버퍼 크기**: `STATUS_REPORTER_LINE_BUFFER_SIZE`(96 byte). LPWM/RPWM은 항상
`-99`~`99`(최대 3자), LE/RE는 `int32_t` 전체 범위(`-2147483648`, 최대 11자)로 값이
보장되므로, 이 두 필드 기준 최악의 경우 패킷 길이는 다음과 같이 널 종료 문자 포함
73byte이고 96byte 버퍼에 23byte 여유가 있다.

```
STATUS,-999.99,-999.99,-999.99,-999.99,-99,-99,-2147483648,-2147483648\r\n  (72byte + NUL = 73byte)
```

단, 위 계산은 LT/RT(Target)를 `-999.99`~`999.99` 범위로 가정한 것이며, 위 표에 적었듯
현재 목표 속도에는 clamp가 없다. PC가 비정상적으로 큰 값을 `SET_WHEEL_VEL`로 보내면
`snprintf`가 버퍼 범위 안에서 안전하게 잘라내므로 메모리 오버플로우는 발생하지 않지만,
줄 끝의 `\r\n`이 잘려 나가 해당 STATUS 줄의 프레이밍이 깨질 수 있다. 이 caveat은
`MOTION_CONTROLLER_MAX_WHEEL_RAD_S` clamp가 구현되면 함께 해소된다(별도 TODO, 이번
작업 범위 아님).

## TODO

- **HAL_UART_Transmit의 DMA/IT 전환 검토**: 현재 STATUS Packet 송신은 `HAL_UART_Transmit()`
  블로킹 방식을 사용한다(전송 시간 약 4~8ms, Main Loop tick 예산 대비 무시할 수준이라
  이번 단계에서는 유지). PI가 도입된 지금도 `MOTOR_SAMPLE_PERIOD_SEC`가 여전히 100ms라
  당장은 문제되지 않지만, 향후 이 값을 더 촘촘하게(예: 10~20ms) 낮춰야 한다면 이 블로킹
  구간이 영향을 줄 수 있으므로 그 전에 `HAL_UART_Transmit_IT` 또는 DMA 기반 송신으로
  전환할지 검토가 필요하다.

## Config 구조

`Application/Config/`에 도메인별 설정 헤더를 모은다(코드에 숫자를 직접 쓰지 않고 이
헤더들을 통해서만 참조). 현재는 `motor_config.h`만 있으며, 향후 아래가 추가될 예정이다
(이번 작업 범위 아님, 아직 없음):

- `communication_config.h`: Baudrate, STATUS Packet 송신 주기, 통신 Timeout 등
- `robot_config.h`: Wheel Radius, Wheel Base, Max Linear/Angular Speed 등

## Kp/Ki 실기 튜닝 순서 (제안)

이제 [SET_PI_GAINS](#set_pi_gains) UART 명령으로 Build/Flash 없이 Kp/Ki를 바로 바꿀 수
있으므로, 아래 각 단계의 "값을 올려본다"는 `motor_config.h` 편집이 아니라
`SET_PI_GAINS,<kp>,<ki>` 재전송으로 수행한다.

1. `MOTOR_PI_KI = 0.0f`로 고정한 채 `MOTOR_PI_KP`만 0보다 큰 작은 값부터 올려가며, Target을
   계단 형태로 바꿔줬을 때(예: 0 -> 2.0 rad/s) Actual이 진동 없이 Target 근처까지 빠르게
   따라오는지 확인한다. 진동/오버슈트가 보이면 Kp를 낮춘다.
2. Kp를 응답은 빠르지만 심하게 진동하지 않는 수준으로 고정한 뒤, `MOTOR_PI_KI`를 0보다 큰
   아주 작은 값부터 올려가며 정상상태 오차(Actual이 Target에 완전히 수렴하지 못하고 남는
   차이)를 없앤다. Ki를 너무 높이면 서서히 진동하거나 정지/재개 시 튀는 현상이 나타나므로,
   그 직전 값으로 낮춘다.
3. `MOTOR_PI_INTEGRAL_PWM_LIMIT`는 처음엔 `motor_config.h`의 기본값(`MOTOR_PWM_MAX`의 절반)을
   유지하고, 2번 과정에서 정지/재개 튐이 관찰되면 이 값을 낮춰본다.
4. 좌/우 바퀴는 독립된 Integral을 쓰므로 같은 Kp/Ki를 공유해도 되지만, 실측 데이터에서 이미
   확인했듯 좌/우 응답이 조금씩 다르므로(개체차) 한쪽만 유독 못 따라오면 좌우 값을 다르게
   튜닝하는 것도 고려할 수 있다(이번 구현은 이미 좌/우 완전히 독립된 구조라 값만 분리하면 됨).

## 확장 계획

- **PI 구현 상태**: Feedforward + PI(Kp/Ki)는 구현 완료([위 "PI Speed Control" 절](#pi-speed-control) 참고).
  D항은 아직 없다(엔코더 기반 속도 신호를 미분하면 노이즈가 증폭되기 쉬워, 필요성이 확인되면
  Previous Error 상태 하나만 추가해서 확장할 수 있다). LT/RT(목표)와 LPWM/RPWM(실제 출력)의 의미는
  PI 도입 전후로 동일하게 유지되므로 STATUS Packet 소비 측(Python Tool, 향후 ROS2 Bridge)은
  수정이 필요 없었다.
- **PING 응답**: PC → STM `PING`에 대한 STM → PC 응답 형식(예: `PONG`)은 아직
  정의하지 않았다. 필요 시 별도 라인 형식으로 추가하고 이 문서에 반영한다.
- **Stall Detection 구현 상태**: 위 [Stall Detection](#stall-detection) 절 참고로 구현
  완료(빌드만 확인, 실기 미검증). 이번 작업에서 하지 않은 것: 전류 센서/ADC 기반 판정,
  자동 Stall 복구(장애물 제거 시 자동 재출발), Protective Stop, EEPROM/Flash에 Fault
  이력 저장, Python Tool의 FAULT/RESET_STALL 지원(별도 작업 예정).
