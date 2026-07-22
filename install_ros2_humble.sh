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
# sudo apt install -y ros-humble-rplidar-ros   # RPLiDAR 쓰는 경우
