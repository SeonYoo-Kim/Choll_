# CLAUDE.md — ros2_ws/

이 워크스페이스는 **Jetson에서 도는 ROS2 노드** 중 모터 구동 계층을 담당합니다.
패키지: `/cmd_vel`을 STM32 모터 제어 보드로 중계하는 [stm_serial_bridge](src/stm_serial_bridge/),
키보드 원격 조종·휠 오도메트리 도구 모음 [cart_teleop](src/cart_teleop/).

프로젝트 전체 개요는 [루트 CLAUDE.md](../CLAUDE.md)를 참고하세요.

## 이 저장소의 ROS2 워크스페이스 3개 — 경계

| 워크스페이스 | 담당 | 빌드 위치 |
|---|---|---|
| `ai/` | 인지 파이프라인 (카메라→YOLO→ByteTrack→Re-ID→`/target_position`, 레거시 PID `/cmd_vel`) | `cd ai && colcon build` |
| `embedded/Lidar/` | SLAM·Nav2·MQTT 브릿지 (LiDAR→slam_toolbox→AMCL→Nav2→`/cmd_vel`) | `cd embedded/Lidar && colcon build` |
| `ros2_ws/` | 모터 구동 (`/cmd_vel`→USB Serial→STM32) + teleop·오도메트리 | `cd ros2_ws && colcon build` |

`/cmd_vel` 발행자는 **동시에 하나만** 존재해야 합니다 — AI 레거시 경로(`legacy_control:=true`)와
Nav2(velocity_smoother)를 함께 켜면 충돌합니다 (실제로 매핑 중 발견된 문제 — [docs/RETROSPECTIVE.md](../docs/RETROSPECTIVE.md) 참조).

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

단독 테스트 시 `/cmd_vel`은 `ros2 topic pub` 또는 `cart_teleop`으로 직접 발행합니다.
통합 구동 시에는 상위 발행자(AI 레거시 PID 또는 Nav2 velocity_smoother) 중 하나가 `/cmd_vel`을 소유합니다.

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
- [x] 9. **실행·검증 워크플로우 (2026-08-04)** — launch + 파라미터 YAML + mock/PTY 자동 검증.
      아래 "실행 및 검증 워크플로우" 참고. 하드웨어 미검증(mock 으로만 확인).
- [ ] 10. **휠 오도메트리** — 아래 "휠 오도메트리" 절 참고
  - [x] 10a. `counts_per_wheel_rev` 파라미터 (2026-08-08 실측 68160, 좌우 공통)
  - [x] 10b. `wheel_odometry.py` 순수 계산 모듈 + 단위 테스트 70개 (2026-08-08)
  - [x] 10c. **별도 `wheel_odometry` 노드 + `/wheel/odom` 발행 (2026-08-08)** — 테스트 49개.
        ⚠️ **하드웨어 미검증**(CLI 발행으로만 확인)
  - [ ] 10d. **STM32 재부팅 탐지 → `rebaseline()` 호출** — **미착수**. 아래 "남은 것" 참고
  - [ ] 10e. **공분산 설정** — **미착수**. 현재 0으로 비어 있다

## 실행 및 검증 워크플로우

수동 명령을 외우는 대신 **launch 한 번**으로 띄우고, **mock/PTY 로 하드웨어 없이 자동 검증**한다.

| 파일 | 역할 |
|---|---|
| `launch/stm_serial_bridge.launch.py` | 통합 실행. `mode:=hardware`(기본) / `mode:=mock` |
| `config/stm_serial_bridge.yaml` | 공통 파라미터 **정본**(11개). launch 인자로 개별 덮어쓰기 |
| `stm_serial_bridge/mock_stm.py` | STM32 대역 mock. PTY 를 만들고 STATUS 를 10Hz 로 송신 |
| `stm_serial_bridge/topic_checker.py` | `/stm/*` 6개 토픽 자동 검증. 종료 코드로 합격/불합격 |
| `scripts/verify_bridge_mock.sh` | 위를 묶은 3-시나리오 회귀 검증 + 로그 파일 저장 |

### 하드웨어 없이 (mock/PTY) — 반복 검증

```bash
cd ros2_ws
colcon build --symlink-install

# 3개 시나리오 자동 검증 (connect / cmd_vel 왕복 / STATUS 중단 → connected=false)
bash scripts/verify_bridge_mock.sh                       # 로그: log/bridge_verify/<타임스탬프>/
bash scripts/verify_bridge_mock.sh --log-dir /tmp/stmlog  # 로그 위치 지정
```

개별로 돌릴 때:

```bash
export ROS_LOCALHOST_ONLY=1
source /opt/ros/humble/setup.bash && source install/setup.bash

ros2 launch stm_serial_bridge stm_serial_bridge.launch.py mode:=mock
ros2 run stm_serial_bridge check_stm_topics --timeout-sec 10          # 별 터미널

# STATUS 중단 → status_timeout_sec 동작 확인
ros2 launch stm_serial_bridge stm_serial_bridge.launch.py mode:=mock mock_stop_after_sec:=5.0
ros2 run stm_serial_bridge check_stm_topics --expect-disconnect --timeout-sec 15
```

⚠️ `mode:=mock` 은 **실제 장치를 절대 열지 않는다.** mock 이 만든 PTY symlink
(`/tmp/stm_serial_bridge_mock_pty`)로 `serial_port` 를 강제 덮어쓰므로 YAML 의
`/dev/ttyACM0` 값은 무시된다.

### 실제 하드웨어

**같은 launch 파일을 쓰고 `serial_port` 만 바꾼다.** YAML 기본값이 `/dev/ttyACM0` 이므로
보통은 인자도 필요 없다.

```bash
export ROS_LOCALHOST_ONLY=1                 # 다른 머신의 /cmd_vel 차단 (필수)
source /opt/ros/humble/setup.bash && source install/setup.bash

# 바퀴를 공중에 띄운 상태에서만 실행할 것
ros2 launch stm_serial_bridge stm_serial_bridge.launch.py \
  2>&1 | tee ~/stm_$(date +%Y%m%d_%H%M%S).log

# 포트가 다르면 이 인자만 바꾼다
ros2 launch stm_serial_bridge stm_serial_bridge.launch.py serial_port:=/dev/ttyACM1

# 같은 검증 도구를 실기에도 그대로 쓴다
ros2 run stm_serial_bridge check_stm_topics --timeout-sec 10
```

### 속도 상한과 프로파일 (2026-08-04 추가)

`max_wheel_rad_s` 를 넘는 목표는 `limit_wheel_rad_s()` 가 **좌우 비율을 유지한 채 비례
축소**한다. 궤적·조향은 유지되고 속도만 느려지므로, 상한이 상위 스택의 봉투보다 낮으면
증상이 "상한이 낮다"가 아니라 **"주행 스택이 동작하지 않는다"처럼 보인다.**
(제한이 걸리면 노드가 경고 로그를 남기므로 조용히 일어나는 일은 아니다.)

Nav2 봉투(`max_vel_x=0.3`, `max_vel_theta=0.6`)와의 관계
— `r=0.065`, **`L=0.38`(2026-08-04 실측)** 기준:

| Nav2 명령 | 필요 상한 | 상한 1.0 일 때 |
|---|---|---|
| 직진 `v=0.3` | **4.615 rad/s** | 0.065 m/s (21.7%) |
| 제자리 회전 `ω=0.6` | **1.754 rad/s** | 0.57 배로 축소 |
| 직진+회전 (최악) | **6.369 rad/s** | 0.157 배로 축소 |

`wheel_separation_m` 은 **회전 성분에만** 들어간다. 그래서 `L` 이 0.30 → 0.38 로 바뀌어도
**직진 요구량 4.615 는 불변**이고, 회전·최악 조합만 커진다(1.385→1.754, 6.000→**6.369**).
이 때문에 `nav2` 프로파일 상한을 6.0 → **6.4** 로 올렸다.

계산은 주석이 아니라 코드에 있다 — `differential_drive.required_max_wheel_rad_s()` +
`test_differential_drive.py`(회귀 고정: `(0.3, 0.6, 0.065, 0.30) → 6.0`).

**기본값 `1.0` 은 바꾸지 않는다.** 올릴 때는 프로파일/인자를 쓴다:

| 프로파일 | 상한 | 직진 최대 | 제자리 회전 | 상태 |
|---|---|---|---|---|
| `bench` (기본) | 1.0 | 0.065 m/s | 축소됨 | ✅ 실기 검증됨. ⚠️ 모터 데드밴드 미만일 수 있어 **바닥에서 안 움직일 가능성** |
| `slow` | 2.0 | 0.13 m/s | **무축소** | ✅ **2026-08-04 실기 확인** — 바퀴 공중 + **바닥 전진·정지** + **바닥 제자리 회전**(목표 `[-1.754, 1.754]` 무축소 확인). fault·급가속 없음. ⚠️ **속도·회전각 수치는 미검증** |
| `nav2` | **6.4** | 0.30 m/s | 무축소 | ⚠️ **실기 미검증** (계산상 상한. 검증된 최대는 2.0) |

```bash
ros2 launch stm_serial_bridge stm_serial_bridge.launch.py speed_profile:=slow
ros2 launch stm_serial_bridge stm_serial_bridge.launch.py speed_profile:=nav2
ros2 launch stm_serial_bridge stm_serial_bridge.launch.py max_wheel_rad_s:=3.5  # 임의값
```

**파라미터 우선순위** (뒤가 앞을 덮어쓴다):

```
① config/stm_serial_bridge.yaml         (base, 정본)
② config/speed_profile_<profile>.yaml   (bench 는 오버레이 없음)
③ launch 인자 (max_wheel_rad_s, serial_port / mock 의 PTY 경로)
```

- `speed_profile` 에 알 수 없는 값을 주면 **조용히 기본값으로 대체하지 않고 실패**한다.
- `max_wheel_rad_s` 인자는 프로파일보다 **우선**한다 — 실기에서 단계적으로 올릴 때 쓴다.
- ⚠️ Nav2 쪽 `max_vel_x`/`max_vel_theta` 도 `TODO-팀확인` 표기가 붙어 있다. 봉투 정합의
  **최종 결정은 팀 합의 사항**이며, 이 워크스페이스는 브리지 쪽 상한만 다룬다.

### 휠 오도메트리 (2026-08-08, 순수 모듈까지 완료)

`stm_serial_bridge/wheel_odometry.py` — `rclpy`·ROS 메시지·serial·**시계**에 의존하지 않는
순수 계산 모듈. `test/test_wheel_odometry.py` 70개 테스트로 검증한다.

| 함수 | 역할 |
|---|---|
| `WheelGeometry` | r·L·counts_per_wheel_rev 묶음. 생성 시 유한·양수 검증 |
| `OdometryState` | 포즈(x, y, theta) + 마지막 raw count. frozen |
| `encoder_delta()` | **int32 래핑 보정**. 단순 뺄셈은 경계에서 약 43억 count 가짜 델타를 만든다 |
| `wheel_distances()` | count 변화량 -> 좌우 이동 거리 |
| `twist_from_distances()` | -> `(v, omega)`. dt 검증은 여기 한 곳에만 |
| `advance()` | 포즈 적분(**midpoint 2차**) + 속도. 새 상태를 반환(입력 불변) |
| `rebaseline()` | 포즈 유지, count 기준만 교체 (STM 재부팅 대응) |

설계상 정해둔 것:

- **속도는 엔코더 델타로 계산한다.** `/stm/wheel_actual_rad_s` 는 펌웨어 명목 77520 기준이라
  약 12% 작다 — 오도메트리에 쓰면 문서화된 스케일 불일치가 코드로 새어 들어간다
- **포즈는 dt 와 무관**하고 **속도만 dt 에 비례**한다. STATUS 에 타임스탬프가 없어 dt 는 수신
  시각 차이로 만들 수밖에 없으므로, 그 지터는 속도에만 실린다
- `theta` 는 `(-pi, pi]` 로 정규화한다 (`nav_msgs/Odometry` 는 쿼터니언이라 누적 회전 수 불필요)

#### 노드 (`wheel_odometry_node.py`, 2026-08-08)

**`stm_serial_bridge` 와 분리된 별도 노드**다. Serial 포트를 열지 않고 브리지가 이미
발행 중인 토픽만 구독한다 — 포트 소유자는 여전히 브리지 하나다.

```
STM32 -> stm_serial_bridge -> /stm/encoder_total -> wheel_odometry -> /wheel/odom
```

| 항목 | 값 |
|---|---|
| 실행 파일 | `wheel_odometry_node` |
| **노드 이름** | **`wheel_odometry`** (YAML 키도 이 이름. 브리지와 같은 규칙) |
| 구독 | `/stm/encoder_total` (`Int32MultiArray [left, right]`) |
| 발행 | `/wheel/odom` (`nav_msgs/Odometry`) |
| 파라미터 | `config/wheel_odometry.yaml` |

```bash
ros2 run stm_serial_bridge wheel_odometry_node --ros-args \
  --params-file install/stm_serial_bridge/share/stm_serial_bridge/config/wheel_odometry.yaml
```

설계 결정 (2026-08-08):

1. **`/odom` 이 아니라 `/wheel/odom` 으로 발행한다.** 이 노드의 출력은 이후 LiDAR
   오도메트리와 융합할 **EKF 의 입력 하나**이지 최종 오도메트리가 아니다.
2. **TF 를 발행하지 않는다.** `odom -> base_link` 는 EKF 의 몫이다. 여기서 쏘면 충돌한다.
   (`ros2 node info /wheel_odometry` 로 `/tf` 발행자가 없음을 확인했다.)
3. **첫 `encoder_total` 은 적분하지 않고 기준만 잡고, 발행도 하지 않는다.** 비교할 이전
   count 도 경과 시간도 없기 때문이다. 속도 0을 지어내 발행하면 소비하는 쪽이 "정지해
   있다는 측정"으로 받아들인다.
4. **`dt <= 0` 이면 발행을 건너뛰되 기준(count·시각)은 유지한다.** 기준을 갱신하면 그 구간의
   이동량이 통째로 버려져 포즈에 영구 오차가 남는다. 유지하면 다음 샘플이 함께 적분한다.
5. **`/stm/wheel_actual_rad_s` 를 구독하지 않는다** (명목 77520 기준이라 약 12% 작다).

⚠️ **기구 상수 3개가 두 YAML 에 중복된다** (`stm_serial_bridge.yaml` / `wheel_odometry.yaml`).
ROS 파라미터에는 파일 간 참조가 없어 중복이 불가피하다. 대신
`test_wheel_odometry_node.py` 가 두 파일의 일치를 강제하므로 **한쪽만 고치면 테스트가
실패한다.**

#### 거리 스케일 보정 — 2026-08-08 실기 1m 직진 x3

| 회차 | 보고 `|Δ|` | Δyaw |
|---|---|---|
| 1 | 1.1012 m | -0.095 rad |
| 2 | 1.1136 m | -0.161 rad |
| 3 | 1.1055 m | -0.147 rad |
| **평균** | **1.1068 m** (실제 약 1.0 m) | **-0.1343 rad** |

오도메트리가 거리를 약 **10.7% 크게** 보고했다. 시작 방위가 0이 아니므로 `Δx` 가 아니라
**변위 크기 `|Δ|`** 로 비교했다(회전 불변). 보고 경로가 약간 휘어 있어 호 길이는 현보다
길지만 그 차이는 0.1% 미만이라 무시했다.

**보정: `wheel_radius_m` 0.065 → `0.065 / 1.1068 = 0.058728` → 채택 `0.0587`** (잔차 -0.05%,
3회 스프레드 ±0.56%보다 훨씬 작다). **오도메트리 설정에만 적용했다.**

**✅ 보정 후 재검증 (2026-08-08, 1m 직진 x2)**: 보고 `|Δ|` = **0.9918 / 1.0112 m**,
평균 **1.0015 m** → 거리 오차 **+0.15%**. 거리 스케일 보정은 확인됐다.

⚠️ **이 값을 "바퀴 반지름 실측치"로 읽으면 안 된다.** 거리에는 `2*pi*r / counts_per_rev`
라는 **곱만** 들어가므로 직진 시험으로 두 인자를 분리할 수 없다. 0.0587 은
(유효 구름반지름 + 슬립 + `counts_per_rev` 오차)를 전부 흡수한 **스케일 보정 상수**다.

⚠️ **브리지의 `wheel_radius_m` 은 0.065 로 두었다.** 그 값은 `/cmd_vel` -> 바퀴 rad/s 변환에
쓰이는 **명목 기구 치수**이고 엔코더가 개입하지 않는다. 게다가 `r=0.065` 를 참으로 두면
이번 데이터가 가리키는 유효 counts/rev 는 약 **75,439** 로, 손회전 실측 68,160 보다
**펌웨어 명목 77,520 에 훨씬 가깝다** — 즉 이 10.7% 의 상당 부분이 반지름이 아니라
**미해결 상태인 엔코더 스케일**일 수 있다. 명령 경로에 옮기면 실제 주행 속도와 속도 봉투
표(4.615/1.754/6.369)가 모두 바뀌므로, 바퀴 실측과 엔코더 원인 규명 후에 합칠지 결정한다.

#### ⚠️ 직진 시 yaw drift — 원인 미확정, 임의 보정 금지

5회 모두 **음(-)의 방향**(우회전)으로 틀어졌고, 보정 후에도 재현됐다.

`Δθ = (d_R - d_L) / L` 이므로 이것은 **각도 문제가 아니라 좌우 이동거리 차이 문제**다.

비교는 반드시 **곡률 `κ = Δyaw / d_c`(rad/m)** 로 한다. `Δθ` 와 `d_c` 가 둘 다 `r` 에
비례하므로 **`κ` 와 `d_L/d_R` 은 `r` 에 무관**하다 — 반지름을 바꿔도 변하지 않는 양이라
보정 전후를 직접 비교할 수 있다.

| 회차 (시간 순) | r | 보고 `\|Δ\|` | Δyaw | **κ (rad/m)** | **d_L/d_R** |
|---|---|---|---|---|---|
| S1-1 | 0.065 | 1.1012 | -0.095 | -0.0863 | +3.33% |
| S1-2 | 0.065 | 1.1136 | -0.161 | -0.1446 | +5.65% |
| S1-3 | 0.065 | 1.1055 | -0.147 | -0.1330 | +5.18% |
| S2-1 | 0.0587 | 0.9918 | -0.197 | -0.1986 | +7.84% |
| S2-2 | 0.0587 | 1.0112 | -0.210 | -0.2077 | +8.22% |
| **세션1 평균** | | 1.1068 | -0.1343 | **-0.1213** | **+4.72%** |
| **세션2 평균** | | 1.0015 | -0.2035 | **-0.2032** | **+8.03%** |

**`wheel_separation_m` 을 바꿔도 이 drift 는 없어지지 않는다.** `d_L = d_R` 이면 `L` 이
얼마든 `Δθ = 0` 이다. `L` 은 좌우 차이를 각도로 환산하는 계수일 뿐이므로, 건드리면 drift 의
**표시 크기만** 바뀌고 원인은 그대로인 채 **진짜 회전까지 왜곡**된다.

##### 관측 1 — 비대칭은 **상수가 아니다** (예측 빗나감)

반지름 보정 시 "보고 drift 가 9.7% 축소될 것"이라 예상했으나, **실제로는 `κ` 가
-0.1213 → -0.2032 로 +67.5% 커졌다.** `κ` 는 `r` 에 무관하므로 이것은 보정 탓이 아니라
**물리적 좌우 비대칭 자체가 커진 것**이다. 회차별로도 3.33 → 5.65 → 5.18 → 7.84 → 8.22% 로
대체로 증가한다.

→ **고정 원인은 설명력이 떨어진다.** 좌우 엔코더 counts/rev 차이나 바퀴 지름 차이는 상수여야
하는데 관측은 상수가 아니다. 반대로 슬립·마찰·기구 헐거워짐·속도 의존 edge 누락처럼
**조건에 따라 변하는 원인**이 남는다. (표본 5개이고 S1-3 < S1-2 이므로 "단조 증가"로
단정하지는 않는다.)

##### 관측 2 — **공통 성분은 안정, 차동 성분만 증가**

`r=0.065` 기준으로 환산해 비교하면:

| | 공통 `d_c` | 차동 `d_L - d_R` | d_L | d_R |
|---|---|---|---|---|
| 세션1 | 1.1068 | 0.0510 | 1.1323 | 1.0813 |
| 세션2 | 1.1090 (**+0.2%**) | 0.0856 (**+68%**) | 1.1518 | 1.0662 |

**평균은 그대로인데 좌우가 평균을 중심으로 대칭적으로 벌어졌다.** 이것은 **원호를 실제로
그렸을 때의 서명**이다 — 원호에서는 바깥 바퀴가 더 가고 안쪽 바퀴가 덜 가며 **평균은 경로
길이와 같다.** 반대로 한쪽 센서만 틀렸다면 평균도 함께 움직였어야 한다.

##### 관측 3 — 실제로 휠 **메커니즘이 존재한다** (PI 게인 0)

`motor_config.h` 의 `MOTOR_PI_KP`/`MOTOR_PI_KI` 는 **아직 0.0f** 이다. 즉 STM 은 바퀴 속도를
**폐루프로 맞추지 않고 Feedforward(개루프)만** 쓴다. 좌우 모터·기어박스·마찰이 조금만 달라도
같은 목표 rad/s 에 대해 **실제 회전 속도가 달라지고 카트는 실제로 휜다.** 배터리 전압이
떨어지면 그 불균형이 변할 수 있어 관측 1의 "변하는 비대칭"과도 맞는다.

→ **현재 가장 유력한 가설: 카트가 실제로 우측으로 휘고 있고, 오도메트리는 그것을 옳게 보고하고
있다.** 그렇다면 이것은 오도메트리 버그가 아니라 **구동계 불균형** 문제이며, 해결도
`wheel_separation_m` 이 아니라 **PI 속도 제어 튜닝** 쪽이다.

##### 관측 4 — 이 가설은 **자로 재면 바로 판별된다**

원호를 가정하면 1 m 주행 후 관측돼야 할 값:

| | 곡률반경 | **횡방향 이탈** | **최종 방위** |
|---|---|---|---|
| 세션1 (κ=-0.121) | 8.25 m | **6.1 cm** | 6.9° |
| 세션2 (κ=-0.203) | 4.92 m | **10.1 cm** | 11.6° |

**10 cm 이탈과 11.6° 기울어짐은 눈으로 바로 보인다.** 실제로 그만큼 벗어나 있으면 오도메트리는
정상이고 원인은 구동계다. 직선에서 1~2 cm 이내이고 차체가 선과 나란하면 drift 는 측정 오차다.

##### 남은 원인 후보

| # | 후보 | 정합 |
|---|---|---|
| 1 | **구동계 불균형으로 실제 회전** | ✅ 관측 2·3 과 일치. 현재 가장 유력 |
| 2 | 좌우 **슬립·마찰** 비대칭 | ✅ 관측 1(변동)과 일치 |
| 3 | 기구 **헐거워짐**(허브·세트스크류 등 진행성) | ✅ 관측 1과 일치. 육안·손 점검 대상 |
| 4 | 좌우 **엔코더 스케일** 차이 | ⚠️ 상수여야 하므로 관측 1과 불일치. 손회전(L 68420/R 67913)도 같은 부호지만 0.75% 뿐 |
| 5 | 좌우 **바퀴 지름** 차이 | ⚠️ 상수여야 하므로 관측 1과 불일치. 그래도 캘리퍼로 싸게 배제 가능 |
| 6 | 한쪽 **엔코더 edge 누락** | △ 속도 의존이면 변동 가능(IC1/IC2Filter=8, TIM2 vs TIM8) |

#### 다음 실측: raw `encoder_total` 측정에서 기록할 값

⚠️ **raw count 만으로는 결론이 나지 않는다.** 오도메트리의 `Δθ` 는 애초에 그 count 에서
계산된 값이므로, `ΔL/ΔR ≈ 1.08` 은 **산술적으로 반드시 나온다.** 새 정보는 **바닥 기준
ground truth 를 함께 재야만** 생긴다.

**가장 깨끗한 실험 — 모터 끄고 가이드를 따라 밀기.** 벽·직선 자를 따라 물리적으로 직진을
강제하면 **좌우 바퀴의 실제 지면 이동거리가 같다는 것이 보장**된다. 그 조건에서 `ΔL/ΔR` 은
엔코더·바퀴지름 비대칭만 담는다.

| 결과 | 해석 |
|---|---|
| 밀기 `ΔL/ΔR ≈ 1.00`, 주행 `≈ 1.08` | 카트가 **실제로 휜다** → 구동계 문제(후보 1·2), 오도메트리는 정상 |
| 밀기도 `≈ 1.08` | **센서·기구 비대칭**(후보 4·5·6) |

**회차마다 기록할 값**:

| 구분 | 항목 |
|---|---|
| 엔코더 | `/stm/encoder_total` 시작/종료의 **raw 2원소 그대로** (`[left, right]`). 델타만 적지 말 것 — int32 래핑 재구성이 불가능해진다. 두 시점 모두 **카트 정지 상태**에서 읽는다 |
| 오도메트리 | `/wheel/odom` 시작/종료 포즈 (count → 오도메트리 계산 교차검증용) |
| 거리 | 줄자 실측 이동거리 + **차체의 어느 점을 기준으로 쟀는지** |
| **방위** | **직선 대비 최종 횡방향 이탈(cm)** 과 **최종 기울기(deg)** ← 이번 측정의 핵심 |
| 조건 | 명령 `linear.x`, `speed_profile`, 주행 시간, 진행 방향(전진/후진) |
| 조건 | 배터리 전압, 적재 하중, 바닥 재질 — 관측 1(변동)의 원인 추적에 필요 |
| 절차 | 회차 사이에 **카트를 물리적으로 다시 정렬했는지** (오도메트리 yaw 가 회차마다 누적되고 있다) |

**계산할 값** (`r`·`counts_per_rev` 가정이 전혀 필요 없다):

```
counts/m (좌) = ΔL / 실측거리      counts/m (우) = ΔR / 실측거리
비대칭        = ΔL / ΔR           거리 스케일   = (ΔL + ΔR) / 2 / 실측거리
```

**현재 설정이 함의하는 기준값**: `68160 / (2*pi*0.0587)` = **184,804 count/m** (좌우 공통).

| 관측 | 의미 |
|---|---|
| `(ΔL+ΔR)/2` ≈ 184,804 (±1% = ±1,848) | 거리 스케일 보정이 맞다 |
| `ΔL/ΔR` ≈ 1.080 (ΔL≈191,938 / ΔR≈177,671) | 세션2 비대칭이 그대로 재현됨 |
| `ΔL/ΔR` ≈ 1.000 | 비대칭이 사라짐 → 조건 의존이라는 증거 |

**이후 순서** (앞 단계가 뒤 단계의 전제):

1. **위 밀기/주행 대조 + 방위 ground truth** — 후보 1·2 vs 4·5·6 을 가른다. 최우선.
2. **바퀴 지름 실측**(양쪽 캘리퍼 + 하중 상태 축-바닥 높이) — 가장 싸고, 후보 5와
   `0.0587 vs 0.065` 를 동시에 본다. 지름이 130 mm 에 가까우면 스케일 오차는 반지름이 아니라
   엔코더 쪽이다.
3. **후진 주행** — 부호가 뒤집히는지로 기구 비대칭과 방향성 원인(바닥 기울기)을 가른다.
4. **속도·하중·배터리 변경 반복** — 슬립·구동 불균형은 변하고 고정 스케일 오차는 안 변한다.
5. 구동계로 확정되면 **PI 게인 튜닝**(`SET_PI_GAINS`)이 해결 경로다. 오도메트리 파라미터가
   아니다.

**`wheel_separation_m` 캘리브레이션(제자리 360° 회전)은 위가 정리된 뒤에 한다.** 좌우 스케일이
틀린 상태에서 `L` 을 맞추면 두 오차가 서로를 가려 둘 다 틀린 값으로 수렴한다.

#### ⚠️ 남은 것 (10d/10e)

- **STM32 재부팅을 탐지하지 않는다.** 실행 중 카운터가 0으로 초기화되면 **포즈가 크게 튄다.**
  순수 모듈에 `rebaseline()` 이 준비돼 있지만 호출 조건이 아직 없다.
  ⚠️ **`/stm/connected` 의 false -> true 전이만으로 모든 reset 을 잡을 수 있다고 가정하지 말 것**
  — STATUS 가 끊기지 않을 만큼 빠른 재부팅이나, 연결이 유지된 채 카운터만 초기화되는 경로를
  놓칠 수 있다. 탐지 방법 자체를 먼저 정해야 한다.
- **공분산이 0으로 비어 있다.** 근거 있는 값이 없어 채우지 않았다. **EKF 연결 전에 반드시
  설정해야 한다** — 0을 "오차 없음"으로 읽는 융합기가 있다. 노드가 시작 시 경고를 남긴다.
- **launch 파일에 통합하지 않았다.** 현재는 `ros2 run` 으로만 띄운다.
- **하드웨어 미검증.** `ros2 topic pub` 으로 만든 가짜 count 로만 확인했고, 실제 주행에서
  오도메트리가 실제 이동량과 얼마나 맞는지는 **측정하지 않았다.**

### 수동 지도 작성 모드 — `cart_teleop` (2026-08-04 추가)

LiDAR + slam_toolbox 를 띄운 상태에서 **SSH 터미널의 WASD 로 직접 주행**하며 지도를
만드는 모드다. 경로는 다음과 같고, teleop 은 **Serial 포트를 열지 않는다** —
포트 소유자는 여전히 `stm_serial_bridge` 하나다.

```
SSH 키보드 → cart_teleop → /cmd_vel → stm_serial_bridge → STM32
```

**패키지**: `src/cart_teleop/` (`ament_python`). 의존성은 `rclpy`·`geometry_msgs` 뿐이다.

#### 실행

```bash
export ROS_LOCALHOST_ONLY=1      # 다른 머신의 /cmd_vel 차단 (필수)
cd ros2_ws
source /opt/ros/humble/setup.bash && source install/setup.bash

# 터미널 1 — LiDAR + rf2o + slam_toolbox (embedded/Lidar 워크스페이스)
ros2 launch choll_slam_bringup bringup.launch.py

# 터미널 2 — Serial Bridge (검증된 slow 프로파일)
ros2 launch stm_serial_bridge stm_serial_bridge.launch.py speed_profile:=slow \
  2>&1 | tee ~/stm_$(date +%Y%m%d_%H%M%S).log

# 터미널 3 — ★ /cmd_vel 발행자가 teleop 하나뿐인지 확인 (teleop 실행 전/후 모두)
ros2 topic info /cmd_vel -v

# 터미널 4 — teleop. ros2 launch 가 아니라 ros2 run 이다
ros2 run cart_teleop keyboard_teleop
```

⚠️ **`ros2 launch` 로 실행하지 않는다.** launch 는 stdin 을 tty 로 넘겨주지 않아 키
입력을 받을 수 없다. 그래서 이 패키지에는 launch 파일이 없다. stdin 이 TTY 가 아니면
teleop 은 명확한 오류를 찍고 종료 코드 1 로 끝난다.

#### 키

| 키 | 동작 | 값 (최대 단계) |
|---|---|---|
| `W` | 전진 | `linear.x = +0.13 m/s` |
| `S` | 후진 | `linear.x = -0.13 m/s` |
| `A` | 제자리 좌회전 | `angular.z = +0.60 rad/s` (REP 103 반시계) |
| `D` | 제자리 우회전 | `angular.z = -0.60 rad/s` |
| `Space` | **정지 명령**(zero Twist) | `0, 0` |
| `+` 또는 `=` / `-` | 속도 단계 증가/감소 | 5단계, 기본 5(=최대) |
| `q` / `Esc` | 정지 후 종료 | — |

선속도와 각속도를 **동시에 섞지 않는다**(직진은 `angular.z=0`, 제자리 회전은
`linear.x=0`). 곡선 주행이 필요하면 Nav2 경로로 전환한다.

`=` 는 `+` 의 별칭이다 — 대부분의 배열에서 `+` 는 Shift 가 필요해 주행 중 조작이
번거롭기 때문이다. 동작은 완전히 같다.

기본값 `0.13 m/s` / `0.60 rad/s` 는 2026-08-04 실기에서 확인한 범위이며, 각각 바퀴
`2.0` / `±1.754 rad/s` — **`speed_profile:=slow` 상한 이내**다. 최종 상한 방어선은
teleop 이 아니라 **Bridge 의 `speed_profile`** 이다.

#### ⚠️ 터미널은 키 릴리즈를 감지할 수 없다 — command lease 방식

터미널(cbreak/raw)에서 얻는 것은 키 *누름* 문자뿐이다. 그래서 "키를 놓으면 정지"를
**command lease** 로 근사한다:

- W/S/A/D 입력마다 유효시간(`input_timeout_sec`, 기본 **1.0초**)을 갱신한다
- 키를 누르고 있으면 OS 자동반복이 lease 를 계속 갱신해 주행이 이어진다
- 손을 떼면 자동반복이 끊기고 **1.0초 뒤 zero Twist** 로 전환한다(`TIMEOUT`)
- lease 가 만료되면 동작을 폐기하므로 **다시 움직이려면 새 키가 필요하다**

⚠️ 자동반복 초기 지연(약 0.5초)보다 timeout 이 짧으면 "움직임→정지→움직임" 끊김이
생긴다. 1.0초는 그보다 크게 잡은 값이다.

#### `/cmd_vel` 발행자 충돌 방지

teleop 은 **시작 시와 실행 중 주기적으로**(기본 2Hz) `/cmd_vel` 의 외부 Publisher 수를
센다. 하나라도 있으면 **`DISARMED`** 로 전환해 non-zero 명령을 발행하지 않고 화면에
충돌을 표시한다.

- 충돌이 사라져도 **자동으로 재가동하지 않는다** — 사용자가 새 W/S/A/D 를 눌러야 한다
  (누르지 않은 명령으로 갑자기 출발하는 것을 막기 위함)
- 상태 표시: `ARMED` / `STOPPED` / `TIMEOUT` / `DISARMED` / `QUIT`

#### 실기 검증 상태 (2026-08-04)

**확인됨** — `mode:=hardware`, `speed_profile:=slow`, 실제 STM32·모터 연결:

- Linux 터미널에서 **W/S/A/D 입력에 따라 실제 로봇이 동작**한다
- 키를 **짧게 한 번** 누르면 잠시 주행한 뒤 **command lease 만료로 자동 정지**한다
  — `input_timeout_sec` 기반의 **의도된 안전 동작**이다
- teleop 키 조작이 전반적으로 정상 동작한다

**확인 필요** — 실기에서 사용한 `input_timeout_sec` 실제 값. 코드 기본값은 **1.0초**지만,
실행 시 `-p input_timeout_sec:=...` 로 덮어썼는지는 확인할 수 없다. teleop 노드는
Bridge 의 `_log_parameters()` 와 달리 **파라미터를 로그에 남기지 않아** 실행 기록으로
역추적이 불가능하다(후속 개선 대상).

**미검증** — 아래는 이번 실기로 확인되지 않았다:

- **낮은 속도 단계의 바닥 데드밴드** — 단계 4 이하는 바퀴 ≤1.6 rad/s → 개루프 PWM ≤16.
  PWM<20 은 비선형(데드존)으로 기록돼 있어 안 움직일 수 있다
- **실제 주행 속도·회전각 수치 정확도** — 측정하지 않았다
- **LiDAR/slam_toolbox 동시 실행** 및 **실제 지도 작성 품질**
- **장시간 SSH 세션에서의 입력 지연·안정성**

#### ⚠️ 경고

- **지도 작성 중에는 Nav2 와 AI launch(`follow_robot_launch.py`)를 실행하지 않는다.**
  AI 의 `control_node` 는 조건 없이 `/cmd_vel` 을 15Hz 로 발행하고, Nav2 는
  `velocity_smoother` 로 20Hz 로 발행한다 — 어느 쪽이든 teleop 과 이중 발행이 된다.
- **Nav2 P2P 로 전환하기 전에 teleop 을 반드시 종료한다**(`q`/`Esc`). 종료 후
  `ros2 topic info /cmd_vel -v` 로 Publisher 수를 다시 확인한다.
- `Space` 는 **정지 명령(zero Twist)** 이다. **ESTOP 이 아니다** — 현재 Bridge 에는 STM
  `ESTOP`/`STOP` 명령 송신 인터페이스가 없다.
  **실제 비상정지는 물리 전원 차단이 필요하다.**
- 종료 경로(`q`/`Esc`/`Ctrl+C`/예외/`ExternalShutdownException`)는 모두 **zero Twist 를
  20ms 간격 5회 발행 → 터미널 설정 복원** 을 거친다. `tty.setcbreak()` 를 쓰므로
  **Ctrl+C 가 SIGINT 로 계속 동작**한다(`tty.setraw()` 면 문자로 삼켜져 종료되지 않는다).
- ⚠️ **다른 셸에서 `kill -INT <ros2 run PID>` 로 죽이지 말 것.** 그 신호는 노드에 닿지
  않아 종료되지 않고 **터미널이 cbreak 로 남는다**(에코가 안 보이는 상태). 정상 종료는
  터미널에서 `q`/`Esc`/`Ctrl+C` 다. 부득이하면 프로세스 그룹으로 보낸다:
  `kill -INT -<PGID>`. 터미널이 망가졌으면 `stty sane` 으로 복구한다.

### mock 으로 검증되는 것 / 안 되는 것

**검증됨** (2026-08-04, mock): 6개 토픽 발행과 원소 수, `connected` true 전이,
`fault` 발행, `/cmd_vel → SET_WHEEL_VEL → mock → STATUS → encoder_total` 왕복,
STATUS 중단 시 `status_timeout_sec`(0.5s)로 `connected=false` 전이.

**검증됨** (2026-08-04, mock): 속도 프로파일 실효성.

- 직진 `linear.x=0.3`(요구 4.615) → `bench→1.000,1.000` / `slow→2.000,2.000` /
  `nav2→4.615,4.615` / `max_wheel_rad_s:=3.5→3.500,3.500`
- 최악 조합 `linear.x=0.3, angular.z=0.6`(요구 left 2.862 / right 6.369) →
  `nav2→2.862,6.369` (**제한 없이 통과**) / `slow→0.899,2.000` (비례 축소,
  좌우 비율 `0.449275362` 가 원본과 **정확히 동일**)
- `speed_profile:=turbo` 는 실패. `slow`+`max_wheel_rad_s` 동시 지정 시 인자가 이김.

**검증됨** (2026-08-04, mock): `cart_teleop` 경로 —
`teleop → /cmd_vel → Bridge(mock, slow) → SET_WHEEL_VEL` 왕복.
`W→2.000,2.000` / `A→-1.754,1.754` / `D→1.754,-1.754` / `Space·timeout→0.000,0.000`.
상태 전이 `ARMED→DISARMED→STOPPED→ARMED→QUIT` 와 외부 Publisher 감지·자동 재가동 금지,
비-TTY 실행 시 종료 코드 1 확인. **실제 모터로는 미검증.**

**검증됨** (2026-08-04, **실기**): `speed_profile:=slow` 로 hardware 모드 실행 —
`serial_port` 는 STLink **by-id 경로** 사용, 바퀴 공중. `check_stm_topics` 통과(6개 토픽),
`linear.x=0.3`(3초) → slow 프로파일이 좌우 목표를 **2.0 rad/s 로 제한**, 좌우 바퀴가 전진
방향으로 회전, `/cmd_vel` 종료 후 **watchdog 정지**, fault 없음.
후진·좌우 회전은 이번에 생략했다 — 방향 매핑은 2026-08-02/08-03 통합 테스트에서 이미
확인했고, 이번 변경 범위가 launch·속도 상한이기 때문이다.

이어서 **바닥 주행**도 확인했다(같은 프로파일, `linear.x=0.3` → 1초 후 zero Twist):
차체가 실제로 전진하고 명령 종료 후 정상 정지했으며, 급가속·위험한 움직임은 없었다.
이동량 관측값은 **약 5.8 cm** 였다.
⚠️ **이 값을 1초 주행거리나 속도(0.058 m/s)로 환산하지 않는다** — 발행 창 1초에 ROS2 CLI
기동·discovery 시간이 포함될 수 있다. 계산상 0.13 m/s 와의 차이 원인도 이 테스트만으로는
판정하지 않는다. **속도 정확도는 미검증 유지.**

**바닥 제자리 회전**도 확인했다(같은 프로파일, `linear.x=0.0, angular.z=0.6` → 약 1초 후
zero Twist): `/stm/wheel_target_rad_s` 가 **약 `[-1.754, 1.754]`** 로 발행되고 좌우 바퀴가
반대 방향으로 돌아 차체가 **왼쪽(반시계)으로 제자리 회전**했으며, 명령 종료 후 정상 정지,
fault 없음. 이 결과가 확인해 주는 것 두 가지:

- **`L=0.38` 실측값이 실제로 STM 까지 반영된다.** 직진은 `L` 과 무관하므로 앞선 전진
  테스트로는 확인할 수 없었던 부분이다(1.754 = `0.6 × 0.38/2 / 0.065`).
- **`slow`(2.0)가 제자리 회전 봉투를 비례 축소 없이 통과시킨다** — 2.0 을 고른 근거가
  실기로 확인됐다(1.754 < 2.0).
- REP 103 부호 규약도 맞다: `angular.z > 0` → 반시계 → 왼쪽 바퀴 음수·오른쪽 양수.

⚠️ **회전각은 측정하지 않았다** — 실제로 몇 도 돌았는지, `ω=0.6 rad/s` 와 일치하는지는
**미검증**이다.

**검증 안 됨** — mock 은 STM32 를 **모방**할 뿐이다:

- `wheel_actual_rad_s` 의 **수치 정확도** (엔코더 스케일 12.1% 미확정. 실기 측정만이 판정 가능)
- 실제 모터 구동·부하·전류, 실제 USB Serial 전기적 특성
- 실제 Stall 발생 시 **펌웨어의** FAULT 판정 (mock 은 `--fault-after-sec` 로 흉내만 냄)
- USB 강제 분리 시 RX fatal error 처리
- mock 은 `actual = target` **스텁**이다. 관성·마찰·PI 제어를 흉내내지 않으므로
  제어 성능은 판단할 수 없다.

### 알려진 거친 부분

- launch 에 SIGINT(Ctrl+C)를 주면 브리지 노드가 `destroy_node()` 중 `KeyboardInterrupt`
  traceback을 찍고 exit code -2 로 죽는다(launch 는 이를 ERROR 로 보고). **기능 영향은
  없으나 로그가 시끄럽다.** 노드 종료 경로의 문제이며 이번 작업 범위에서 고치지 않았다.

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
- ⚠️ **위 `angular.z=±0.433333` 은 `wheel_separation_m=0.30`(당시 placeholder) 기준 값이다.**
  실측 **0.38** 로 바뀐 뒤에는 같은 명령이 한쪽 바퀴만 돌리지 않는다
  (`linear.x=0.065, angular.z=-0.433333` → 좌 2.267 / 우 -0.267).
  **지금 한쪽 바퀴만 돌리려면 `angular.z=±0.342105`** 를 쓴다 (= `linear.x / (L/2)`).
  위 기록 자체는 2026-08-03 당시 실제로 실행한 값이므로 그대로 보존한다.
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
- **`actual_rad_s` 수치 정확도** — STM 감속비 정정(100:1 → 51:1) 펌웨어의 빌드·플래시와 전진/후진
  동작 확인은 **2026-08-04 완료**됐다(보고값이 이전보다 약 1.96배 커진다). 그러나
  **보고값이 실제 회전 속도와 일치하는지는 아직 측정하지 않았다.** 검증은 목표/보고 속도 비교가
  아니라 **바퀴 1회전 전후 `/stm/encoder_total` 차이 측정**으로 한다
- ~~`wheel_separation_m=0.30` 실측 확정~~ → **2026-08-04 완료: 0.38 m**
  (좌우 구동 바퀴 트레드 중심선 간 거리). 이 값으로 회전 성분과 `nav2` 프로파일(6.0→6.4)을
  재계산했고, **바닥 제자리 회전 실기로 STM 반영까지 확인**했다(목표 `[-1.754, 1.754]`)
- ~~실제 바닥 주행~~ → **2026-08-04 완료** (`slow` 프로파일로 전진·정지·제자리 회전).
  ⚠️ `bench`·`nav2` 프로파일의 바닥 주행은 여전히 미검증
- STATUS 수신이 끊겼을 때 주행 명령을 강제로 0으로 만드는 추가 안전 정책(8d)
- **`slow`(2.0) 프로파일의 속도·회전각 수치** — 전진·정지·회전 **동작**은 2026-08-04
  확인했으나 **수치는 미검증**이다. 직진: 실제 속도가 0.13 m/s 인지 측정하지 않았고,
  이동량 관측(약 5.8 cm)은 발행 창에 CLI 기동·discovery 시간이 섞여 있어 속도로 환산할 수
  없다. 회전: 실제 회전각을 측정하지 않아 `ω=0.6 rad/s` 와 일치하는지 알 수 없다
- **`nav2`(6.4) 프로파일** — 실기 미검증 (mock 에서 송신값만 확인). **바닥 주행 미검증**
- **`bench`(1.0) 이 바닥에서 움직이는지** — **미검증**. 모터 데드밴드 미만일 가능성

### 엔코더 스케일: 실측 2회 재현 완료 / 원인 미확정 (2026-08-03, 08-08)

`/stm/encoder_total`로 출력축 수동 회전 Count를 측정했다. 아래 값은 모두 **바퀴 1회전당
count**의 평균이다 — 누적 count가 아니다.

| 대상 | 2026-08-03 (좌우 각 4회전) | 2026-08-08 (좌우 각 10회, 이상치 제거) |
|---|---|---|
| Left | 68107.75 | 약 68420 |
| Right | 68217.25 | 약 67913 |
| **좌우 전체 평균** | **68162.5** | **약 68167** |

- **완료**: 출력축 1회전당 Count 실측 및 **재현 확인**. 통합 평균이 두 차례 사실상 같은 값으로
  나왔으므로 명목값과의 약 12% 차이는 1회성 측정 실수가 아니다
- **완료**: STM 감속비 오기재 발견 → `MOTOR_GEAR_RATIO` 100.0f → **51.0f**(구매 사양)로 정정.
  명목값이 152000 → **77520**(= 380 × 51 × 4)으로 바뀌었다
- ⚠️ **좌우 편차는 재현되지 않았다**: 08-03은 Right가 약 0.16% 컸고, 08-08은 Left가 약 0.75%
  크다 — 크기도 부호도 달라졌다. 두 측정 모두 손 회전이라 "정확히 1회전" 오차가 값에 섞여
  있다. **좌우 차이를 하드웨어 특성으로 확정하지 않으며, 좌우 개별 보정값도 두지 않는다**
- **미완료**: 실측 약 68160이 명목 77520보다 약 **12.1% 작은 원인**이 CPR 380의 정의 /
  Quadrature 해석(x4) / 타이머 입력 필터(`IC1Filter`/`IC2Filter`=8) / 실제 감속비 중
  무엇인지 **확정되지 않았다**
- **미완료**: `MOTOR_ENCODER_CPR`·`MOTOR_ENCODER_QUADRATURE_MULTIPLIER`·실제 감속비 확정
- 상세: `embedded/motor/docs/serial_protocol.md`의 "Actual Wheel Velocity 계산" 절,
  `motor_config.h`의 `MOTOR_ENCODER_COUNTS_PER_WHEEL_REV` 주석

#### ⚠️ 펌웨어와 ROS의 스케일이 현재 서로 다르다 (의도된 일시적 상태)

| 계층 | 상수 | 값 | 영향 |
|---|---|---|---|
| STM32 펌웨어 | `MOTOR_ENCODER_COUNTS_PER_WHEEL_REV` | **77520** (명목) | `/stm/wheel_actual_rad_s`, PI 오차 입력, Stall 판정 |
| 이 워크스페이스 | `counts_per_wheel_rev` 파라미터 | **68160** (실측, 좌우 공통) | Wheel Odometry (구현 예정) |

2026-08-08 결정: **Wheel Odometry는 실측 68160을 쓰고, 펌웨어의 77520은 이번에 바꾸지 않는다.**
펌웨어 상수는 속도 **보고**만이 아니라 **PI 제어 입력과 Stall 판정까지** 함께 바꾸므로,
원인 규명을 포함한 별건의 **Encoder Scale Calibration** 작업에서 다룬다.

그때까지:

- `/stm/wheel_actual_rad_s`는 여전히 실제보다 **약 12% 작게** 보고된다
- 그 값과 odometry가 산출한 속도를 **같은 축에서 직접 비교하지 않는다.** 약 12% 차이는
  버그가 아니라 이 불일치다
- 두 값을 함께 쓰는 로직(교차 검증 등)은 불일치가 해소되기 전까지 만들지 않는다
