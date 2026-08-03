#!/usr/bin/env bash
# 쫄래쫄래 Lidar SLAM/NAV 의존성 설치 (Jetson Orin Nano / 노트북 공용)
# 전제: Ubuntu 22.04 + ROS2 Humble 설치됨. sudo 권한 필요.
# 사용: bash setup_jetson.sh   (이 파일이 있는 embedded/Lidar 에서 실행)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

echo "=== [1/4] apt 의존성 ==="
sudo apt update
sudo apt install -y \
  ros-humble-slam-toolbox ros-humble-navigation2 ros-humble-nav2-bringup \
  ros-humble-tf2-tools cmake build-essential git

echo "=== [2/4] YDLidar-SDK (드라이버 하드 의존성, 시스템 설치) ==="
if ! ls /usr/local/lib/cmake/ydlidar_sdk >/dev/null 2>&1; then
  SDK_DIR="$HOME/YDLidar-SDK"
  [ -d "$SDK_DIR" ] || git clone https://github.com/YDLIDAR/YDLidar-SDK.git "$SDK_DIR"
  mkdir -p "$SDK_DIR/build" && cd "$SDK_DIR/build"
  cmake .. && make -j"$(nproc)" && sudo make install
else
  echo "이미 설치됨 — 건너뜀"
fi

echo "=== [3/4] upstream ROS 패키지 클론 (git 미커밋 대상 — .gitignore 처리됨) ==="
cd "$HERE/src"
[ -d ydlidar_ros2_driver ] || git clone -b humble https://github.com/YDLIDAR/ydlidar_ros2_driver.git
[ -d rf2o_laser_odometry ] || git clone -b ros2 https://github.com/MAPIRlab/rf2o_laser_odometry.git

echo "=== [4/4] 라이다 포트 권한 (udev 규칙: /dev/ydlidar 별칭 + MODE 0666) ==="
sudo sh "$HERE/src/ydlidar_ros2_driver/startup/initenv.sh"
echo "※ 라이다 USB를 뽑았다 다시 꽂으면 규칙이 적용됩니다."

echo ""
echo "완료. 다음 단계:"
echo "  cd $HERE && source /opt/ros/humble/setup.bash"
echo "  colcon build --symlink-install && source install/setup.bash"
echo "  ros2 launch choll_slam_bringup lidar.launch.py   # /scan 6~12Hz 확인부터"
