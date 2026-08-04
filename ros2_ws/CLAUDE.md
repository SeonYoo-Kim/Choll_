# CLAUDE.md — ros2_ws/

이 워크스페이스는 **Jetson에서 도는 ROS2 노드**를 개발하는 공간입니다.
현재 유일한 패키지는 `/cmd_vel`을 STM32 모터 제어 보드로 중계하는
[stm_serial_bridge](src/stm_serial_bridge/)입니다.

프로젝트 전체 개요는 [루트 CLAUDE.md](../CLAUDE.md)를 참고하세요.

## 현재 목표

```text
키보드 또는 상위 주행 노드
    ↓
ROS2 /cmd_vel  (geometry_msgs/msg/Twist)
    ↓
stm_serial_bridge      ← 이 워크스페이스가 담당하는 범위
    ↓
좌우 바퀴 목표 각속도 계산
    ↓
USB Serial (115200 8N1)
    ↓
STM32 (NUCLEO-F446RE)
    ↓
모터 제어
```

현재는 비전·LiDAR·Nav2와 통합하지 않습니다. `/cmd_vel`은 `ros2 topic pub` 또는
`teleop_twist_keyboard`로 직접 발행해 테스트합니다.

## 작업 범위

**기본 수정 범위는 `ros2_ws/` 하위뿐입니다.**

| 경로 | 정책 |
|------|------|
| `ros2_ws/` | 수정 가능 (기본 작업 범위) |
| `ai/` | **수정 금지** — 다른 팀원 소유 코드. 패키지 구조·토픽 이름은 참고만 가능. `motor_node.py`·`control_node.py`·launch 파일 모두 수정하지 않는다 |
| `embedded/` | **명시적 요청 없이 수정 금지** — STM32 펌웨어는 별도로 개발·실기 검증 중. 프로토콜 확인을 위해 읽는 것만 가능 |
| 루트 설정 파일 (`pyproject.toml`, `.gitignore`, `docs/` 등) | 수정해야 할 이유가 생기면 **먼저 보고하고 승인을 받는다** |

`stm_serial_bridge`는 AI 노드의 내부 구현을 몰라야 하며, 표준 `/cmd_vel`만
구독합니다. AI 코드에 직접 결합하지 않습니다.

## 워크스페이스 정책

`ai/`와 **독립된 ROS2 워크스페이스**로 유지합니다. 나중에 두 워크스페이스를
각각 source하거나 하나로 합칠 수 있지만, **지금은 통합 방식을 결정하지 않습니다.**

ROS2 배포판: **Humble**

```bash
cd ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

## 개발 원칙

1. **한 번에 전체 기능을 구현하지 않는다.** 작은 단계로 나누고, **각 단계마다
   빌드와 실행을 확인**한 뒤 다음 단계로 넘어간다.
2. **기존 AI 전체 launch(`follow_robot_launch.py`)와 Serial Bridge 실기 테스트를
   동시에 실행하지 않는다.** 그 launch의 `control_node`가 15Hz로 `/cmd_vel`을
   발행하므로, 테스트용 `ros2 topic pub`/teleop 명령과 섞여 의도하지 않은
   모터 구동이 일어날 수 있다.
3. **코드·문서·설명이 충돌하면 임의로 수정하지 않고 보고한다.** 오래된 문서나
   주석이 실제 구현과 다를 수 있으므로, 문서에 적혀 있다는 이유만으로 구현
   상태를 단정하지 않는다. 판단 기준 순서:
   ```text
   실제 실행 코드
   → 실제 빌드 및 테스트 결과
   → 현재 코드와 일치하는 프로토콜 문서
   → 과거 설계 문서와 주석
   → Claude/GPT의 해석
   ```
4. 하드코딩을 최소화하고 설정값은 ROS2 parameter로 관리한다.
5. 초기에 불필요한 custom message 패키지를 만들지 않는다. 표준 메시지와 단순한
   상태 토픽으로 시작한 뒤 필요할 때 확장한다.

## STM 통신 프로토콜

**참고 위치: [embedded/motor/docs/serial_protocol.md](../embedded/motor/docs/serial_protocol.md)**

이 문서가 현재 펌웨어 구현과 가장 일치하는 정본입니다. 프로토콜을 임의로
변경하지 않습니다.

> ⚠️ `docs/JETSON_TO_STM.md`, `embedded/CLAUDE.md`, `docs/SYSTEM_ARCHITECTURE.md`에는
> 과거의 micro-ROS / `/wheel_speed_cmd` 기반 설계가 남아 있습니다. 현재 펌웨어에
> micro-ROS 수신 경로는 없으므로(2026-08-02 확인) 이 워크스페이스는 텍스트 UART
> 프로토콜을 기준으로 개발합니다. 문서 정리는 파트 간 합의가 필요한 별건입니다.

## 구현 단계

- [x] 1. `/cmd_vel` 수신 (패키지 골격 + 파라미터 선언 + 구독 로그)
- [x] 2. 차동구동 좌우 속도 계산 (`differential_drive.py` 순수 모듈 + 단위 테스트)
- [x] 3. STM 명령 문자열 생성 (`protocol.py` 순수 모듈 + 단위 테스트, dry-run 로그)
- [x] 4. dry-run 검증 (`_send_command()` 송신 단일 출구 + `dry_run=false` 시작 거부)
- [x] 5a. Serial 연결만 (`serial_link.py` open/close + 단위 테스트, 송신 없음)
- [x] 5b. 주기 송신 구조 (`command_watchdog.py` + 20Hz 타이머 + timeout 0,0, 송신 없음)
- [x] 5c-1. USB Serial 실제 write (`SerialLink.write()`, PTY로 검증)
- [x] 5c-2. 실기 전 안전장치 (최대 wheel rad/s 비례 제한 + 핵심 파라미터 시작 검증)
- [x] 5c-3. **실기 STM32 연결 및 모터 구동 (2026-08-02 확인)** — 아래 "실기 검증 현황" 참고
- [ ] 6. 키보드(`teleop_twist_keyboard`)로 실제 모터 공중 테스트 — **미완료**
      (2026-08-02·08-03 실기는 모두 `ros2 topic pub`으로 수행, teleop은 아직 사용하지 않음)
- [x] 7. `/cmd_vel` timeout 안전정지 (5b 구현 + 실기 확인)
- [x] 8. **STM STATUS 수신 및 ROS2 상태 발행 (2026-08-03 실기 확인)**
  - [x] 8a. 수신 패킷 파서 (`packet_parser.py`)
  - [x] 8b. raw 수신 + 줄 조립 (`SerialLink.read_available()` / `line_decoder.py`)
  - [x] 8c. RX 타이머 + `/stm/*` 상태 토픽 발행
  - [x] 8e. **실기 수신 검증** — 아래 "실기 검증 현황" 참고
  - [ ] 8d. 수신 끊김 시 추가 안전 정책(STATUS 끊기면 주행 명령을 0으로 강제) — **미착수**

## 실기 검증 현황

기록: [tests/TEST_LOG.md](../tests/TEST_LOG.md)

### 송신 경로 (ROS2 → Serial Bridge → STM32 → Motor) — 2026-08-02 검증 완료

대상 커밋: `b4293b0` "[feat] ROS2 <-> STM serial Bridge 추가."

- `/cmd_vel` 발행 → 노드 수신 → 차동구동 좌우 rad/s 변환 정상
- `SET_WHEEL_VEL,<left>,<right>` USB Serial 전달 → STM32가 수신해 양쪽 모터 실제 구동
- 전진·후진·좌회전·우회전 정상
- `/cmd_vel` 중단 시 watchdog이 약 0.5초 후 자동 정지 (`timed_out` → `0.000,0.000`)
  — 2026-08-03에 `ros2 topic pub --once`로 재확인

### 수신 경로 (STM32 → Serial Bridge → ROS2) — 2026-08-03 검증 완료

대상 커밋: `d6bbe29` "[feat] STM STATUS 수신 및 ROS2 상태 토픽 발행"
환경: Ubuntu + ROS2 Humble, `/dev/ttyACM0`, 115200, **바퀴 공중 상태**

`STM → SerialLink → LineDecoder → parse_packet() → ROS2 Publisher` 전 구간이 실제
장치에서 동작함을 확인했습니다.

- `/stm/connected` = **true** — 포트 open 여부가 아니라 **유효 STATUS 수신** 기준임을 확인
- `/stm/fault` 초기값 = **NONE**
- STATUS 주기: `/stm/wheel_actual_rad_s`를 `ros2 topic hz`로 측정해 **약 9.995~9.999 Hz**
  → 펌웨어 `STATUS_REPORTER_INTERVAL_MS`(10Hz)와 일치
- `in_waiting` 기반 `read_available()`이 실제 `/dev/ttyACM0`에서 정상 동작
  (PTY에서만 검증됐던 부분이 실기로 확인됨)

**좌우 매핑 실측 확정** — 이전까지 "코드 주석 기준, 실측 미확정"이던 항목입니다.

```
물리 왼쪽  바퀴 ↔ STM 논리 Left  ↔ /stm/encoder_total[0] ↔ /stm/wheel_actual_rad_s[0]
물리 오른쪽 바퀴 ↔ STM 논리 Right ↔ /stm/encoder_total[1] ↔ /stm/wheel_actual_rad_s[1]
```

- 손으로 물리 왼쪽 바퀴를 돌리면 `encoder_total[0]`만, 오른쪽은 `[1]`만 변화
- `SET_WHEEL_VEL,2.000,0.000`(= `linear.x=0.065, angular.z=-0.433333`) → 물리 왼쪽만 회전 +
  `encoder_total[0]`만 변화
- `SET_WHEEL_VEL,0.000,2.000`(= `linear.x=0.065, angular.z=+0.433333`) → 물리 오른쪽만 회전 +
  `encoder_total[1]`만 변화
- **PWM 출력 채널과 엔코더 입력 채널의 좌우 짝이 정상** — 즉 "엔코더만 교차"된 상태가 아니다
- `/stm/wheel_actual_rad_s` 부호: 왼쪽만 전진 → `[+, ~0]`, 오른쪽만 전진 → `[~0, +]`,
  왼쪽만 후진 → `[-, ~0]`, 오른쪽만 후진 → `[~0, -]`

> 실기 중 왼쪽 모터/엔코더가 동작하지 않는 현상이 있었으나, 장비 이동 과정에서 배선이
> 빠진 하드웨어 문제였고 재연결 후 정상 확인됐습니다. **코드 결함이 아니었습니다.**

### 수신 경로에서 아직 검증하지 않은 것

- STATUS 중단 후 `/stm/connected=false` 전환 및 재연결 복귀
- USB 강제 분리 시 RX fatal error 처리(종료 코드 1, 타이머 취소)
- 실제 Stall 발생 시 `/stm/fault` 전이(`STALL_LEFT`/`RIGHT`/`BOTH`)와 `FAULT_CLEARED` 수신
- `RESET_STALL` 송신 (미구현)
- **엔코더 스케일 확정** — 출력축 Count 실측 자체는 완료됐으나(아래) **명목값과의 차이 원인은 미확정**
- **`actual_rad_s` 재검증** — STM 감속비 정정(100:1 → 51:1)을 반영한 펌웨어로 **재빌드·재플래시 후**
  다시 확인해야 한다. `/stm/wheel_actual_rad_s` 보고값이 이전보다 약 1.96배 커진다
- `wheel_separation_m=0.30` 실측 확정 (여전히 플레이스홀더)
- 실제 바닥 주행
- STATUS 수신이 끊겼을 때 주행 명령을 강제로 0으로 만드는 추가 안전 정책(8d)

### 엔코더 스케일: 실측 완료 / 원인 미확정 (2026-08-03)

`/stm/encoder_total`로 출력축 수동 회전 Count를 측정했다(좌우 각 4회전, 총 8회전).

| 대상 | 평균 count/wheel-rev |
|---|---|
| Left | 68107.75 |
| Right | 68217.25 |
| **좌우 전체 평균** | **68162.5** |

- **완료**: 출력축 1회전당 Count 실측, 좌우 일관성 확인(서로 약 0.16% 차이)
- **완료**: STM 감속비 오기재 발견 → `MOTOR_GEAR_RATIO` 100.0f → **51.0f**(구매 사양)로 정정.
  명목값이 152000 → **77520**(= 380 × 51 × 4)으로 바뀌었다
- **미완료**: 실측 68162.5가 명목 77520보다 약 **12.1% 작은 원인**이 CPR 380의 정의 /
  Quadrature 해석(x4) / 타이머 입력 필터(`IC1Filter`/`IC2Filter`=8) / 실제 감속비 중
  무엇인지 **확정되지 않았다**
- **미완료**: `MOTOR_ENCODER_CPR`·`MOTOR_ENCODER_QUADRATURE_MULTIPLIER`·실제 감속비 확정
- 실측값을 코드 보정 상수로 강제 적용하지 않았다(파생식 유지). 따라서 **현재
  `/stm/wheel_actual_rad_s`는 실제보다 약 12% 작게 보고된다**는 전제로 해석해야 한다
- 상세: `embedded/motor/docs/serial_protocol.md`의 "Actual Wheel Velocity 계산" 절,
  `motor_config.h`의 `MOTOR_ENCODER_COUNTS_PER_WHEEL_REV` 주석
