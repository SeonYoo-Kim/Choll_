# 쫄래쫄래 — AI 파트

> 프로젝트 전체 소개는 [루트 README](../README.md), 노드·토픽 상세는
> [노드 CLAUDE.md](src/person_follow_robot/person_follow_robot/CLAUDE.md)를 참조하세요.

## Overview
사서를 따라다니며 구역별 도서 정리를 돕는 자율주행 북카트의 **인식·추종 파트**

Face Recognition이 아닌 Person Re-Identification(Re-ID)로 동일 인물을 추적하고,
카메라 방위각 + LiDAR 거리 + SLAM 포즈로 **사서의 지도 좌표(/target_position)를 발행**합니다
(경로 계획·모터 구동은 EM의 SLAM Nav 담당).

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

**타겟 선택 — 기본은 자동입니다**
카메라 앞에 서면 가장 가까운(화면에서 가장 큰) 사람이 0.5초 뒤 자동 선택되고,
2초 등록 후 추종이 시작됩니다. 사람을 잠깐 놓쳐도 Re-ID로 다시 찾습니다.

수동으로 고르려면 `auto_select:=false`로 실행하고:

```bash
ros2 topic echo /person_tracks              # 잡힌 사람들의 id 확인 (Ctrl+C로 종료)
ros2 topic pub --once /select_target std_msgs/msg/Int32 "{data: 1}"   # 위에서 고른 id로 교체
```

FE 화면에서 클릭으로 고르는 모드는 `fe_bridge:=true auto_select:=false`
(상세: [패키지 CLAUDE.md](src/person_follow_robot/CLAUDE.md)의 실행 옵션).

## Key Features

- Person Detection (YOLOv10s TensorRT)
- Multi Object Tracking (ByteTrack)
- Person Re-Identification (OSNet) + Online Memory Bank
  (시공간 타당성 게이트·연속 확인으로 오인 방지)
- 최근접 인물 자동 선택 / FE 화면 클릭 선택 (fe_bridge)
- LiDAR 거리 측정 (bbox 폭 조회창 + 드롭아웃 유예)
- 사서 지도 좌표 발행 (/target_position — SLAM Nav 연동)
- ROS2 Integration

## Hardware

- Jetson Orin Nano 8GB
- RGB Camera
- 2D LiDAR
- Differential Drive Robot

## Repository Structure (AI 파트)

    ai/
    ├── README.md                  # (이 문서) AI 실행 가이드
    ├── test/                      # 프레임워크 독립 로직 테스트 (pytest, ROS 불필요)
    │   ├── CLAUDE.md              # 테스트 전략·규칙
    │   └── TEST_LOG.md            # 테스트 실행 기록 (원본 출력)
    └── src/person_follow_robot/   # ROS2 패키지 (빌드·실행의 정본)
        ├── CLAUDE.md
        ├── launch/follow_robot_launch.py
        ├── person_follow_robot/   # 노드 소스 — 목록·책임·토픽 계약은 CLAUDE.md 참조
        │   └── CLAUDE.md
        └── test/                  # ament lint (colcon test)

전체 저장소 구조는 [루트 README](../README.md), 문서 색인은 [루트 CLAUDE.md](../CLAUDE.md) 참조.



## Documentation

| Document | Description |
|----------|-------------|
| [../docs/AI_SPECIFICATIONS.md](../docs/AI_SPECIFICATIONS.md) | AI 명세 + 기술 선택 이유 |
| [../docs/SYSTEM_ARCHITECTURE.md](../docs/SYSTEM_ARCHITECTURE.md) | 시스템 구조 + ROS2 토픽 + 데이터 흐름 |
| [src/person_follow_robot/person_follow_robot/CLAUDE.md](src/person_follow_robot/person_follow_robot/CLAUDE.md) | 노드별 책임 · 토픽 계약 · Known Gaps |
| [test/CLAUDE.md](test/CLAUDE.md) | 테스트 전략 (2단계) · 로그 규칙 |

프로젝트 공통 문서(헌장·컨벤션·유지보수)는 [루트 README](../README.md)와 [루트 CLAUDE.md](../CLAUDE.md) 참조.


## Current Progress

Step 1 — 인식
- [x] YOLOv10 TensorRT
- [x] ByteTrack

Step 2 — Re-ID
- [x] OSNet + Memory Bank
- [x] 재인식 강화 (크롭 품질 게이트 · 시공간 타당성 · 연속 확인)

Step 3 — 센서 융합·선택
- [x] LiDAR 거리 측정 (좌우 반전 보정 · bbox 폭 조회창)
- [x] 최근접 인물 자동 선택 / FE 클릭 선택 브릿지

Step 4 — SLAM 연동 (진행 중)
- [x] 사서 지도 좌표 발행 (/target_position, 가짜 포즈 검증 완료)
- [ ] EM 실포즈(/robot_pose) 연동 재검증
- [ ] 상실 시 탐색 거동 배선 (search_behavior, 조립 후)