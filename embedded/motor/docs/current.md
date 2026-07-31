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
  2. App_ProcessEvents()       AppEventQueue 소비 -> StopController/MotionController Request 호출
  3. StopController_Process()  정지 요청 처리 (Motor_NormalStop/EmergencyStop 호출은 여기서만)
  4. MotionController_Process() 통신 Timeout 검사 + 목표 속도 -> Motor_SetTargetWheelVelocity
  5. Motor_Process()            엔코더 값 갱신
  6. AppTest_Process()          APP_MODE_SELF_TEST일 때만 동작(기본은 비활성)
```

- `Application/Communication/`: `serial_rx`(ISR-safe byte ring buffer) → `communication`(줄 조립 + 이벤트 등록) → `command_parser`(순수 파싱, bounded, `strtof` 기반)
- `Application/Controller/`: `stop_controller`(Operational/Latched Safe/Emergency 3단계 정지), `motion_controller`(목표 속도 저장 + 통신 Timeout 감지)
- `Application/Motor/`: 하드웨어 제어 전담. `Motor_SetTargetWheelVelocity()`는 목표값 저장만 하며 PID/PWM 반영 없음(아직 미구현)
- `Application/App/`: `AppEventQueue`(payload 포함, `SET_WHEEL_VELOCITY`는 coalescing) + `App_Run`/`App_ProcessEvents`가 전체를 조립

상세 설계 근거는 [history/2026-07-31_usb-serial-command-interface.md](history/2026-07-31_usb-serial-command-interface.md) 참고.

## 완료된 기능 (요약)

- USART2(ST-LINK VCP, 115200 8N1) CubeMX 활성화 및 RX 인터럽트 배선
- USB Serial 명령 파이프라인: `SerialRx` → `Communication` → `CommandParser` → `AppEventQueue`
- `StopController` 3단계 정지 분리: Operational(USB STOP/Timeout, 재이동 가능) / Latched Safe(B1, 재부팅까지 유지) / Emergency(USB ESTOP, 재부팅까지 유지)
- `MotionController`: 목표 좌우 바퀴 각속도 저장, 300ms 통신 Timeout 1회 래치 감지
- `Motor_SetTargetWheelVelocity()`: 목표값 저장 전용 API (Wheel PID 자리만 마련)
- `App_Mode`(REMOTE_CONTROL 기본값 / SELF_TEST)로 기존 자동 주행 테스트 시퀀스와 USB 원격 제어 분리
- `HAL_UART_ErrorCallback` 추가: UART 프레이밍/오버런 에러 발생 시 수신이 영구 중단되는 문제 수정

## 실제 검증 완료된 기능

- CubeIDE Build 성공
- Tera Term를 이용한 USB Serial 송신 확인
- CommandParser에서
  SET_WHEEL_VEL,1.0,1.0
  명령이 정상적으로 left/right wheel velocity로 파싱되는 것 확인
- AppEventQueue까지 이벤트 전달 확인
- MotionController → Motor_SetTargetWheelVelocity()까지 목표 속도 전달 확인

아직 PID 및 PWM 출력은 연결되지 않았으므로 실제 모터는 회전하지 않는다.

## 현재 개발 중인 기능

USB Serial 명령 인터페이스의 **실기 검증**을 시작하는 단계.
- CubeIDE 빌드 결과 미확인 (사용자가 직접 빌드 예정, 에러/경고 로그 공유 시 대응)
- 시나리오 A~G(정상 주행/STOP-재개/ESTOP 래치/300ms Timeout/B1/잘못된 입력) 실기 테스트 예정
- 통신 경로(초기 `HAL_UART_Receive_IT` 무장 → `RxCpltCallback` 재무장 → `ErrorCallback` 복구)는 코드 레벨로만 점검 완료, 오실로스코프/실제 터미널 송수신 검증은 아직

## 다음 개발 목표

1. CubeIDE 빌드 통과 확인 (경고 0개 목표)
2. 실기 USB Serial 명령 테스트 (시나리오 A~G)
3. Wheel Velocity PID 구현 (엔코더 기반 폐루프 제어) — 현재 `Motor_SetTargetWheelVelocity()`는 저장만 함
4. 하드웨어 실측(기어비/바퀴 반지름/최대 RPM) 후 `MOTION_CONTROLLER_MAX_WHEEL_RAD_S` 확정 및 clamp 적용 (`motion_controller.c` TODO 참고)

## Claude가 다음 세션에서 가장 먼저 이해해야 하는 내용

- **이 프로젝트는 아직 실기 검증 전이다.** "구현 완료"와 "동작 확인됨"을 혼동하지 말 것.A
- `.ioc`, HAL 자동 생성 코드(`usart` 관련, `stm32f4xx_it.c`/`stm32f4xx_hal_msp.c`의 USER CODE 밖 영역)는 CubeMX 산출물이며, PinMap·주변장치 설정 변경은 항상 사용자에게 먼저 제안한다([../CLAUDE.md](../CLAUDE.md) 참고).
- STOP(USB)과 B1(Latched Safe)과 ESTOP은 서로 다른 상태이며 혼동하면 안전 로직이 깨진다 — 구분 근거는 history 문서 참고.
- 하드웨어 파라미터(최대 rad/s 등)를 임의로 추측해 상수에 채워 넣지 않는다. 확정 전까지는 TODO로 남긴다.