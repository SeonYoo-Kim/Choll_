# CLAUDE.md — embedded/Lidar (SLAM/NAV 워크스페이스)

이 폴더는 **colcon 워크스페이스 루트**다 (여기서 `colcon build`).
사람용 셋업·검증 절차는 [README.md](README.md)가 정본.

## 구성 (자세한 것은 각 패키지 문서)

- `src/choll_slam_bringup` — 라이다+rf2o+slam_toolbox 설정/런치만 있는 패키지 (노드 없음)
- `src/choll_nav` — `cart_pose_publisher`(TF→`/robot_pose`+`/cart/pose` 10Hz),
  `goal_forwarder`(`/target_position`·`/cart/target_pose`→Nav2, `/cart/cancel`,
  `/cart/nav_status` 래치). 순수 로직은 `choll_nav/nav_logic.py` — ROS 없이
  `pytest src/choll_nav/test/test_nav_logic.py` 실행 가능 (31개).
- `src/choll_nav2` — Nav2 Humble 파라미터/런치. `bench:=true`=모터리스 검증용.
  `behavior_trees/navigate_to_pose_no_backup.xml` = **후진(BackUp) 리커버리 제거**
  커스텀 BT — behavior_server가 velocity_smoother를 우회하므로 BT에서 원천 차단.

## 절대 규칙

- `src/ydlidar_ros2_driver`, `src/rf2o_laser_odometry`는 upstream — **직접 수정 금지,
  커밋 금지**(.gitignore 처리됨). 설정 변경은 항상 choll_* 쪽 yaml/launch에서.
- 토픽 계약(`/robot_pose`, `/target_position`, `/cart/*`, `/scan`, `/cmd_vel`,
  `/odom_rf2o`)은 AI·BE와 합의된 것 — 단독 변경 금지 (docs/SYSTEM_ARCHITECTURE.md,
  노션 AI-EM ROS2 명세서 동시 갱신).
- odom→base_link TF 발행자는 항상 하나만 (STM32 휠 오도메트리 도입 시 rf2o 제거
  또는 publish_tf: false + EKF 융합).
- YDLIDAR X4 Pro: baud **128000**(115200 아님), 싱글채널(회전속도 시리얼 제어 불가).
- TODO-실측 표기 값(laser TF z=0.20, footprint, ignore_array, 가속 한계)은
  임의 확정 금지 — 팀 확인 후 갱신.

## 검증 루틴 (모든 변경 후)

`colcon build` → `ruff check`(repo pyproject 기준) → `pytest src/choll_nav/test/` →
`/scan` 6~12Hz → `view_frames` TF 트리 → RViz 육안. 결과는 `tests/TEST_LOG.md`에 기록.
