cmake_minimum_required(VERSION 3.8)
project(choll_slam_bringup)

find_package(ament_cmake REQUIRED)

install(DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME}
)

# 자기차폐 각도 마스킹 노드 (rf2o는 원본 /scan_raw, 나머지는 마스킹된 /scan)
# odom 공분산 스탬퍼 (rf2o가 공분산을 안 채워 EKF가 0을 "오차 없음"으로 읽는 문제)
# ZUPT (엔코더 정지 시 vx=0·vyaw=0 을 EKF에 알려 정지 중 yaw 드리프트를 막는다)
install(PROGRAMS
  scripts/scan_mask_node.py
  scripts/odom_covariance_node.py
  scripts/zupt_node.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
