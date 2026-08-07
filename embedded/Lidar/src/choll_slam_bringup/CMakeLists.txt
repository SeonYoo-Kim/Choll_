cmake_minimum_required(VERSION 3.8)
project(choll_slam_bringup)

find_package(ament_cmake REQUIRED)

install(DIRECTORY launch config
  DESTINATION share/${PROJECT_NAME}
)

# 자기차폐 각도 마스킹 노드 (rf2o는 원본 /scan_raw, 나머지는 마스킹된 /scan)
install(PROGRAMS
  scripts/scan_mask_node.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
