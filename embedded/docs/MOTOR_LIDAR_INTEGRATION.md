# 모터 + LiDAR 통합 실기 검증 — 작업 인계 및 3단계 계획

> 브랜치 `em/feature/motor-Lidar-integrated` (HEAD `355cb0d`) 기준.
> 작업 위치는 **저장소 루트 `/home/ssafy/S15P11C101`** — 워크스페이스가 두 개라서
> `embedded/Lidar`만으로는 모터 쪽을 다룰 수 없다.
> 작성: 2026-08-04 / Jetson Orin Nano 실기에서 직접 확인한 사실만 기록.

---

## 0. 다음 세션에서 Claude에게 할 말 (복사해서 쓰기)

```
작업 위치는 /home/ssafy/S15P11C101 (브랜치 em/feature/motor-Lidar-integrated).
embedded/docs/MOTOR_LIDAR_INTEGRATION.md 를 먼저 읽고 이어서 진행해줘.
워크스페이스는 두 개다: embedded/Lidar(SLAM/Nav2), ros2_ws(모터 브릿지+teleop).
Phase 1(WASD 수동주행) → Phase 2(AI 카메라 추종) → Phase 3(매핑+Nav) 순서로 간다.
dialout 권한은 방금 해결했으니 그것부터 검증하고 Phase 1을 시작해줘.
```

세부 측정 데이터·설계 근거가 더 필요하면 `~/.claude/plans/readme-step-validated-breeze.md`
(LiDAR 단독 브링업 계획서 + 시야 실측 원자료)를 함께 참조할 것.

---

## 1. 지금 상태 (사실만)

### 브랜치 / 통합
| 항목 | 값 |
|---|---|
| 현재 브랜치 | `em/feature/motor-Lidar-integrated` @ `355cb0d` (origin과 동일, 워킹트리 깨끗) |
| LiDAR 작업 포함 | ✅ `4fd5a44` (cart/cancel 타입 String(requestId)) 까지 포함 |
| 모터 작업 포함 | ✅ `1a1f7a5` (ROS2 수동 주행 teleop) 까지 포함 |
| `embedded/Lidar` 소스 | `em/feature/Lidar`와 **완전 동일** (`git diff --stat` 결과 0건) → 기존 빌드 그대로 유효 |

### 워크스페이스 2개
| 경로 | 내용 | 빌드 상태 |
|---|---|---|
| `embedded/Lidar` | `choll_slam_bringup`, `choll_nav`, `choll_nav2` + upstream(`ydlidar_ros2_driver`, `rf2o_laser_odometry`) | ✅ **5 packages finished** (2026-08-04, symlink-install) |
| `ros2_ws` | `stm_serial_bridge`, `cart_teleop` | ✅ **2 packages finished** (2026-08-04). 실행파일: `stm_serial_bridge_node`, `check_stm_topics`, `mock_stm`, `keyboard_teleop` |

두 워크스페이스는 **각각 source** 한다 (합치지 않음 — `ros2_ws/CLAUDE.md` 정책).

### 검증 완료 (Jetson 실기)
- apt 의존성 전부 설치됨: `slam-toolbox 2.6.10`, `navigation2 1.1.20`, `nav2-bringup`, `nav2-map-server`, `rmw-cyclonedds-cpp`
- YDLidar SDK(`/usr/local/lib/cmake/ydlidar_sdk`) + udev 규칙 기존 설치돼 있음
- `ydlidar.service`(AI 파트 자동기동 서비스) **stop + disable 완료** → 포트·`/scan`·정적TF 충돌 제거
- `colcon build --symlink-install` → 5 packages 통과. **yaml·launch 편집은 리빌드 불필요**(심볼릭 확인), 단 노드 재기동 필요
- `pytest src/choll_nav/test/test_nav_logic.py` → **31 passed**
- `ruff check`(repo pyproject) → **All checks passed**
- **`/scan` 11.34 Hz**, 발행자 1개, 440빔, `angle ±180°`, `range 0.12~10.0 m`, `frame_id=laser_frame`
- 패키지 우선순위 확인: `ros2 pkg prefix ydlidar_ros2_driver` → 우리 워크스페이스 install (구 `~/ydlidar_ros2_ws` 아님)

### ✅ Phase 1 완료 (2026-08-04 실기) — 상세 기록은 [tests/TEST_LOG.md](../../tests/TEST_LOG.md) 최상단

`teleop → /cmd_vel → stm_serial_bridge → STM32 → 모터` 전 구간을 **통합 브랜치에서 원본 증거와 함께**
재검증했다. 증거 파일: `ros2_ws/log/phase1_20260804/`.

- 공중: 전진·후진·좌/우 제자리 회전, watchdog 0.501초, 램프 0.2 rad/s/틱, PWM=10×rad/s
- 회전 target `∓1.754` 확인 → **`wheel_separation_m=0.38` 실측값이 실제 경로에 반영돼 있음**
- 바닥: **3.5×3.5 m 구역 주행**, 속도 단계 5/5 유지, STALL·FAULT·ERROR **0건**
- **`Space` 정지**(공중+바닥 부하)와 **DISARMED 충돌 차단** 실기 최초 확인
- **`dialout` 권한 해결됨** — Jetson 재부팅 후 네이티브 적용, `sg dialout` 래핑 불필요

#### 🔴 이번에 실측으로 확정한 안전 사실 (Phase 2·3에 그대로 적용)

| 사실 | 값 / 함의 |
|---|---|
| **펌웨어 통신 타임아웃** | **약 5.0초** (`motion_controller.c:14` 5000u가 실동작값, 주석 2곳의 "300ms"는 stale). 브릿지가 죽으면 STM32는 최대 5초간 마지막 속도 유지 → 0.13 m/s면 **약 0.65 m 추가 주행**. 주행 방향 여유 거리 확보 필수 |
| **브릿지는 종료 시 정지 명령을 보내지 않는다** | 주행 중 Ctrl+C 하면 위 5초가 그대로 적용된다. **종료 순서가 안전 속성**: teleop `q` → 발행자 0 확인 → `target/pwm` 0 확인 → 그 다음 브릿지 |
| **개루프 데드존 `PWM<20`** | PWM 4 → 무회전 / PWM 8 → 한쪽만 1.18 rad/s / PWM 20 → 대칭. **바닥에서는 속도 단계 5/5 고정**, 안 움직이면 즉시 키를 놓을 것(계속 누르면 PI 적분이 PWM 80까지 올라가 STALL 래치) |
| **STALL 래치는 Jetson에서 복구 불가** | `RESET_STALL` 미구현 → **NUCLEO RESET(NRST) 또는 전원 재투입**만 |
| **NUCLEO B1은 래치를 *걸고* 해제하지 못한다** | `latched_stopped`는 부팅(`StopController_Init()`)에서만 0. 해제는 **RESET(NRST)/전원 재투입**. "B1으로 해제"는 오류 |
| **비상 정지 수단** | ROS에서 ESTOP 불가(브릿지가 `STOP`/`ESTOP` 송신 미구현, 유일한 도구는 Windows 전용). → **전원 차단**이 실질적 비상 수단 |
| **`speed_profile` 기본값은 `bench`(1.0)** | 바닥 데드밴드 미만 가능 → **`speed_profile:=slow` 명시 필수** |
| 이전 세션 래치는 포트 개방으로 지워지지 않는다 | 증상: `connected=true`·STATUS 정상인데 TX는 nonzero인데도 `wheel_target`이 `[0,0]` 고정 → **첫 주행 전 RESET 한 번** |

### 미검증 (아직 안 함)
`/odom_rf2o` · `/map` · TF 체인 `map→odom→base_link→laser_frame` · RViz ·
AI 추종 · 지도 저장 · Nav2 벤치 · slow 프로파일의 **속도 정확도**(m/s 환산 안 함) ·
`bench`·`nav2` 프로파일 바닥 주행 · 속도 단계 ≤4 바닥 주행(STALL 위험으로 의도적 미실시)

### 하드웨어 인식 상태
| 장치 | 경로 | 권한 | 상태 |
|---|---|---|---|
| YDLIDAR X4 Pro (CP2102 `10c4:ea60`) | `/dev/ttyUSB0` (= `/dev/ydlidar`) | `crw-rw-rw-` (udev 0666) | ✅ 정상 |
| STM32 (ST-LINK/V2.1 `0483:374b`) | `/dev/ttyACM0` (= `/dev/serial/by-id/usb-STMicroelectronics_STM32_STLink_066FFF525771555067235049-if02`) | `crw-rw---- root:dialout` | ✅ 정상 (`dialout` 적용 완료 — §2 B1 해결) |
| 카메라 | Logitech Brio 100 (`046d:094c`) | — | 인식됨 |

모터 담당자 안내의 PORT 탐색 명령은 그대로 동작함 (`-if02` 심링크 존재 확인).

---

## 2. 🚨 블로커 3건 — 이 순서로 해결

> **B1·B2는 2026-08-04에 해결됨.** B1은 `sudo usermod -aG dialout $USER` + Jetson 재부팅으로
> 네이티브 적용됐다(이제 `sg dialout` 래핑 불필요). B2는 **`ROS_DOMAIN_ID=42` 도메인 분리**로
> AI 스택을 종료하지 않고 우회했다 — Phase 2에서는 반대로 AI가 `/cmd_vel` 주역이므로 domain 0을 쓴다.
> **B3(라이다 실측·마스킹)만 남아 있고, Phase 3-1의 선행 조건이다.**
> 아래 진단·절차는 재발 시 참고용으로 보존한다.

### B1. `dialout` 그룹 권한 (사용자 sudo 필요) — ✅ 해결됨

**증상**
```
$ python3 -c "import serial; serial.Serial('/dev/ttyACM0', 115200)"
SerialException [Errno 13] could not open port /dev/ttyACM0: Permission denied
```

**원인**: `/dev/ttyACM0`은 `crw-rw---- root:dialout`인데 `ssafy`가 `dialout`에 없다.
```
$ id -nG            # ssafy adm cdrom sudo audio dip video plugdev render i2c lpadmin gdm ...  ← dialout 없음
$ getent group dialout
dialout:x:20:       # ← 멤버 0명
```
라이다(`ttyUSB0`)는 udev 규칙이 `MODE:="0666"`을 주므로 예외적으로 잘 열린다. STM32에는
그런 규칙이 없어 그룹 멤버십이 유일한 통로다.

**해결**
```bash
sudo usermod -aG dialout $USER
getent group dialout                      # dialout:x:20:ssafy  ← 멤버 확인
```

**적용 범위가 핵심** — `usermod`는 **이미 떠 있는 프로세스에는 소급 적용되지 않는다.**
현재 SSH/VS Code 서버 프로세스에서 파생되는 모든 셸(Claude의 도구 셸 포함)은 여전히 구
그룹 목록을 갖는다. 셋 중 하나를 골라야 한다.

| 방법 | 적용 범위 | 비고 |
|---|---|---|
| **SSH 완전 종료 후 재접속** (권장) | 새 세션 전체 | VS Code Remote면 서버까지 내려야 함 (`Remote-SSH: Kill VS Code Server on Host`) 또는 재부팅 |
| `newgrp dialout` | 실행한 그 셸만 | 대화형 터미널에서 즉시 쓸 때 |
| `sg dialout -c '<명령>'` | 그 명령 하나만 | 재접속 없이 Claude 도구 셸에서 검증할 때 유용 |

**검증** (아래 둘 다 통과해야 Phase 1 시작 가능)
```bash
id -nG | tr ' ' '\n' | grep -x dialout
python3 -c "import serial; s=serial.Serial('/dev/ttyACM0',115200,timeout=0.5); print('OPEN OK'); s.close()"
```

**선택 — ModemManager 간섭 차단**: Ubuntu의 ModemManager가 `ttyACM*`을 모뎀으로 오인해
연결 직후 잠깐 물고 AT 명령을 쏘는 경우가 있다. 첫 개방 시 쓰레기 데이터나 일시적
`Device busy`가 보이면 아래 중 하나로 차단한다.
```bash
# (a) 이 장치만 무시하도록 udev 규칙 (권장 — 서비스는 살려둠)
sudo tee /etc/udev/rules.d/99-stm32-ignore-mm.rules <<'EOF'
SUBSYSTEM=="tty", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="374b", ENV{ID_MM_DEVICE_IGNORE}="1", MODE:="0666"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger
# (b) 서비스 자체를 끔
sudo systemctl mask ModemManager
```
(a)는 `MODE:="0666"`도 같이 주므로 **dialout 없이도 열린다** — 라이다와 같은 방식으로
통일하고 싶으면 이쪽이 더 깔끔하다.

### B2. AI 스택이 `/cmd_vel`을 점유 중 (현재 실행 중)

```
PID 12774  ros2 launch person_follow_robot follow_robot_launch.py fe_bridge:=true ...   (1시간+ 실행)
노드: camera_node control_node detector_node reid_node tracker_node target_position_node motor_node fe_bridge_node debug_visualization_node
/cmd_vel  Publisher count: 1   ← control_node
/scan     Publisher count: 0   ← 라이다 드라이버가 없는 상태 (내가 STEP A 후 정리함)
```
- **Phase 1(teleop)·Phase 3(Nav2) 에서는 반드시 종료**해야 한다. `/cmd_vel` 발행자는 항상 1개여야 하고,
  `cart_teleop`은 외부 발행자를 감지하면 안전상 non-zero 발행을 스스로 차단한다.
- **Phase 2에서는 이게 주역**이다 (AI가 `/cmd_vel`을 발행해 카트를 움직임).
- 종료: `pkill -f follow_robot_launch` 또는 해당 터미널에서 Ctrl+C.

### B3. 라이다 실측값·시야 마스킹 미반영 (Phase 3 전 필수, Phase 1·2는 무관)

현재 `lidar.launch.py`의 정적 TF는 **임시 플레이스홀더**다.
```
--x 0.0  --y 0.0  --z 0.20     ← 현재
--x 0.30 --y 0.0  --z 0.25     ← 실측(임시 장착, 사용자 제공). yaw는 기둥 대칭축 +0.51° → 0 확정
```
그리고 `x4pro.yaml`의 `ignore_array`가 비어 있다. 100스캔 1° 빈 실측 결과:

| 구간 | 폭 | 중앙거리 | 판정 |
|---|---|---|---|
| −80..−70° | 11° | **0.130 m** | 우측 기둥(접촉) |
| −94..−85° | 10° | 전부 무효 | 완전 차폐 |
| **+50..+89°** | **40°** | 0.427 m | 좌측 기둥(+76..+83° @0.140 m) + 주변 구조물 |
| +97..+106 / +112..+116 / +164..+167° | 10/5/4° | 0.57~0.72 m | 구조물 의심 (미확정) |

유효 빈 248/360(68.9%). **전방(−90~+90°) 59% vs 후방 79%** — 즉 팀이 전제했던
"선반 때문에 전방 180°만 유효"는 **데이터와 반대**다. `angle_min/max`를 ±90°로 자르면
좋은 쪽 절반을 버린다. 게다가 rf2o는 FOV가 x축 대칭이라 가정하므로(`angle_min`을 쓰지 않음)
비대칭 크롭은 오도메트리를 편향시킨다. → **±180 유지 + `ignore_array`로 실측 구간만 마스킹**.

⚠️ 기둥 실측 0.140 m는 현재 `range_min: 0.12`를 **통과**한다. 마스킹 없이 매핑하면
카트 자기 구조물이 지도(`.pgm`)와 costmap에 **영구 장애물로 박힌다.** footprint 0.70×0.64의
inscribed 반경은 0.32 m이므로, 0.32 m 안에 lethal 셀이 생기면 로봇 중심 셀이 253이 되어
**DWB 모든 궤적이 불법 처리되고 Navfn도 "failed to create plan"** 이 된다. 사후 수정 불가 —
재매핑만이 해법이다. **마스킹은 Phase 3 매핑보다 반드시 먼저.**

---

## 3. 3단계 계획

전제: 각 Phase는 **앞 Phase가 통과한 뒤** 시작한다. 모든 터미널에서 환경변수를 통일한다
(§5 정정 1 참조 — `ROS_LOCALHOST_ONLY`는 **설정하지 않는다**).

공통 소스 방법:
```bash
source /opt/ros/humble/setup.bash
source /home/ssafy/S15P11C101/embedded/Lidar/install/setup.bash   # SLAM/Nav2 쓸 때
source /home/ssafy/S15P11C101/ros2_ws/install/setup.bash          # 모터/teleop 쓸 때
```

---

### Phase 1 — WASD 수동 주행 (SLAM·지도 없음)

**목표**: 키보드 → `/cmd_vel` → `stm_serial_bridge` → STM32 → 바퀴가 실제로 돈다.

**선행**: B1(dialout) 해결 · B2(AI 스택) 종료 · `ros2_ws` 빌드 완료.

```bash
# [터미널 1] STM Serial Bridge
cd /home/ssafy/S15P11C101/ros2_ws && source install/setup.bash
PORT=$(find /dev/serial/by-id -maxdepth 1 -type l \
  -name 'usb-STMicroelectronics_STM32_STLink_*-if02' -print -quit)
ros2 launch stm_serial_bridge stm_serial_bridge.launch.py \
  mode:=hardware speed_profile:=slow serial_port:="$PORT"

# [터미널 2] 연결·충돌 확인
ros2 run stm_serial_bridge check_stm_topics --timeout-sec 10   # /stm/connected=True, /stm/fault=NONE
ros2 topic info /cmd_vel -v                                    # Publisher 0 / Subscriber 1  ← teleop 실행 전 기대값

# [터미널 3] WASD 수동 주행 ← 사용자가 직접 (대화형 TTY 필요)
cd /home/ssafy/S15P11C101/ros2_ws && source install/setup.bash
ros2 run cart_teleop keyboard_teleop
#  W 전진 / S 후진 / A 좌회전 / D 우회전 / Space 정지 / q·Esc 종료 / +,- 속도단계
```

**합격 기준**
- `/stm/connected = True`, `/stm/fault = NONE`
- `/cmd_vel` 발행자 = **teleop 1개만**
- W 입력 시 `/cmd_vel linear.x > 0` → `/stm/wheel_target` 반응 → **좌우 바퀴 실제 회전**
- 키 떼면 워치독으로 자동 정지

**안전**
1. **1차는 바퀴를 공중에 띄우고**(카트 들어올림 또는 받침) 확인, 통과 후 바닥 주행.
2. `Space`는 zero Twist 정지 명령이며 **ESTOP이 아니다.** 비상시 **물리 전원 차단**.
3. `speed_profile:=slow`는 `max_wheel_rad_s: 2.0` — 제자리 회전(ω=0.6) 봉투는 온전히 수용하고
   직진만 약 43%로 제한한 값(r=0.065, L=0.38 실측 기준). 첫 통합 테스트에 적합.

**Claude가 할 일 / 사용자가 할 일**: `keyboard_teleop`은 키 입력을 받는 대화형 노드라
**Claude의 도구 셸로는 조작할 수 없다.** 사용자가 터미널에서 직접 누르고, Claude는
`/cmd_vel`·`/stm/*` 토픽과 브릿지 로그를 실시간 모니터링한다.

---

### Phase 2 — AI 카메라 추종 (지도 없이)

> **⏸ 2026-08-04 Stage 0에서 중단** (사용자가 라이다 위치 변경). 상세 실행 계획·재개 지점은
> `~/.claude/plans/readme-step-validated-breeze.md`, 실측 기록은 `tests/TEST_LOG.md` 18:20 항목.
>
> 🔴 **Stage 0에서 블로커 발견**: AI는 `camera_fov_deg=58°` → **±29° 창**에서만 거리를 조회하는데,
> 그 창의 라이다 유효율이 **6/70 = 8.6%**이고 **정면 −5°~+5°에 유효 빔이 0개**였다(구 위치 기준).
> 이 상태면 사람이 정면에 서도 `linear_vel=0.0`으로 고정돼 **전진 없이 회전만** 한다.
> 무효 빔이 구조물 차폐(`0.0`)인지 range 초과(`>10 m`)인지 **판별 미완** — 재개 시 이것부터.

**목표**: 사람을 카메라로 인식·추종해 카트가 따라온다.

```
카메라 → YOLO/ByteTrack/Re-ID → control_node → /cmd_vel → stm_serial_bridge → STM32
                                      ↑
                            /scan (AI가 구독 — 선속도의 필수 입력)
```

**선행**: Phase 1 통과(같은 `/cmd_vel` 경로를 그대로 재사용) · **teleop 종료** · SLAM/Nav2 미실행.

#### 🔴 조사로 확정된 정정 사항 (2026-08-04, 코드 근거 있음)

| # | 기존 서술 | 실제 |
|---|---|---|
| 1 | `/scan`은 "거리 추정용" 보조 입력 | **필수.** 거리 실패 시 `linear_vel=0.0`인데 **각속도는 계속 발행** → 라이다 없으면 **제자리 회전만** (`control_node.py:339-357`) |
| 2 | `choll-fe`로 띄우면 추종 시작 | 별칭이 `auto_select:=false` → **`/select_target` 수신 전까지 절대 안 움직인다** (`reid_node.py:343-346`). 등록 입구는 `/select_target`(std_msgs/Int32) **단 하나**, 서비스·액션 없음 |
| 3 | 속도는 AI가 관리 | AI 상한 `max_linear_vel=0.5 / max_angular_vel=1.0`이 **런치 dict에 하드코딩**. 런치 인자에 없고 파라미터 콜백도 없어 `ros2 param set`도 무효 → **브릿지 cap이 유일한 속도 방어선** |

**속도 봉투**: `wheel_speed_limiter.py:62-67`이 좌우 **비율을 보존한 채 비례 축소**하므로
`speed_profile:=slow`(cap 2.0)에서 실효 **직진 0.130 m/s · 회전 0.684 rad/s**
= Phase 1 실기 검증 봉투와 사실상 동일. **속도 안전은 브릿지 하나로 봉인된다.**

**예측 거동** (PWM = 10 × rad/s, PWM<20 데드존, linear kp=0.5):
거리 ≥1.26 m → 0.130 m/s 전진 / 1.00~1.26 m → 데드존(안 움직임) /
**<0.74 m → 0.130 m/s 후진**(사용자 결정: 코드가 아니라 절차로 막는다 — 1.2 m 이상 유지, 후방 2 m 확보).
순수 회전은 화면 중심 85% 이탈 전엔 데드존 → **매끄러운 추종이 아니라 계단식(bang-bang) 추종**이 정상.

**등록 3경로** (모두 `/select_target`으로 수렴 — FE가 안 되면 즉시 대체):
① FE 웹 클릭 ② `curl -X POST http://your-server.example.com/api/carts/1/follow/target -d '{"trackId":N}'`
③ `ros2 topic pub --once /select_target std_msgs/msg/Int32 "{data: N}"`
track id는 `ros2 topic echo /person_tracks --once`로 확인.
등록 성공 판정 2줄: `Memory Bank initialized (N features)` → `Switched to normal tracking mode`.
등록 시 **2~3 m 거리·전신·화면 중앙** — bbox가 화면 면적 50% 초과 또는 좌우 4 px 이내로 잘리면
크롭 게이트에 걸려 `Memory Bank initialization failed`.

**🔴 ROS 비상정지는 존재하지 않는다**
- `cart_teleop`은 외부 `/cmd_vel` 발행자를 감지해 **DISARMED**가 되어 non-zero를 못 낸다.
  게다가 DISARMED 상태에서도 20 Hz로 zero를 계속 발행해 AI 명령과 경합한다 → **동시 실행 금지.**
- `ros2 param set stm_serial_bridge max_wheel_rad_s ...`는 **성공을 반환하지만 효과가 없다**
  (`stm_serial_bridge_node.py:167-176` 값 캐시, 콜백 미구현). 안전 조치로 착각 금지.
- 유효한 정지는 **AI 종료 → 브릿지 watchdog 0.5 s** 하나뿐.
  **종료 순서: ① AI Ctrl+C → ② `/stm/pwm` 0 확인 → ③ 브릿지 Ctrl+C → ④ 라이다.**
  브릿지를 먼저 끄면 STM32가 최대 5초간 마지막 속도를 유지한다(약 0.65 m).

**무해하지만 알아둘 것**: `motor_node`가 함께 떠서 `/wheel_speed_cmd`를 10 Hz로 발행하지만
구독자 0이라 무해. 단 이 경로는 브릿지 cap을 우회하고 `wheel_separation_m: 0.30`(실측 0.38과 불일치)
→ **micro-ROS agent를 절대 함께 띄우지 말 것.**
`~/Choll/ros2_ws/install`에 stale `person_follow_robot`이 있으니 **소싱 금지**
(`ros2 pkg prefix person_follow_robot`이 `~/Choll/ai/install`인지 확인).

```bash
# [터미널 1] 라이다 드라이버만 (AI가 /scan을 구독한다 — SLAM은 불필요)
cd /home/ssafy/S15P11C101/embedded/Lidar && source install/setup.bash
ros2 launch choll_slam_bringup lidar.launch.py

# [터미널 2] STM Serial Bridge — Phase 1과 동일

# [터미널 3] AI 스택 (단축어)
choll-fe
#  = cd ~/Choll && ros2 launch person_follow_robot follow_robot_launch.py fe_bridge:=true
#    auto_select:=false be_video_ws_url:=... mqtt_host:=your-server.example.com ...
```

**합격 기준**
- `/cmd_vel` 발행자 = **`control_node` 1개만** (`ros2 topic info /cmd_vel -v`로 확인)
- 사람이 이동하면 `/cmd_vel`이 따라 변하고 카트가 추종
- 사람이 사라지면 정지

**주의**
- `choll-fe`는 `~/Choll`(develop 클론)의 AI 워크스페이스를 쓴다. 이 저장소(`~/S15P11C101`)와
  **별개 클론**이라 브랜치가 다르다 — 정상이며, AI 코드는 이번 작업 범위 밖(수정 금지).
- teleop과 **절대 동시 실행 금지**. AI와 teleop이 동시에 `/cmd_vel`을 쏘면 명령이 뒤섞인다.
- Nav2도 동시 금지(같은 이유).
- AI 스택은 `/scan`을 구독하므로 라이다 드라이버가 떠 있어야 거리 추정이 동작한다.

---

### Phase 3 — 매핑 + Nav 테스트

#### 3-1. 라이다 실측 반영 (매핑 전 필수 — B3)

1. **자기 구조물 각도 객관 산정**: Phase 1의 teleop으로 카트를 움직여 `/scan`을 bag 녹화한다
   (정지 10s → 직진 2 m → 정지 → 제자리 90° 회전 → 정지 → 직진 → 정지).
   여러 자세에서 `(방위, 거리)`가 모두 불변인 빈만 자기 구조물이다
   (`median<1.6 m ∧ std<0.03 ∧ 자세간 변동<0.05 ∧ 유효율>0.6`), 유효율<0.2는 완전 차폐.
   같은 bag의 직진 구간에서 `Δr_i = a·cosθ_i + b·sinθ_i` 최소제곱 → **전방각과 `--x` 부호를 동시 확정**,
   회전 구간 순환 상호상관 부호로 **`inverted` 정상 여부** 확정.
   → 산출값을 근거표와 함께 사용자 승인 후 반영.
   (분석 스크립트 초안: `embedded/Lidar/scripts/scan_analyze.py` — ⚠️ 아직 ruff 미통과(23건),
    커밋 전 정리하거나 커밋에서 제외할 것)
2. `lidar.launch.py` 정적 TF → `--x 0.30 --y 0.0 --z 0.25 --yaw 0.0`, TODO 주석을 실측 근거로 교체
3. `x4pro.yaml` → `ignore_array` 승인값 반영 (`angle_min/max`는 ±180 유지, `range_min` 0.12 유지,
   `invalid_range_is_inf: false` 유지 — rf2o는 `inf`를 유효값으로 오인해 NaN이 전파됨)
4. 반영 후 `ruff check` + `pytest` + 라이다 재기동해 마스킹 구간이 `0.0`으로 나오는지 확인
   (심볼릭 설치라 **리빌드는 불필요**, 노드 재기동만)

#### 3-2. 수동 매핑

```bash
# [터미널 1] LiDAR + rf2o + slam_toolbox  ← 이게 매핑 정본
cd /home/ssafy/S15P11C101/embedded/Lidar && source install/setup.bash
ros2 launch choll_slam_bringup bringup.launch.py     # 0s 라이다 → 3s rf2o → 6s slam_toolbox

# [터미널 2] STM Serial Bridge (Phase 1과 동일)
# [터미널 3] WASD teleop (사용자)
# [터미널 4] 검증
ros2 topic hz /scan            # 6~12 Hz (실측 11.34)
ros2 topic hz /odom_rf2o       # ~10 Hz
ros2 topic echo /map --once --qos-durability transient_local --no-arr
ros2 run tf2_ros tf2_echo map base_link
ros2 run tf2_ros tf2_echo base_link laser_frame
cd <스크래치패드> && ros2 run tf2_tools view_frames   # CWD에 산출물 생성됨
```

**TF 불변식**: `map→odom`(slam_toolbox) 1개 · `odom→base_link`(rf2o) 1개 ·
`base_link→laser_frame`(정적) 1개. `stm_serial_bridge`는 `/odom`·TF를 발행하지 않으므로
**충돌 없음**(확인함 — 휠 오도메트리는 아직 없고 `/stm/encoder`만 발행).

**주행 규칙** (반쪽 시야가 아님을 확인했으므로 표준 규칙 + 카트 특성)
- 사람 걸음보다 느리게(0.2 m/s 이하), 급가속·급회전 금지
- **제자리 회전(A/D)·후진(S)은 최소화** — rf2o는 라이다 스캔만으로 오도메트리를 추정하므로
  제자리 선회와 바퀴 슬립에 취약하다. 회전은 반경 1 m 이상의 호로.
  (Nav2 자율주행의 "후진 금지" 설계는 별개 사안 — 수동 주행에서 S를 쓰는 것 자체는 무방)
- 라이다 수평 유지, 외곽 한 바퀴 → 내부 통로, **시작점으로 복귀해 루프 클로저**
- 같은 구간은 같은 진행 방향으로 재방문 (전방 편향 센서는 반대 헤딩 재방문 시 정합할 데이터가 없음)
- 지도가 갑자기 찢어지거나 크게 튀면 즉시 정지 → `/odom_rf2o`·TF 확인

**지도 저장** (스택을 끄지 않은 상태에서)
```bash
mkdir -p ~/maps
ros2 run nav2_map_server map_saver_cli -f ~/maps/library_map
ros2 service call /slam_toolbox/serialize_map \
  slam_toolbox/srv/SerializePoseGraph "{filename: '$HOME/maps/library_map'}"
ls -l ~/maps/   # library_map.{yaml,pgm,posegraph,data} 4개
```
`map_saver_cli`만 쓰면 `.yaml`+`.pgm` 2개다. `serialize_map`까지 해야 `.posegraph`·`.data`가
생겨 **나중에 이어서 매핑**할 수 있다 → 4개 다 만들 것.

#### 3-3. Nav 테스트

```bash
# 먼저 모터리스 벤치 (컨트롤러가 포기하지 않는 완화 파라미터)
ros2 launch choll_nav2 nav.launch.py bench:=true     # bench는 true/True/TRUE/1 만 인식
ros2 launch choll_nav interface.launch.py approach_distance:=1.0

# 목표는 반드시 이 토픽으로 (RViz "2D Goal Pose"는 /goal_pose로 직행해 goal_forwarder를 우회한다)
ros2 topic pub --once /cart/target_pose geometry_msgs/msg/PoseStamped \
  "{header: {frame_id: base_link}, pose: {position: {x: 1.5}}}"

# 상태는 latched + on-change 발행 → QoS 플래그 없으면 아무것도 안 나온다
ros2 topic echo /cart/nav_status --once \
  --qos-durability transient_local --qos-reliability reliable --qos-depth 1

# 취소 — ⚠️ 이번 pull에서 Empty → String(data=requestId)로 변경됨
ros2 topic pub --once /cart/cancel std_msgs/msg/String "{data: 'test-req-1'}"
```
- `/cart/nav_status`: `IDLE → NAVIGATING → (SUCCEEDED|ABORTED|CANCELED)`, Nav2 미기동 시 `NAV2_UNAVAILABLE`
- `/cmd_vel` ~20 Hz, `0 ≤ linear.x ≤ 0.3`, `|angular.z| ≤ 0.6`, **음수 linear.x 0건**(후진 금지 확인)
- `requestId`는 **로그·추적용**이며 취소 대상을 필터링하지 않는다(빈 문자열 허용).
  로그에 `주행 취소 요청 (requestId=test-req-1)`이 찍히는지 확인.
- 좁은 공간에서 `ABORTED`(플래너 실패)는 footprint 0.70×0.64 기준 **정상** → 넓은 공간에서 재시도
- 첫 기동 시 lifecycle이 멈추면 **Nav2만 재시작** (Humble DDS 레이스)
- **AI 스택·teleop 종료 필수** (`/cmd_vel` 발행 주체 충돌)
- 벤치 통과 후 실주행은 **반드시 기본 `nav2_params.yaml`** (bench는 모터리스 검증 전용)

---

## 4. `/cmd_vel` 소유권 (Phase별로 하나만)

| Phase | `/cmd_vel` 발행자 | 동시에 꺼야 하는 것 |
|---|---|---|
| 1 수동 주행 | `cart_teleop` | AI 스택, Nav2 |
| 2 AI 추종 | AI `control_node` | teleop, Nav2 |
| 3-3 Nav | Nav2 `velocity_smoother` | teleop, AI 스택 |

확인은 항상 `ros2 topic info /cmd_vel -v` → **Publisher count 1**.

---

## 5. 모터 담당자 안내 대비 정정 사항

1. **`export ROS_LOCALHOST_ONLY=1`은 쓰지 않기를 권한다.** 노트북에서 원격 RViz로 지도를
   보려면 DDS가 네트워크로 나가야 한다(=0). 또 `choll-fe` 단축어는 이 변수를 설정하지 않으므로
   Phase 2에서 브릿지만 `=1`이면 설정이 엇갈린다. **모든 터미널에서 설정하지 않는 쪽(기본 0)으로 통일**하고,
   외부 간섭이 실제로 관찰될 때만 `ROS_DOMAIN_ID`로 분리한다.
   (Jetson `wlP1p1s0 192.168.0.254/24`, 노트북 동일 서브넷, `docker0`는 DOWN이라 간섭 없음)
2. **지도 저장은 4파일**(`map_saver_cli` + `serialize_map`) — 2파일만으로는 이어서 매핑 불가.
3. **매핑 정본 launch는 맞다**: `choll_slam_bringup/launch/bringup.launch.py`
   (내부 `lidar` 0s → `laser_odom` 3s → `slam` 6s). 단 이 파일은 **launch 인자를 선언하지 않아서**
   `params_file`/`slam_params_file`을 통해 넘길 수 없다 — 오버라이드가 필요하면 자식 launch를 개별 기동.
4. **`develop` 병합은 사람이 한다.** 프로젝트 규칙(`CLAUDE.md`)상 에이전트는 피처 브랜치 푸시와
   MR 생성까지만 하고 `develop`/`main` 직접 푸시·로컬 머지를 하지 않는다. 또한 현 시점에서
   LiDAR 스택은 **`/scan`까지만 실기 검증**된 상태이므로(매핑·Nav2 미검증), 병합 전에 최소한
   Phase 3-2 매핑 성공까지 확인하는 편이 안전하다.
5. **`tests/TEST_LOG.md` 충돌 시 양쪽 기록 보존** — 최신 항목이 맨 위이므로 두 항목을 시각순으로
   나란히 남기면 된다(둘 중 하나를 지우지 말 것).
6. `base_link→laser_frame`은 **아직 임시값 z=0.20**이다. 실측 반영은 Phase 3-1에서 한다.
   지금 매핑하면 지도 품질이 맞지 않으므로 순서를 지킬 것.

---

## 6. 미확정 / 팀 확인 필요 (임의로 확정하지 않음)

- **카트 footprint 실측** — `nav2_params.yaml`의 0.70×0.64는 가정값. 라이다가 x=+0.30에 있어
  실측 시 전후 비대칭 폴리곤이 될 가능성이 큼
- 라이다 `--y` 오프셋(중심선 가정 0.0), 최종 장착 확정 후 정적 TF·`ignore_array` 재측정
- 가속 한계(`acc_lim_*`, `max_accel`) — STM32 램프 기준 팀 확인
- 서가 통로 폭 기준 `inflation_radius`·`xy_goal_tolerance`
- 휠 오도메트리(`/odom`) 도입 시 rf2o와의 융합 방식(EKF vs rf2o `publish_tf: False`)
- `/cart/nav_status` ↔ FE `NAVIGATION_STATUS` 값 매핑 (`docs/ROS2_API.md` 미해결 항목)
