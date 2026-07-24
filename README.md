# 쫄래쫄래

## Overview
사서를 따라다니며 구역별 도서 정리를 돕는 자율주행 북카트

Face Recognition가 아닌 Person Re-Identification(Re-ID)로 동일 인물을 추적

ROS2 기반 **Jetson Orin Nano 8GB**에서 구동

## Quick Start (처음 실행하는 사람용)

> 코드와 모델은 모두 **Jetson Orin Nano 위**에서 돕니다. 노트북/PC에서 직접 실행하는 게 아니라,
> **SSH로 Jetson에 접속한 뒤** 그 안에서 아래 명령을 실행합니다.
> 저장소는 Jetson의 `~/Choll` 에 있다고 가정합니다.

### 0. Jetson에 SSH 접속

```bash
ssh <사용자名>@<Jetson_IP>       # 예: ssh jetson@192.168.0.42
```

### 1. (최초 1회 또는 코드 변경 후) 빌드

빌드는 **반드시 `~/Choll/ai/` 에서** 합니다.

```bash
cd ~/Choll/ai
colcon build --symlink-install
source install/setup.bash
```

> 코드를 바꿀 때마다 이 위치에서 다시 빌드하세요. (`--symlink-install` 이라 파이썬 소스만 고친 경우엔
> 재빌드 없이 반영되지만, launch 파일·노드 추가·`setup.py` 변경 시엔 다시 빌드해야 합니다.)

### 2. 실행 — 터미널 3개 (각 터미널은 Jetson에 SSH로 각각 접속)

**모든 새 터미널에서 먼저 ROS 환경을 source** 해야 `ros2` 명령이 동작합니다:

```bash
source /opt/ros/humble/setup.bash
source ~/Choll/ai/install/setup.bash
```

**터미널 1 — LiDAR 드라이버** (위치 무관)

```bash
ros2 launch ydlidar_ros2_driver ydlidar_launch.py
```

**터미널 2 — 메인 파이프라인**
`~/Choll` 에서 실행합니다. (detector가 모델을 `models/yolov10s.engine` **상대 경로**로 찾기 때문에
반드시 이 디렉토리에서 실행해야 엔진 파일을 찾습니다.)

```bash
cd ~/Choll
ros2 launch person_follow_robot follow_robot_launch.py
# 결과 영상을 저장하려면: ros2 launch person_follow_robot follow_robot_launch.py save_debug_video:=true
```

**터미널 3 — 따라갈 사람(사서) 선택** (위치 무관)
먼저 화면에 잡힌 사람들의 track id를 확인하고, 따라가게 할 id를 골라 발행합니다.

```bash
ros2 topic echo /person_tracks              # 잡힌 사람들의 id 확인 (Ctrl+C로 종료)
ros2 topic pub --once /select_target std_msgs/msg/Int32 "{data: 1}"   # 위에서 고른 id로 교체
```

선택 후 로봇이 해당 사람을 1 m 거리로 추종합니다. 사람을 잠깐 놓쳐도 Re-ID로 다시 찾습니다.

> docker 지원은 추가 예정입니다.

## Key Features

- Person Detection (YOLOv10s TensorRT)
- Multi Object Tracking (ByteTrack)
- Person Re-Identification (OSNet)
- Online Memory Bank
- LiDAR-based Distance Control
- PID Motion Control
- ROS2 Integration

## Hardware

- Jetson Orin Nano 8GB
- RGB Camera
- 2D LiDAR
- Differential Drive Robot

## Repository Structure

    Choll/
    ├── CLAUDE.md                  # AI 에이전트 진입점 (저장소 지도 + 규칙)
    ├── README.md
    ├── pyproject.toml             # ruff 린트/포맷 설정
    ├── .pre-commit-config.yaml    # 커밋 훅
    ├── install_ros2_humble.sh
    ├── docs/                      # 프로젝트 문서 (단일 진실 공급원)
    │   ├── CLAUDE.md
    │   ├── PROJECT_CHARTER.md
    │   ├── SYSTEM_ARCHITECTURE.md
    │   ├── AI_SPECIFICATIONS.md
    │   ├── DEVELOPMENT_GUIDE.md
    │   ├── JETSON_TO_STM.md
    │   └── MAINTENANCE.md         # 가비지 컬렉션/정리 정책
    ├── scripts/
    │   ├── gc.sh                  # 빌드 산출물 정리 (Linux/Jetson)
    │   └── gc.ps1                 # 빌드 산출물 정리 (Windows)
    ├── tests/                     # 프레임워크 독립 로직 테스트 (pytest)
    │   ├── CLAUDE.md
    │   ├── conftest.py
    │   ├── test_pid.py
    │   └── test_control_logic.py
    └── ai/
        └── src/
            └── person_follow_robot/
                ├── CLAUDE.md
                ├── launch/follow_robot_launch.py
                ├── person_follow_robot/
                │   ├── CLAUDE.md
                │   ├── camera_node.py
                │   ├── detector_node.py
                │   ├── tracker_node.py
                │   ├── reid_node.py
                │   ├── control_node.py
                │   ├── motor_node.py
                │   └── debug_visualization_node.py
                ├── test/          # ament lint (colcon test)
                ├── resource/person_follow_robot
                ├── package.xml
                ├── setup.cfg
                └── setup.py



## Documentation

| Document | Description |
|----------|-------------|
| [CLAUDE.md](CLAUDE.md) | AI 에이전트/기여자 진입점 — 저장소 지도, 규칙, 명령 |
| [docs/PROJECT_CHARTER.md](docs/PROJECT_CHARTER.md) | 프로젝트 목표, 제약 |
| [docs/SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md) | 시스템 구조 + ROS2 구조 + 데이터 흐름 |
| [docs/AI_SPECIFICATIONS.md](docs/AI_SPECIFICATIONS.md) | AI 명세 + 기술 선택 이유 |
| [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md) | 개발 환경 설정, Coding Rules, 아키텍처 원칙 및 TODO |
| [docs/JETSON_TO_STM.md](docs/JETSON_TO_STM.md) | STM 통신 관련 |
| [docs/MAINTENANCE.md](docs/MAINTENANCE.md) | 가비지 컬렉션 / 저장소 정리 정책 |
| [docs/GIT_CONVENTION.md](docs/GIT_CONVENTION.md) | 브랜치 전략, 커밋 메시지, MR/이슈 템플릿 |


## Current Progress

Step 1
- [x] YOLOv10 TensorRT
- [x] ByteTrack

Step 2
- [x] OSNet
- [x] Memory Bank

Step 3
- [ ] LiDAR
- [ ] PID
- [ ] Optimization