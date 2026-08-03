# CLAUDE.md — person_follow_robot (ROS2 package)

이 디렉토리는 하나의 **ament_python ROS2 패키지**입니다. 빌드·실행·테스트의 정본(定本)입니다.
노드 각각의 책임과 토픽 계약은 [person_follow_robot/CLAUDE.md](person_follow_robot/CLAUDE.md)를 참조하세요.

## 패키지 레이아웃

```
person_follow_robot/
├── launch/follow_robot_launch.py     # 전체 파이프라인 실행 (파라미터 정본)
├── person_follow_robot/              # 노드 소스 (Python 모듈)
├── test/                             # colcon 테스트 (ament lint 등)
├── resource/person_follow_robot      # ament 리소스 마커
├── package.xml                       # 의존성 선언
├── setup.py                          # entry_points = 노드 실행 파일 등록
└── setup.cfg
```

## 빌드

빌드는 **colcon 워크스페이스 루트(`ai/`)에서** 합니다 — 이 패키지 디렉토리가 아님에 주의.
Jetson 실기에서는 **`~/Choll/ai/`** 가 정확한 위치입니다. **코드를 바꿀 때마다 이 위치에서 재빌드**하세요.

```bash
cd ~/Choll/ai     # 실기 경로 (저장소 루트/ai)
colcon build --symlink-install
source install/setup.bash
```

`--symlink-install`을 쓰면 Python 소스 수정 후 재빌드 없이 반영됩니다(launch/entry_points/setup.py 변경 시엔 재빌드 필요).

## 실행

Jetson에 SSH로 접속한 뒤 **터미널 3개**로 실행합니다. 각 새 터미널에서 먼저 환경을 source 해야 `ros2`가 동작합니다:

```bash
source /opt/ros/humble/setup.bash
source ~/Choll/ai/install/setup.bash
```

```bash
# 터미널 1) LiDAR 드라이버 (위치 무관)
ros2 launch ydlidar_ros2_driver ydlidar_launch.py

# 터미널 2) 파이프라인 — 반드시 저장소 루트에서 실행 (모델을 models/yolov10s.engine 상대경로로 찾음)
cd ~/Choll
ros2 launch person_follow_robot follow_robot_launch.py
#   video_path:=/path/to.mp4      # USB 카메라 대신 영상 입력
#   save_debug_video:=true        # /debug/image를 result.mp4로 저장
#   threshold:=0.80               # Re-ID 유사도 임계값 실험 (기본 0.70)
#   fe_bridge:=true auto_select:=false \
#     be_video_ws_url:=ws://<BE호스트>:8080/ws/carts/1/video/publish mqtt_host:=<브로커IP>
#                                 # FE 화면에서 타겟을 직접 고르는 모드 (자동 선택 끔)

# 터미널 3) 타겟 선택 — 기본은 자동 (카메라 앞에 서면 최대 bbox가 0.5초 뒤 자동 선택됨)
# 수동으로 고르고 싶을 때만 (launch에 auto_select_enabled:=false 주고):
ros2 topic echo /person_tracks                                    # track id 확인
ros2 topic pub --once /select_target std_msgs/msg/Int32 "{data: 1}"  # 확인한 id로 선택
```

> 초심자용 단계별 안내(SSH 접속 포함)는 [AI README Quick Start](../../README.md#quick-start-처음-실행하는-사람용)를 참조.

## 테스트

```bash
# colcon (ament lint + 패키지 테스트)
cd ai && colcon test --packages-select person_follow_robot
colcon test-result --verbose

# 프레임워크 독립 로직 테스트는 ai/test/ 참조 (ROS 설치 불필요, 저장소 루트에서 실행)
pytest ai/test/
```

> `setup.py`의 `find_packages(exclude=["test"])`가 `test/`를 패키지에서 제외합니다 — 테스트는 이 디렉토리 안에 두세요.

## 노드 ↔ 실행 파일 매핑 (setup.py entry_points)

| executable | 소스 | 역할 |
|------------|------|------|
| `camera_node` | camera_node.py | RGB 프레임 발행 |
| `detector_node` | detector_node.py | YOLOv10s TensorRT 사람 검출 |
| `tracker_node` | tracker_node.py | ByteTrack ID 부여 |
| `reid_node` | reid_node.py | OSNet Re-ID + Memory Bank + 타겟 선택/재탐색 |
| `control_node` | control_node.py | PID (거리/각도) → cmd_vel |
| `motor_node` | motor_node.py | cmd_vel → 좌우 바퀴 RPM(/wheel_speed_cmd) (레거시, EM 재활용 예정) |
| `target_position_node` | target_position_node.py | 카트 포즈(SLAM)+방위각+거리 → 사서 지도 좌표 /target_position |
| `fe_bridge_node` | fe_bridge_node.py | FE 타겟 선택 연동 (영상·트랙 하행, SELECT_TARGET 상행. fe_bridge:=true일 때만) |
| `debug_visualization_node` | debug_visualization_node.py | 오버레이 영상 발행/저장 |

## 규칙

- 노드를 추가하면 **setup.py `entry_points` + launch 파일 + package.xml 의존성 + 노드 CLAUDE.md**를 함께 갱신한다.
- 새 의존 메시지 타입을 쓰면 `package.xml`의 `<exec_depend>`에 추가한다.
- 파라미터 기본값의 정본은 **launch 파일**이다. 노드의 `declare_parameter` 기본값과 어긋나지 않게 한다.
