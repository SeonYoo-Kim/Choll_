# motor/ 현재 상태

이 문서는 `motor/` 프로젝트의 **현재 상태만** 담습니다. 완료된 기능은 요약만 남기고,
상세 설계·검증 기록은 [history/](history/)로 옮깁니다. 이 문서가 특정 history 문서를
언급하지 않는 한 history는 읽지 않아도 됩니다.

## 프로젝트 목적

Jetson Orin이 USB Serial(USART2, ST-LINK VCP)로 보내는 주행 명령(`SET_WHEEL_VEL` /
`STOP` / `ESTOP`)을 STM32(NUCLEO-F446RE)가 받아, 비블로킹 Event Loop 구조로 안전하게
좌우 모터를 제어한다.

## 현재 아키텍처 요약

```
main() while(1) -> App_Run()

App_Run()
  1. Communication_Process()   USB Serial byte 소비 -> 줄 조립 -> 명령 파싱 -> AppEvent 등록
                                (SET_PI_GAINS/RESET_STALL은 큐를 거치지 않고 즉시 동기 처리)
  2. App_ProcessEvents()       AppEventQueue 소비 -> StopController/MotionController Request 호출
  3. StopController_Process()  Stall Fault 폴링(Motor_IsStalled(), rising edge에서만 FAULT Packet
                                1회 송신) + 정지 요청 처리 (Motor_NormalStop/EmergencyStop 호출은
                                여기서만. 이 두 함수가 PI Integral 리셋 + Speed Controller
                                비활성화도 겸함)
  4. MotionController_Process() 통신 Timeout 검사 + (정지 아니면) Motor_EnableSpeedControl() +
                                목표 속도 -> Motor_SetTargetWheelVelocity
  5. Motor_Process()            엔코더 값 갱신(항상) + Actual Wheel Velocity 갱신(100ms 주기, 항상,
                                이 주기 안에서 Stall Detection도 함께 판정) +
                                (Speed Controller 활성 시만) Feedforward+PI -> 최종 PWM, 아니면 PWM 0
  6. StatusReporter_Process()   10Hz로 STATUS Packet 조립 + USART2 송신
  7. AppTest_Process()          APP_MODE_SELF_TEST일 때만 동작(기본은 비활성)
```

- `Application/Config/`: 도메인별 설정 헤더 모음. 현재 `motor_config.h`(모터/기어박스/엔코더/PWM/Feedforward/PI/Stall Detection 상수)만 존재. 코드에 숫자를 직접 쓰지 않고 이 헤더를 통해서만 참조 (향후 `communication_config.h`/`robot_config.h` 추가 예정, [docs/serial_protocol.md](serial_protocol.md) Config 구조 절 참고)
- `Application/Communication/`: `serial_rx`(ISR-safe byte ring buffer) → `communication`(줄 조립 + 이벤트 등록, `SET_PI_GAINS`/`RESET_STALL`만 예외적으로 AppEventQueue를 거치지 않고 즉시 처리) → `command_parser`(순수 파싱, bounded, `strtof` 기반), `status_reporter`(STM→PC STATUS Packet 주기 송신 + `SET_PI_GAINS`/`RESET_STALL` ACK/ERROR + Stall FAULT/FAULT_CLEARED 알림, [docs/serial_protocol.md](serial_protocol.md))
- `Application/Controller/`: `stop_controller`(Operational/Latched Safe/Emergency/**Stall Fault** 4단계 정지 — Stall Fault는 Motor가 확정한 상태를 매 tick 폴링해 반영, `RESET_STALL`로만 해제), `motion_controller`(목표 속도 저장 + 통신 Timeout 감지 + Speed Controller 활성화 트리거 + `MotionController_ResetTarget()`으로 RESET_STALL 후 저장 target 초기화)
- `Application/Motor/`: 하드웨어 제어 + 제어 루프 전담. `Motor_SetTargetWheelVelocity()`로 저장된 목표 rad/s를 `Motor_Process()`가 Feedforward(`Motor_TargetVelocityToPwm()`, Open-loop 비례식) + PI 보정(`Motor_ComputePiCorrection()`, 엔코더 기반 Actual Wheel Velocity 폐루프)을 합산해 PWM에 반영. `motor_speed_control_enabled` 상태(`Motor_EnableSpeedControl()`로 활성화, `Motor_NormalStop()`/`Motor_EmergencyStop()`에서 비활성화+Integral 리셋)가 0이면 계산을 건너뛰고 PWM 0 유지. `Motor_UpdateActualVelocity()`가 엔코더 ΔCount로 Actual Wheel Velocity(rad/s)를 계산(`MOTOR_SAMPLE_PERIOD_SEC` 주기, `motor_config.h`)하면서 같은 주기로 PI Integral 누적 + **Stall Detection**(PWM/Target/Actual 3조건이 500ms 연속 유지되면 확정, `Motor_ResetSpeedController()` 재사용해 즉시 정지)도 수행. `Motor_GetTargetWheelVelocity()`/`Motor_GetLastPwm()`/`Motor_GetActualWheelVelocity()`/`Motor_IsStalled()`/`Motor_GetStallCause()`는 StatusReporter/StopController 전용 조회 API. Motor는 StopController를 참조하지 않는다(Controller -> Motor 단방향 의존성)
- `Application/App/`: `AppEventQueue`(payload 포함, `SET_WHEEL_VELOCITY`는 coalescing) + `App_Run`/`App_ProcessEvents`가 전체를 조립

상세 설계 근거는 [history/2026-07-31_usb-serial-command-interface.md](history/2026-07-31_usb-serial-command-interface.md) 참고.

## 완료된 기능 (요약)

- USART2(ST-LINK VCP, 115200 8N1) CubeMX 활성화 및 RX 인터럽트 배선
- USB Serial 명령 파이프라인: `SerialRx` → `Communication` → `CommandParser` → `AppEventQueue`
- `StopController` 3단계 정지 분리: Operational(USB STOP/Timeout, 재이동 가능) / Latched Safe(B1, 재부팅까지 유지) / Emergency(USB ESTOP, 재부팅까지 유지)
- `MotionController`: 목표 좌우 바퀴 각속도 저장, 통신 Timeout 1회 래치 감지
- `Motor_SetTargetWheelVelocity()` + Open-loop 변환(`Motor_TargetVelocityToPwm()`): 목표 rad/s를 단순 비례식으로 PWM에 반영(Wheel PID 아님)
- `App_Mode`(REMOTE_CONTROL 기본값 / SELF_TEST)로 기존 자동 주행 테스트 시퀀스와 USB 원격 제어 분리
- `HAL_UART_ErrorCallback` 추가: UART 프레이밍/오버런 에러 발생 시 수신이 영구 중단되는 문제 수정
- **UART Protocol v1 확정 및 STATUS Packet 구현** ([docs/serial_protocol.md](serial_protocol.md)): `StatusReporter` 모듈이
  10Hz로 `STATUS,<LT>,<LA>,<RT>,<RA>,<LPWM>,<RPWM>,<LE>,<RE>`를 USART2로 송신. `tools/motor_serial_test`가
  이 Packet을 수신해 콘솔에 표시하도록 함께 갱신(Target/Actual/Error/PWM/Encoder).
- **Actual Wheel Velocity 계산**: `Motor_UpdateActualVelocity()`가 엔코더 ΔCount -> RPM -> rad/s 순으로 계산해
  STATUS Packet의 LA/RA에 실측값을 채움(계산식/하드웨어 상수는 [docs/serial_protocol.md](serial_protocol.md) 참고).
  `MOTOR_ENCODER_QUADRATURE_MULTIPLIER`(4.0f)는 아직 실기로 절대 검증은 안 된 **임시 가정**(간접 정합성만 확인됨, 아래 참고).
- **Config 디렉터리 도입**: `Application/Config/motor_config.h`에 Motor 관련 설정값(기어비, Encoder CPR,
  Quadrature Multiplier, Sampling Time, PWM Max, Feedforward/PI 상수)을 모음. 향후 `communication_config.h`/`robot_config.h` 확장 예정.
- **PI Speed Controller (Feedforward + PI)**: `Motor_Process()`가 기존 Open-loop 변환(`Motor_TargetVelocityToPwm()`,
  변경 없이 Feedforward로 재사용)에 PI 보정(`Motor_ComputePiCorrection()`)을 더해 최종 PWM을 출력. Integral은
  Ki가 이미 곱해진 PWM 단위로 누적하고 `MOTOR_PI_INTEGRAL_PWM_LIMIT`로 clamp(Anti-Windup, 최종 PWM
  saturation과는 별개). `motor_speed_control_enabled` 상태로 On/Off: `Motor_NormalStop()`/`Motor_EmergencyStop()`이
  Integral 리셋 + 비활성화를 겸하고(4가지 정지 트리거 전부 이 두 함수로 수렴), `MotionController_Process()`가
  `StopController_IsStopped() == false`일 때만 `Motor_EnableSpeedControl()`(멱등)로 재활성화한다.
  Motor는 StopController를 직접 참조하지 않는다(Controller -> Motor 단방향 의존성 유지).
  `MOTOR_PI_KP`/`MOTOR_PI_KI`는 아직 **0.0f**(미튜닝) — 즉 지금은 PI 보정이 항상 0이라 기존 Open-loop
  동작과 완전히 동일하며, 실기 튜닝 전까지 기존 동작을 깨지 않는다.
- **Kp/Ki 런타임 변경**: `motor_pi_kp`/`motor_pi_ki`를 컴파일 타임 매크로 → 전역 변수(`motor_config.c`)로
  전환. UART `SET_PI_GAINS,<kp>,<ki>` 명령(`Motor_SetPiGains()`, 범위 `MOTOR_PI_KP/KI_MIN/MAX` 검증,
  성공 시 좌우 PI Integral만 리셋)으로 Build/Flash 없이 튜닝 가능. 정상/실패 시 각각
  `PI_GAINS,<kp>,<ki>` / `ERROR,SET_PI_GAINS,<reason>` 응답(`status_reporter.c`). 상세는
  [docs/serial_protocol.md](serial_protocol.md) SET_PI_GAINS 절 참고. **실기 검증 완료**(아래
  "실제 검증 완료된 기능" 참고).
- **Stall Detection + Fault Recovery**: 바퀴가 물리적으로 막혀(벽/사람 등) Actual이 거의 0인데도
  PI가 PWM을 최대치까지 밀어붙이는 상황을 소프트웨어로 감지해 정지시킨다. `Motor_UpdateActualVelocity()`의
  기존 100ms 게이트 안에서 좌/우 독립적으로 "|PWM|≥Threshold AND |Target|≥Threshold AND
  |Actual|≤Threshold"가 `MOTOR_STALL_DURATION_MS`(500ms) 연속 유지되면 확정(`motor_config.h`
  `MOTOR_STALL_*`, 전부 잠정값). 확정 시 좌우 PWM 즉시 0 + `Motor_ResetSpeedController()` 재사용(Integral
  리셋 + Speed Controller 비활성화) + 원인(`MotorStallCause_t`: LEFT/RIGHT/BOTH) 래치.
  `StopController`가 `Motor_IsStalled()`를 매 tick 폴링해 `stall_stopped`(4번째 정지 레벨, Latched
  Safe/Emergency와 동일하게 `IsStopped()`/`IsLatched()`에 포함)로 반영하고, 확정 시 1회
  `FAULT,STALL,<cause>`를 송신. UART `RESET_STALL` 명령(`StopController_ClearStall()`, Emergency/Latched
  Safe 활성 시 거부)으로만 해제되며, 성공해도 모터 재출발은 하지 않는다 — `MotionController_ResetTarget()`을
  함께 호출해 저장된 target도 0으로 지워, 재출발은 이후 별도의 새 `SET_WHEEL_VEL`을 통해서만 Speed
  Profile을 거쳐 이뤄지도록 강제한다. 성공/실패 시 각각 `STALL_RESET,OK` / `ERROR,RESET_STALL,<reason>`
  응답. PWM/Encoder 기반 간접 추정 보호이며 BTS7960 자체 보호(과전류/과열)를 대체하지 않는다. 상세는
  [docs/serial_protocol.md](serial_protocol.md) Stall Detection/RESET_STALL 절 참고. 빌드만 확인,
  실기 미검증.

## 실제 검증 완료된 기능

- CubeIDE Build 성공
- STM Open Loop 정상 동작 (실기)
- USB Serial 양방향 통신 정상 (실기): `SET_WHEEL_VEL`/`STOP`/`ESTOP` 파싱 → AppEventQueue → MotionController → Motor_SetTargetWheelVelocity → Open-loop PWM 출력까지 확인
- Python Serial Test Tool(`tools/motor_serial_test`) 정상 동작, W/A/S/D 실시간 제어 정상 (실기)
- STATUS Packet 정상 송신(STM) 및 정상 수신·표시(Python Tool): Target/PWM/Encoder Count 표시 확인 (실기)
- **Actual Wheel Velocity 실기 확인** (Target 1.0/2.0/3.0/4.0/7.0 rad/s 입력 테스트): Actual이 PWM 증가에 따라
  단조 증가, 좌우 값이 서로 비슷(1~9% 이내), Encoder Count도 정상 증가. PWM~Actual 관계는 저속 구간(PWM<20)에서
  비선형(정지마찰/데드존 추정)이고 그 이상에서는 대체로 선형 — 파이프라인 자체는 정상 동작하는 것으로 판단.
  단, 이 테스트는 상대적 정합성만 확인했을 뿐 `MOTOR_ENCODER_QUADRATURE_MULTIPLIER`의 절대 배율(4 vs 1 등)까지
  검증하지는 못했다(스케일 요인은 이 데이터만으로 구분 불가) — 여전히 "손으로 1바퀴 돌려 Count 절댓값 비교" 테스트 필요.
- 전체 흐름 검증: `Python(SET_WHEEL_VEL) → STM → Motor → Encoder → Actual → STATUS Packet → Python` (실기)
- **PI Speed Controller(Feedforward+PI, Anti-Windup, Speed Controller Enable/Disable) 실기 검증 완료**:
  PI 제어, Feedforward+PI 구조, Speed Profile(Direction Change Protection 포함), StopController
  (Normal Stop/ESTOP), Communication Timeout 모두 정상 동작 확인. Kp/Ki Runtime 변경(UART
  `SET_PI_GAINS`) 및 Python Tool/CSV Logger도 정상 동작 확인.
- **ROS2 Serial Bridge 연동(Jetson cmd_vel → STM) 실기 검증 완료 (2026-08-02)**: Python Tool이 아니라
  ROS2 노드가 `SET_WHEEL_VEL`을 보내는 경로가 실기에서 동작함을 확인. `/cmd_vel`(Twist) → 차동구동
  좌우 rad/s 변환 → `SET_WHEEL_VEL,<left>,<right>` USB Serial 송신 → STM 수신 → 양쪽 모터 구동,
  전진/후진/좌회전/우회전 정상. `/cmd_vel`이 끊기면 Bridge watchdog이 약 0.5초 후 `0.000,0.000`을
  보내 자동 정지(STM 자체 Communication Timeout과는 별개의 상위 안전장치).
  브리지 구현은 이 저장소의 `ros2_ws/`이며 STM 펌웨어는 변경되지 않았다
  (Protocol v1 그대로). 상세: [../../../ros2_ws/CLAUDE.md](../../../ros2_ws/CLAUDE.md),
  기록: [../../../tests/TEST_LOG.md](../../../tests/TEST_LOG.md).
  ⚠️ **STM → ROS2 수신 경로(STATUS Packet)는 아직 미구현** — 현재 STATUS를 소비하는 것은
  Python Tool뿐이다.

## 현재 개발 중인 기능

**Stall Detection + Fault Recovery(`RESET_STALL`)가 방금 구현되었고 아직 실기 검증 전이다.**
- 코드 작성 완료(빌드 확인), 실기 테스트는 아직. `MOTOR_STALL_PWM_THRESHOLD`(80)/`MOTOR_STALL_TARGET_RAD_S`
  (0.2f)/`MOTOR_STALL_ACTUAL_RAD_S`(0.1f)/`MOTOR_STALL_DURATION_MS`(500u)는 모두 실기 미검증 잠정값
  (`motor_config.h`) — 실기에서 바퀴를 손으로 잡아 의도적으로 Stall을 유발해 튜닝 필요.
- `MOTOR_ENCODER_QUADRATURE_MULTIPLIER = 4.0f`(motor_config.h)는 여전히 **임시 가정** — 바퀴 1바퀴 수동 회전 후
  Encoder Count 절댓값이 152000(=380x100x4)에 가까운지, 38000(=380x100)에 가까운지로 검증 필요
  ([docs/serial_protocol.md](serial_protocol.md) Actual Wheel Velocity 계산 절 참고)

## 다음 개발 목표

1. **Stall Detection 실기 검증(최우선, 안전 기능)**: 바퀴를 손으로 잡아 의도적으로 Stall 유발 →
   500ms 내 PWM 0 확인 → `FAULT,STALL,<cause>` 수신 확인 → `RESET_STALL` 전송 → `STALL_RESET,OK` +
   `FAULT_CLEARED,STALL` 확인 → 모터가 재출발하지 않음(target 0 유지)을 확인 → 새 `SET_WHEEL_VEL`로만
   재출발되는지 확인. ESTOP/Latched Safe Stop 중 `RESET_STALL`이 거부되는지도 함께 확인
   (안전 테스트 절차는 [docs/serial_protocol.md](serial_protocol.md) Stall Detection 절 참고).
   실기 데이터로 `MOTOR_STALL_*` Threshold 튜닝(오검출/미검출 여부 확인).
2. `MOTOR_ENCODER_QUADRATURE_MULTIPLIER`/`MOTOR_LEFT_ENCODER_DIRECTION_SIGN`/`MOTOR_RIGHT_ENCODER_DIRECTION_SIGN` 실측 검증
3. 하드웨어 실측(바퀴 반지름/최대 RPM) 후 `MOTION_CONTROLLER_MAX_WHEEL_RAD_S`와 `MOTOR_OPEN_LOOP_PWM_PER_RAD_S` 확정 및 clamp 적용 (`motion_controller.c`/`motor_config.h` TODO 참고)
4. Python Tool의 FAULT/RESET_STALL 지원(별도 작업)
5. (STM 쪽 작업 아님, 참고) ROS2 Serial Bridge의 **STATUS 수신 경로** 구현 — STM → ROS2 방향.
   STM 송신부(`StatusReporter`)는 이미 완성되어 있어 펌웨어 변경은 예상되지 않는다.
   Bridge 쪽 진행 상태는 [../../../ros2_ws/CLAUDE.md](../../../ros2_ws/CLAUDE.md) 참고.

## Claude가 다음 세션에서 가장 먼저 이해해야 하는 내용

- **"구현 완료"와 "동작 확인됨"을 혼동하지 말 것.** Open Loop/USB Serial/STATUS Packet/Actual Wheel Velocity/
  PI Speed Controller(Feedforward+PI, Enable/Disable, Anti-Windup, SET_PI_GAINS)는 실기 검증
  완료됐지만, **Stall Detection + RESET_STALL은 방금 구현되어 아직 실기 검증 전이다**(위 "현재
  개발 중인 기능" 참고). 새 기능을 추가할 때마다 이 구분을 갱신할 것.
- Stall Fault는 Latched Safe Stop/Emergency Stop과 마찬가지로 자동 해제되지 않는다 — `RESET_STALL`도
  "재출발"이 아니라 "Fault 해제"만 의미하며, 모터는 별도의 새 `SET_WHEEL_VEL`을 받아야만 다시 움직인다.
  이 구분이 무너지면(예: RESET_STALL이 자동으로 재출발시키면) 사람과 함께 있는 환경에서 안전 문제가
  생긴다 — 구분 근거는 [docs/serial_protocol.md](serial_protocol.md) RESET_STALL 절 참고.
- `.ioc`, HAL 자동 생성 코드(`usart` 관련, `stm32f4xx_it.c`/`stm32f4xx_hal_msp.c`의 USER CODE 밖 영역)는 CubeMX 산출물이며, PinMap·주변장치 설정 변경은 항상 사용자에게 먼저 제안한다([../CLAUDE.md](../CLAUDE.md) 참고).
- STOP(USB)과 B1(Latched Safe)과 ESTOP은 서로 다른 상태이며 혼동하면 안전 로직이 깨진다 — 구분 근거는 history 문서 참고.
- 하드웨어 파라미터(최대 rad/s 등)를 임의로 추측해 상수에 채워 넣지 않는다. 확정 전까지는 TODO로 남긴다.