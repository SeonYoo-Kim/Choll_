#!/bin/bash
set -e

echo "===== 1. 로케일 설정 ====="
sudo apt update && sudo apt install -y locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8

echo "===== 2. Ubuntu Universe 저장소 활성화 ====="
sudo apt install -y software-properties-common
sudo add-apt-repository universe -y

echo "===== 3. ROS2 GPG 키 및 저장소 추가 ====="
sudo apt update && sudo apt install -y curl gnupg
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

echo "===== 4. ROS2 Humble 설치 (desktop 전체 버전) ====="
sudo apt update
sudo apt upgrade -y
sudo apt install -y ros-humble-desktop

# 개발용 도구 (colcon, rosdep 등)
sudo apt install -y ros-dev-tools

echo "===== 5. rosdep 초기화 ====="
sudo rosdep init || echo "이미 초기화됨, 계속 진행"
rosdep update

echo "===== 6. 환경변수 자동 로드 설정 ====="
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc

echo "===== 설치 완료 ====="
echo "새 터미널을 열거나 'source ~/.bashrc' 실행 후 아래로 확인하세요:"
echo "  ros2 doctor"
echo "  printenv ROS_DISTRO   # humble 출력되어야 정상"

# 참고: 카메라/라이다용 자주 쓰는 추가 패키지 (필요시 주석 해제)
# sudo apt install -y ros-humble-cv-bridge ros-humble-image-transport

echo "===== 7. YDLiDAR SDK + ROS2 드라이버 빌드 (apt 바이너리 없음, 소스 빌드 필요) ====="
# YDLiDAR는 apt로 배포되지 않아서 소스에서 직접 빌드해야 함

# 7-1. 빌드 의존 패키지
sudo apt install -y cmake pkg-config git swig python3-pip

# 7-2. YDLidar-SDK (C++ 코어 라이브러리) 빌드/설치
cd ~
git clone https://github.com/YDLIDAR/YDLidar-SDK.git
cd YDLidar-SDK/build
cmake ..
make
sudo make install

# 7-3. ydlidar_ros2_driver 클론 (반드시 humble 브랜치로!)
mkdir -p ~/ydlidar_ros2_ws/src
cd ~/ydlidar_ros2_ws/src
git clone -b humble https://github.com/YDLIDAR/ydlidar_ros2_driver.git

# 7-4. 빌드
cd ~/ydlidar_ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install

# 7-5. USB 권한 스크립트 실행 (라이다 연결 후 재부팅 또는 재연결 필요할 수 있음)
chmod 0777 src/ydlidar_ros2_driver/startup/*
sudo sh src/ydlidar_ros2_driver/startup/initenv.sh

# 7-6. 환경변수 자동 로드
echo "source ~/ydlidar_ros2_ws/install/setup.bash" >> ~/.bashrc

echo "===== YDLiDAR 설치 완료 ====="
echo "라이다 모델에 맞는 파라미터 파일을 확인하세요:"
echo "  ~/ydlidar_ros2_ws/src/ydlidar_ros2_driver/params/"
echo "  (예: X4 모델이면 X4.yaml을 ydlidar.yaml로 복사해서 사용)"
echo ""
echo "실행:"
echo "  ros2 launch ydlidar_ros2_driver ydlidar_launch.py"
