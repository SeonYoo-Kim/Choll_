# Jetson ↔ STM32 인터페이스 규격

> **정본**: 프로토콜 상세는 [embedded/motor/docs/serial_protocol.md](../embedded/motor/docs/serial_protocol.md),
> ROS2 쪽 구현은 [ros2_ws/src/stm_serial_bridge/](../ros2_ws/src/stm_serial_bridge/)를 참조.
> 이 문서는 두 파트를 잇는 요약 계약서다.

## 1. 하드웨어 및 통신 환경

- 물리 연결: **USB Serial** (USART2, ST-LINK VCP)
- Baud Rate: **115200 8N1**
- 프로토콜: **텍스트 라인 기반 (UART Protocol v1)** — 한 줄 = 한 명령/한 상태
- 후보였던 micro-ROS는 채택하지 않음 (텍스트 프로토콜 + `stm_serial_bridge` 노드로 확정)

## 2. Jetson(ROS2) → STM32

`stm_serial_bridge` 노드가 `/cmd_vel`(geometry_msgs/Twist)을 구독해 차동구동
좌/우 바퀴 각속도(rad/s)로 변환한 뒤 시리얼 명령으로 내려보낸다.

| 명령 | 형식 | 의미 |
|------|------|------|
| 속도 지령 | `SET_WHEEL_VEL,<left_rad_s>,<right_rad_s>` | 좌/우 바퀴 목표 각속도 |
| 정지 | `STOP` | 일반 정지 (Speed Profile 감속) |
| 비상 정지 | `ESTOP` | 즉시 PWM 차단, 래치됨 |
| PI 게인 | `SET_PI_GAINS,<kp>,<ki>` | 런타임 PI 튜닝 (Build/Flash 불필요) |
| Stall 해제 | `RESET_STALL` | Stall Fault 해제 (재출발은 새 SET_WHEEL_VEL 필요) |

## 3. STM32 → Jetson(ROS2)

| 메시지 | 형식 | 주기/시점 |
|--------|------|-----------|
| 상태 패킷 | `STATUS,<LT>,<LA>,<RT>,<RA>,<LPWM>,<RPWM>,<LE>,<RE>` | 10 Hz |
| PI 게인 응답 | `PI_GAINS,<kp>,<ki>` 또는 `ERROR,SET_PI_GAINS,<reason>` | 명령 수신 시 1회 |
| Stall 알림 | `FAULT,STALL,<LEFT\|RIGHT\|BOTH>` / `FAULT_CLEARED,STALL` | 확정/해제 시 1회 |
| Stall 해제 응답 | `STALL_RESET,OK` 또는 `ERROR,RESET_STALL,<reason>` | 명령 수신 시 1회 |

- LT/RT: 목표 각속도(rad/s), LA/RA: 엔코더 실측 각속도(rad/s)
- LPWM/RPWM: 부호 있는 duty(−99~99, 부호 = 방향)
- LE/RE: 엔코더 누적 카운트(int32)

`stm_serial_bridge`는 STATUS를 파싱해 `/stm/wheel_actual_rad_s` 등 ROS2 토픽으로
올린다. 휠 오도메트리는 실측 보정값 `counts_per_wheel_rev = 68160`을 사용한다
(펌웨어 명목값 77520과 약 12% 불일치 — 원인과 경위는 serial_protocol.md의
"Actual Wheel Velocity 계산" 절 참조).

## 4. 안전 동작 요약

- **통신 Timeout**: 일정 시간 `SET_WHEEL_VEL`이 없으면 STM32가 자체 정지
- **Stall Detection**: PWM 고출력 + 엔코더 무회전이 500 ms 연속이면 양쪽 정지 후 래치
- **Emergency/Latched Safe Stop**: ESTOP 명령·NUCLEO B1 버튼, 재부팅 또는 하드웨어로만 해제
