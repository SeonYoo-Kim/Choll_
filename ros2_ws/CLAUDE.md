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
- [x] 5c-1. USB Serial 실제 write (`SerialLink.write()`, **PTY로만 검증** — 실기 미연결)
- [x] 5c-2. 실기 전 안전장치 (최대 wheel rad/s 비례 제한 + 핵심 파라미터 시작 검증)
- [ ] 5c-3. 실기 STM32 연결 (`/dev/ttyACM*`, 바퀴 공중 상태) — **미완료**
- [ ] 6. 키보드로 실제 모터 공중 테스트
- [x] 7. `/cmd_vel` timeout 안전정지 (5b에서 함께 구현)
- [ ] 8. STM STATUS 수신 및 ROS2 상태 발행
