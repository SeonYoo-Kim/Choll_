# Phase 3 퀵스타트 — 매핑 + Nav2 (1페이지 압축 절차)

> 판단 근거·상세는 [MOTOR_LIDAR_INTEGRATION.md](MOTOR_LIDAR_INTEGRATION.md) §3,
> 실측 원본은 [tests/TEST_LOG.md](../../tests/TEST_LOG.md) 2026-08-07 항목.
> 이 파일은 Claude 없이 터미널에 그대로 붙여넣는 용도.
> ⚡ 전원은 **벽 어댑터 권장** — 보조배터리 급단 사고 2회 (Jetson·RPi).

## 상태 (2026-08-07 실기)

| 단계 | 상태 |
|---|---|
| ③ 라이다 마스킹·드리프트 | ✅ 완료 (`scan_mask_node` 이관, 정지 드리프트 0) |
| ④ 매핑 + 지도 저장 | ✅ 완료 — 97 m², `~/maps/library_map.*` 4파일 |
| ⑤ Nav2 자율주행 | 🔴 미달 — 회전 발진으로 `SUCCEEDED` 못 봄 (§4 참조) |

## 0. 공통 (모든 터미널에서 먼저)

```bash
export ROS_DOMAIN_ID=42          # 🔴 필수 — 다른 사람 ROS와 격리. 노트북 RViz도 동일
source /opt/ros/humble/setup.bash
```

- 워크스페이스는 2개, **각각 따로 source**:
  `~/S15P11C101/embedded/Lidar`(SLAM/Nav2) · `~/S15P11C101/ros2_ws`(모터·teleop)
- yaml/launch 변경은 심볼릭 설치라 **재빌드 불필요**, 노드 재기동만
- 첫 주행 전 **NUCLEO RESET 한 번** (이전 세션 STALL 래치 제거)
- `/cmd_vel` 발행자는 항상 **정확히 1개**: `ros2 topic info /cmd_vel -v`

## 1. 라이다 단독 확인 (선택 — ③ 완료됨)

```bash
cd ~/S15P11C101/embedded/Lidar && source install/setup.bash
ros2 launch choll_slam_bringup lidar.launch.py
# 드라이버 → /scan_raw (rf2o 전용) / scan_mask_node → /scan (SLAM·Nav2·AI)
ros2 topic hz /scan /scan_raw     # 둘 다 ~11 Hz
```

기둥·합판 마스킹은 실측 확정됨 (기둥 2020 프로파일 좌 −81.6~−73.4°, 우 +70.1~+78.3°,
합판 절단면 좌 0.165 m·우 0.27 m, 총 차폐 약 30°=8%, 남는 시야 330°).
⚠️ `x4pro.yaml`의 `ignore_array`는 **빈 문자열 유지** — 드라이버에서 자르면 rf2o가
정지 상태에서 −0.4°/s 드리프트한다.

## 2. 매핑 (30~40분)

```bash
# [터미널 A] SLAM 스택 (라이다 0s → rf2o 3s → slam_toolbox 6s 자동 순차)
cd ~/S15P11C101/embedded/Lidar && source install/setup.bash
ros2 launch choll_slam_bringup bringup.launch.py

# [터미널 B] 모터 브릿지 — 🔴 매핑용 속도는 max_wheel_rad_s:=8.0
cd ~/S15P11C101/ros2_ws && source install/setup.bash
PORT=$(find /dev/serial/by-id -maxdepth 1 -type l \
  -name 'usb-STMicroelectronics_STM32_STLink_*-if02' -print -quit)
ros2 launch stm_serial_bridge stm_serial_bridge.launch.py \
  mode:=hardware speed_profile:=slow serial_port:="$PORT" \
  max_wheel_rad_s:=8.0

# [터미널 C] WASD 주행 (사용자 직접, W전진 S후진 A/D회전 Space정지 q종료)
cd ~/S15P11C101/ros2_ws && source install/setup.bash
ros2 run cart_teleop keyboard_teleop --ros-args \
  -p max_linear_mps:=0.52 -p max_angular_rps:=0.60

# [터미널 D] 감시
ros2 topic hz /scan            # 11.0~11.7 Hz 실측
ros2 topic hz /odom_rf2o       # 9.3~10.3 Hz 실측
ros2 run tf2_ros tf2_echo map base_link    # 정지 시 yaw 누적 없어야 정상
```

🔴 **속도는 두 곳을 같이 올려야 한다** (2026-08-07 실측): teleop 기본 상한이
0.13 m/s여서 브릿지 cap만 올려도 안 빨라진다. 그리고 두 노드 모두 파라미터를
`__init__`에서 한 번만 읽으므로 **`ros2 param set`은 성공을 반환해도 효과가 없다**
— 값을 바꾸려면 위처럼 기동 인자로 주거나 재기동할 것.
회전(`max_angular_rps`)은 0.60 유지 — 올리면 스캔당 회전각이 커져 지도가 찢어진다.
정지 거리: 0.52 m/s에서 **2.5초·78 cm**, 브릿지가 죽으면 **2.9 m** (펌웨어 5초 타임아웃).

**주행 규칙**: 천천히 / 제자리 회전·후진 최소화(회전은 반경 1 m 이상 호로) /
외곽 한 바퀴 → 내부 통로 → **시작점 복귀(루프 클로저)** / 같은 구간은 같은 진행
방향으로 재방문 / 지도가 찢어지면 즉시 정지.

## 3. 지도 저장 (5분 — SLAM을 끄지 않은 채로!)

```bash
mkdir -p ~/maps
ros2 run nav2_map_server map_saver_cli -f ~/maps/library_map
ros2 service call /slam_toolbox/serialize_map \
  slam_toolbox/srv/SerializePoseGraph "{filename: '$HOME/maps/library_map'}"
ls -l ~/maps/     # library_map.{yaml,pgm,posegraph,data} 4개여야 함
```

→ `library_map.yaml`의 **resolution·origin을 BE에 전달**
(SlamCoordinateConverter 입력 + `mqtt.position-unit=meters` 전환 조건).

**2026-08-07 저장본 실측값** (BE 전달 완료 대상): `resolution 0.05` /
`origin [-8.14, -4.75, 0]` / 격자 366×319셀 = 18.30×15.95 m /
좌표 범위 x −8.14~10.16, y −4.75~11.20 / trinary(occupied 0.65, free 0.25).
재매핑하면 이 값이 바뀌므로 **BE에 다시 전달해야 한다.**

## 4. Nav2 자율주행 (teleop 종료 후!)

```bash
# [터미널 3] teleop q 종료 → ros2 topic echo /stm/pwm --once 로 0 확인

# [터미널 4] — Nav2 (실주행은 기본 파라미터. bench:=true는 모터리스 검증 전용)
cd ~/S15P11C101/embedded/Lidar && source install/setup.bash
ros2 launch choll_nav2 nav.launch.py

# [터미널 5] — 위치 발행 + goal 인터페이스
cd ~/S15P11C101/embedded/Lidar && source install/setup.bash
ros2 launch choll_nav interface.launch.py

# 목표 지정 (⚠ RViz "2D Goal Pose" 금지 — goal_forwarder를 우회함)
ros2 topic pub --once /cart/target_pose geometry_msgs/msg/PoseStamped \
  "{header: {frame_id: map}, pose: {position: {x: 1.5, y: 0.5}}}"

# 상태 확인 (래치 QoS 플래그 필수 — 없으면 아무것도 안 나옴)
ros2 topic echo /cart/nav_status \
  --qos-durability transient_local --qos-reliability reliable --qos-depth 1

# 취소
ros2 topic pub --once /cart/cancel std_msgs/msg/String "{data: 'manual-1'}"
```

⚠️ Nav2용 브릿지는 **`max_wheel_rad_s:=6.0`** 으로 띄운다 (회전 1.2 rad/s = 바퀴
3.51, 조합 명령 최대 5.82 → 비례 축소 없이 통과).

**합격 기준**: `NAVIGATING → SUCCEEDED`, `/cmd_vel`이 `0 ≤ linear.x ≤ 0.15`·
`|angular.z| ≤ 1.2`·**음수 linear.x 0건**(후진 금지).
첫 기동에서 lifecycle이 멈추면 **Nav2만 재시작**(Humble DDS 레이스).

### 🔴 현재 미해결 — 회전 발진 (2026-08-07 3회 시도 전부 SUCCEEDED 미달)

원인은 **회전 액추에이터가 bang-bang**이라는 것. 모터 데드존이 PWM 20이라
바퀴 2.0 rad/s(=회전 0.68) 미만은 아예 안 돌고, 상한이 1.2이므로 쓸 수 있는
제어 대역이 **0.68~1.2 rad/s뿐**이다. 여기에 rf2o의 지연된 yaw 피드백이 겹쳐
DWB 비례 제어가 리미트 사이클(제자리 좌우 발진)에 빠진다.
파라미터는 이미 재배분됨 (`max_vel_x` 0.3→**0.15**, `max_vel_theta` 0.6→**1.2**,
`acc_lim_theta` 0.8→1.6, `behavior_server.min_rotational_vel` 0.15→**0.70**).

**다음 시도 순서** (위에서부터):

1. **데드존 보상** — 브릿지/펌웨어에서 `|목표|>0`일 때 최소 PWM(≈20)을 깔면
   제어 대역이 0부터 열려 발진이 사라진다. **가장 효과 큼**
2. **`Oscillation` 크리틱 실효화** (yaml만, 재기동만 필요) —
   `oscillation_reset_dist` 0.05→**0.3**, `oscillation_reset_angle` 0.2→**0.5**.
   현재는 위치 지터로 매 주기 잠금이 풀려 무력화 상태
3. **`PathAlign.scale`(32)·`GoalAlign.scale`(24) 하향** — 회전 지향 압력 완화
4. **휠 오도메트리** — 근본 해결(STATUS에 `enc L/R` 이미 올라옴). 단 현재 작업 불가
5. **재매핑** — 위치추정 스냅(정지 상태에서 yaw 33° 점프)이 지도 내부 정합
   문제일 수 있어 1·2 해결 후 다시 뜨는 편이 낫다

`ABORTED`는 좁은 공간에서 정상 — 더 넓은 곳에 goal.

## 5. (여유 시) 웹 연동 E2E

```bash
# [터미널 6]
cd ~/S15P11C101/embedded/Lidar && source install/setup.bash
ros2 launch choll_mqtt_bridge bridge.launch.py
# → 웹 지도에 카트 위치 실시간 표시, 웹 "이동" 명령으로 실주행
```

## §RViz 보는 법 (둘 중 하나)

**A. 젯슨 로컬 모니터 — 네트워크 무관, 확실함 (권장)**

```bash
# SSH 세션에서도 젯슨 화면(:0)에 뜬다
DISPLAY=:0 XAUTHORITY=/run/user/1000/gdm/Xauthority \
  ros2 launch choll_nav view.launch.py
# (젯슨에 준비된 래퍼: ros2_ws/log/phase3_20260807/launch_rviz.sh)
```

**B. 노트북 원격 RViz**

```bash
unset RMW_IMPLEMENTATION          # cyclonedds export가 남아 있으면 rcl이 죽는다
export ROS_DOMAIN_ID=42           # 🔴 젯슨과 동일해야 함
source /opt/ros/humble/setup.bash
cd ~/choll/embeded && source install/setup.bash
ros2 launch choll_nav view.launch.py
```

안 보일 때 순서대로: ① 젯슨 스택이 실제로 떠 있는지(`ros2 node list`)
② 양쪽 `ROS_DOMAIN_ID`가 같은지 ③ 노트북 `sudo ufw status` — active면
`sudo ufw allow from 192.168.0.0/24` ④ 그래도 안 되면 공유기 멀티캐스트
차단이므로 유니캐스트 XML 사용 (`~/choll/fastdds_unicast.xml` 또는 젯슨의
`ros2_ws/log/phase3_20260807/fastdds_peer_laptop.xml`):
`export FASTRTPS_DEFAULT_PROFILES_FILE=<경로>` ⑤ 폰 핫스팟으로 양쪽 이동.
RViz Fixed Frame은 `map`(SLAM 필요) — 라이다만 볼 때는 `laser_frame`으로.

## 안전 (실측 확정 사실)

- **ROS 비상정지는 없다** → 비상시 **모터 전원 차단**이 유일 수단
- 종료 순서: teleop/Nav2 끄기 → `/stm/pwm` 0 확인 → 브릿지 → 라이다
  (브릿지를 먼저 끄면 STM32가 **최대 5초** 마지막 속도 유지 — 0.13 m/s면 0.65 m,
  **0.52 m/s면 2.9 m**)
- `/stm/pwm`은 `Int16MultiArray` (Int32 아님 — echo 시 타입 주의)
- STALL 래치 해제는 NUCLEO **RESET(NRST) 또는 전원 재투입**뿐
- 첫 주행 전 NUCLEO RESET 한 번 (이전 세션 래치 제거)
