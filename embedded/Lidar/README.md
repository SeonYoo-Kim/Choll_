# Lidar — SLAM/NAV ROS2 워크스페이스 (X4 Pro + slam_toolbox + Nav2)

이 폴더가 **colcon 워크스페이스 루트**입니다. 노트북(Ubuntu 22.04 + Humble)에서
검증 완료된 상태이며, Jetson Orin Nano(Humble)에 그대로 이식해 사용합니다.

## 패키지 구성

| 패키지 | 역할 |
|---|---|
| `src/choll_slam_bringup` | X4Pro 드라이버 설정 + 정적TF + rf2o(임시 오도메트리) + slam_toolbox 런치 |
| `src/choll_nav` | `/robot_pose` 발행(명세 ROS2-08) + 목표 수신→Nav2 전달 + `/cart/nav_status` — API 대조표: [docs/ROS2_API.md](docs/ROS2_API.md) |
| `src/choll_nav2` | Nav2 파라미터(TB3 각색)·런치·RViz + BackUp(후진) 제거 커스텀 BT |
| `src/ydlidar_ros2_driver`, `src/rf2o_laser_odometry` | **upstream — 커밋 안 함**, setup 스크립트가 클론 |

## Jetson(오링카) 셋업 — 순서대로

```bash
# 0) 저장소 클론 + 브랜치
git clone https://lab.ssafy.com/s15-webmobile3-sub1/S15P11C101.git
cd S15P11C101 && git checkout em/feature/Lidar

# 1) 의존성 (apt + YDLidar-SDK + upstream 클론 + udev) — sudo 필요
bash embedded/Lidar/setup_jetson.sh
# 라이다 USB 재연결 후: ls -l /dev/ydlidar  (또는 /dev/ttyUSB0, crw-rw-rw- 확인)

# 2) 빌드
cd embedded/Lidar
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

## 검증 순서 (노트북에서 전부 통과한 순서 그대로)

```bash
# STEP A. 라이다 단독 — /scan 6~12Hz (실측 11.4Hz)
ros2 launch choll_slam_bringup lidar.launch.py
ros2 topic hz /scan

# STEP B. SLAM 스택 (라이다 0s → rf2o 3s → slam_toolbox 6s 시차 기동)
ros2 launch choll_slam_bringup bringup.launch.py
ros2 launch choll_nav view.launch.py          # RViz (모니터 필요)
ros2 run tf2_tools view_frames                # map→odom→base_link→laser_frame 확인

# STEP C. 매핑 (오링카 저속 주행) — 수평 고정 / 사람 걸음보다 느리게 /
#         급회전 금지 / 시작점 복귀(루프 클로저)
mkdir -p ~/maps
ros2 run nav2_map_server map_saver_cli -f ~/maps/library_map
ros2 service call /slam_toolbox/serialize_map \
  slam_toolbox/srv/SerializePoseGraph "{filename: '$HOME/maps/library_map'}"

# STEP D. Nav2 (모터리스 벤치 — progress checker 완화 파라미터)
ros2 launch choll_nav2 nav.launch.py bench:=true
ros2 launch choll_nav interface.launch.py     # 추종 모드: approach_distance:=1.0
# RViz "2D Goal Pose" 클릭 또는:
ros2 topic pub --once /cart/target_pose geometry_msgs/msg/PoseStamped \
  "{header: {frame_id: base_link}, pose: {position: {x: 1.0}}}"
ros2 topic echo /cart/nav_status              # NAVIGATING 확인
ros2 topic hz /cmd_vel                        # 발행 확인 (|v|≤0.3, |ω|≤0.6)
```

## 주의사항 (노트북 검증에서 실제로 겪은 것들)

- **넓은 공간에서 테스트할 것** — 폭 0.64m 카트 footprint 기준이라 좁은 공간에서는
  플래너가 "failed to create plan"으로 ABORTED가 남 (정상 동작).
- Jetson USB 전류 부족 시 라이다 어댑터보드 **USB_PWR**에 5V 보조 급전.
- Nav2 첫 기동 시 lifecycle이 간헐적으로 멈추면(활성화 로그 없음) Nav2만 재시작 —
  Humble의 일시적 DDS 서비스 레이스, 재시작으로 해결됨.
- `bench:=true`는 모터 없는 검증용(컨트롤러가 포기 안 함). **실주행은 반드시
  기본 nav2_params.yaml** 사용.
- 오링카 모터는 `/cmd_vel`과 연결돼 있지 않음 — 실주행이 아니라
  "goal→경로 생성→cmd_vel 발행" 검증까지가 이 단계의 목표.
- 지도 저장 후 위치추정 모드: `ros2 launch choll_nav2 localization.launch.py
  map:=$HOME/maps/library_map.yaml` (slam.launch.py와 **동시 실행 금지** —
  map→odom 발행자는 하나만).

## 실측 후 갱신할 TODO (카트 골조 장착 시)

- `choll_slam_bringup/launch/lidar.launch.py`: base_link→laser_frame 정적 TF
  (현재 z=0.20 플레이스홀더) + 카메라 장착 시 base_link→camera_frame 추가
- `choll_slam_bringup/config/x4pro.yaml`: `ignore_array` (프레임 기둥 각도 마스킹)
- `choll_nav2/config/nav2_params.yaml`: footprint 실측, 가속 한계(STM32 램프 기준 축
  팀 확인), 서가 통로 폭 기준 inflation/goal tolerance

토픽 계약·파라미터 상세는 각 패키지 README/CLAUDE.md 참고.
