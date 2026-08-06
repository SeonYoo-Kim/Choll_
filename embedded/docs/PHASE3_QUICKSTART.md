# Phase 3 퀵스타트 — 매핑 + Nav2 (1페이지 압축 절차)

> 판단 근거·상세는 [MOTOR_LIDAR_INTEGRATION.md](MOTOR_LIDAR_INTEGRATION.md) §3.
> 이 파일은 Claude 없이 터미널에 그대로 붙여넣는 용도.
> ⚡ 전원은 **벽 어댑터 권장** — 보조배터리 급단 사고 2회 (Jetson·RPi).

## 0. 시작 전 (5분)

- [ ] `git pull` 완료 (라이다 실측 TF x=0.30 + 기둥 마스킹 잠정값 포함)
- [ ] **z 실측 (1분)**: 바닥→라이다 광학창 중심 높이를 줄자로 재서
      `lidar.launch.py`의 `--z` 갱신 (08-06 조립로 높이 변동 —
      2D 지도 품질과 무관하므로 급하면 건너뛰어도 됨)
- [ ] AI 스택·teleop 미실행: `ros2 topic info /cmd_vel -v` → **Publisher 0**
- [ ] yaml/launch 변경은 심볼릭 설치라 **재빌드 불필요**, 노드 재기동만

## 1. 마스킹 검증 (10분) — 매핑 전 필수

```bash
# [터미널 1]
cd ~/S15P11C101/embedded/Lidar && source install/setup.bash
ros2 launch choll_slam_bringup lidar.launch.py
```

노트북 RViz(아래 §RViz)에서 두 가지 확인:

**A. ±75° 기둥 포인트(0.13~0.15 m)가 사라졌는지**

| 관찰 | 조치 |
|---|---|
| 기둥 포인트 사라짐 | ✅ 통과 → B |
| 반대편이 사라짐 | `x4pro.yaml`의 `ignore_array` 부호 반전 (`"-79,-72,70,78"`) 후 재기동 |
| 그대로 남음 | 여유각 ±5°로 확대 (`"-80,-68,70,81"`) 후 재기동 |

**B. 조립로 생긴 새 자기차폐가 없는지** (08-06 선반 카트 조립 — 선반·손잡이)
카트를 제자리에 두고 **0.6 m 이내에 고정 포인트**가 보이면 전부 자기 구조물이다.
각 구간의 각도를 확인해 `ignore_array`에 쌍으로 추가 후 재기동
(예: 뒤 손잡이가 걸리면 `"-78,-70,72,79,170,180,-180,-170"` 식으로 이어붙임).

## 2. 매핑 (30~40분)

```bash
# [터미널 1] — 1번 것을 끄고 (라이다+rf2o+SLAM 통합)
cd ~/S15P11C101/embedded/Lidar && source install/setup.bash
ros2 launch choll_slam_bringup bringup.launch.py

# [터미널 2] — 모터 브릿지
cd ~/S15P11C101/ros2_ws && source install/setup.bash
PORT=$(find /dev/serial/by-id -maxdepth 1 -type l \
  -name 'usb-STMicroelectronics_STM32_STLink_*-if02' -print -quit)
ros2 launch stm_serial_bridge stm_serial_bridge.launch.py \
  mode:=hardware speed_profile:=slow serial_port:="$PORT"

# [터미널 3] — WASD 주행 (사용자 직접, W전진 A/D회전 Space정지 q종료)
cd ~/S15P11C101/ros2_ws && source install/setup.bash
ros2 run cart_teleop keyboard_teleop
```

**주행 규칙**: 0.2 m/s 이하(속도 단계 5 유지) / 제자리 회전·후진 최소화 —
회전은 반경 1 m 이상 호로 / 외곽 한 바퀴 → 내부 통로 → **시작점 복귀(루프
클로저)** / 같은 구간은 같은 진행 방향으로 재방문 / 지도가 찢어지면 즉시 정지.

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

**합격**: `NAVIGATING → SUCCEEDED`, `/cmd_vel`이 `0 ≤ linear.x ≤ 0.3`·
`|angular.z| ≤ 0.6`·**음수 linear.x 0건**(후진 금지).
브릿지는 `speed_profile:=slow` 유지 → 실효 직진 최대 0.13 m/s (안전 우선).
첫 기동에서 lifecycle이 멈추면 **Nav2만 재시작**(Humble DDS 레이스).
`ABORTED`는 좁은 공간에서 정상 — 더 넓은 곳에 goal.

## 5. (여유 시) 웹 연동 E2E

```bash
# [터미널 6]
cd ~/S15P11C101/embedded/Lidar && source install/setup.bash
ros2 launch choll_mqtt_bridge bridge.launch.py
# → 웹 지도에 카트 위치 실시간 표시, 웹 "이동" 명령으로 실주행
```

## §RViz — 노트북에서 원격으로 보기 (권장, 실측 검증된 구성)

조건: 노트북·젯슨이 **같은 Wi-Fi**(192.168.0.x), 양쪽 모두
`ROS_DOMAIN_ID`·`ROS_LOCALHOST_ONLY` **설정하지 않음**(기본값).

```bash
# [노트북]
source /opt/ros/humble/setup.bash
cd ~/choll/embeded && source install/setup.bash
ros2 launch choll_nav view.launch.py     # Map·LaserScan·TF·경로 QoS 설정 포함
```

안 보일 때: ① 같은 공유기인지 ② 양쪽 `env | grep ROS`가 비어 있는지
③ `ros2 topic list`에 /scan이 보이는지 순서로 확인.

## 안전 (실측 확정 사실)

- **ROS 비상정지는 없다** → 비상시 **모터 전원 차단**이 유일 수단
- 종료 순서: teleop/Nav2 끄기 → `/stm/pwm` 0 확인 → 브릿지 → 라이다
  (브릿지를 먼저 끄면 STM32가 **최대 5초** 마지막 속도 유지 ≈ 0.65 m)
- STALL 래치 해제는 NUCLEO **RESET(NRST) 또는 전원 재투입**뿐
- 첫 주행 전 NUCLEO RESET 한 번 (이전 세션 래치 제거)
