# choll_slam_bringup — 쫄래쫄래 X4Pro SLAM 브링업

X4Pro 라이다 + rf2o 레이저 오도메트리(임시) + slam_toolbox 매핑 스택.
Jetson Orin Nano / Ubuntu 22.04 / ROS2 Humble 기준.

## TF 트리 (오늘 구성)

```
map ──(slam_toolbox)──> odom ──(rf2o, 임시)──> base_link ──(정적TF)──> laser_frame
```

STM32 엔코더 오도메트리가 준비되면 rf2o 자리를 휠 odom으로 교체한다.
(`launch/laser_odom.launch.py` 상단 주석 참고)

---

## 0. 워크스페이스 전제

아래는 `/home/ssafy/choll/embeded` 가 **colcon 워크스페이스 루트**(안에 `src/`가 있는 구조)라고
가정한 명령이다. 만약 이 경로 자체가 `src` 라면 경로만 한 단계 조정할 것.

```
/home/ssafy/choll/embeded/
└── src/
    ├── choll_slam_bringup/        <- 이 패키지
    ├── ydlidar_ros2_driver/       <- 클론 필요 (이미 있으면 생략)
    └── rf2o_laser_odometry/       <- 클론 필요
```

## 1. 의존성 설치

```bash
# apt 패키지
sudo apt update
sudo apt install -y ros-humble-slam-toolbox ros-humble-nav2-map-server \
                    cmake build-essential git

# YDLidar-SDK (드라이버가 의존하는 C++ SDK, 시스템에 설치)
cd ~ && git clone https://github.com/YDLIDAR/YDLidar-SDK.git
cd YDLidar-SDK && mkdir -p build && cd build
cmake .. && make -j$(nproc) && sudo make install
```

```bash
# 소스 패키지 클론 (이미 있는 것은 생략)
cd /home/ssafy/choll/embeded/src
git clone -b humble https://github.com/YDLIDAR/ydlidar_ros2_driver.git
git clone -b ros2   https://github.com/MAPIRlab/rf2o_laser_odometry.git
# choll_slam_bringup 폴더(이 패키지)도 여기에 복사
```

## 2. 시리얼 포트 확인 + 권한

```bash
# 라이다 USB 어댑터(CP2102) 연결 후
ls -l /dev/ttyUSB*        # 보통 /dev/ttyUSB0. 여러 개면 뽑았다 꽂아서 식별

# 권한 (둘 중 하나)
sudo usermod -aG dialout $USER   # 후 재로그인
# 또는 드라이버 repo의 udev 스크립트로 /dev/ydlidar 고정 별칭 생성:
cd /home/ssafy/choll/embeded
chmod 0777 src/ydlidar_ros2_driver/startup/*
sudo sh src/ydlidar_ros2_driver/startup/initenv.sh
# (적용 후 라이다 재연결. 별칭을 쓰면 config/x4pro.yaml 의 port 를 /dev/ydlidar 로 변경)
```

## 3. 빌드

```bash
cd /home/ssafy/choll/embeded
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

## 4. 단계별 실행 (처음엔 반드시 하나씩 검증)

### 4-1. 라이다만

```bash
ros2 launch choll_slam_bringup lidar.launch.py
# 다른 터미널에서
ros2 topic hz /scan          # 6~12 Hz 나오면 정상 (기본 ~7Hz 부근)
ros2 topic echo /scan --once | head -n 20
```

### 4-2. 레이저 오도메트리

```bash
ros2 launch choll_slam_bringup laser_odom.launch.py
ros2 topic echo /odom_rf2o   # 라이다를 천천히 움직이면 x,y,yaw 변해야 함
ros2 run tf2_tools view_frames   # odom->base_link->laser_frame 연결 확인 (frames.pdf 생성)
```

### 4-3. SLAM

```bash
ros2 launch choll_slam_bringup slam.launch.py
```

RViz(모니터 연결 또는 같은 네트워크 PC에서 `ROS_DOMAIN_ID` 맞춰 실행):

```bash
rviz2
# Fixed Frame: map
# Add: Map(/map), LaserScan(/scan), TF
```

### 4-4. 검증 후엔 원커맨드

```bash
ros2 launch choll_slam_bringup bringup.launch.py
```

## 5. 매핑 요령과 지도 저장

- 라이다를 카트(또는 임시 거치대)에 **수평** 고정하고, 사람 걸음보다 느리게 이동.
- 회전은 천천히(제자리 급회전은 스캔매칭이 미끄러짐), 복도 끝까지 갔다가 시작점으로
  돌아와 루프 클로저를 만들어 주면 지도가 다듬어짐.

```bash
mkdir -p ~/maps
# Nav2 용 (.pgm + .yaml)
ros2 run nav2_map_server map_saver_cli -f ~/maps/library_map
# slam_toolbox 재사용/localization 용 (.posegraph + .data)
ros2 service call /slam_toolbox/serialize_map \
  slam_toolbox/srv/SerializePoseGraph "{filename: '/home/ssafy/maps/library_map'}"
```

## 6. 트러블슈팅 (X4Pro 문서 근거)

| 증상 | 조치 |
|---|---|
| 모터가 안 돌거나 데이터가 끊김 | USB 전류 부족 가능성. 어댑터보드 **USB_PWR** 에 5V 보조 전원 연결 (User Manual 2.1, 4.3). 매뉴얼상 폰 보조배터리는 리플이 커서 비권장 → 벅컨버터 5V 등 안정 전원 사용 |
| 모터가 아예 회전 안 함 | `x4pro.yaml` 의 `support_motor_dtr` 를 `true` 로 토글 후 재시도 |
| "Failed to connect" / 데이터 파싱 실패 | 포트명 확인, `baudrate: 128000` 확인, 권한(dialout) 확인 |
| 지도가 좌우 반전 | `inverted` 토글 |
| 스캔 전/후 방향이 반대 | `reversion` 토글 |
| slam_toolbox 가 TF 에러 출력 | rf2o(odom->base_link)가 먼저 떠 있는지, `ros2 run tf2_tools view_frames` 로 트리 확인 |
| 프레임 기둥이 지도에 점으로 박힘 | `x4pro.yaml` 의 `ignore_array` 로 해당 각도 구간 마스킹 |

## 7. 다음 단계

1. STM32 휠 오도메트리 노드 완성 → rf2o 제거 또는 `publish_tf: false` + robot_localization EKF 융합
2. 저장한 지도로 slam_toolbox `mode: localization` 전환
3. Nav2 브링업 (AI 추종 위치값 → 목적지 이동 명령 파이프라인)
