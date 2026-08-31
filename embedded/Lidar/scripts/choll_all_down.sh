#!/usr/bin/env bash
# 전체 스택 안전 종료 — 젯슨 재기동 없이 "처음부터" 상태로 되돌린다.
#
# 🔴 종료 순서가 안전 수칙이다 (CLAUDE.md):
#      구동 명령 발행자(AI/Nav2/teleop) → /stm/pwm 0 확인 → 시리얼 브릿지 → 라이다
#    바퀴를 굴리는 쪽을 먼저 끊지 않으면, 브릿지가 죽는 순간 마지막 명령이
#    STM 에 남아 카트가 계속 굴러간다. ROS 비상정지는 없다.
#
# 🔴 pkill -f 패턴을 호출 명령줄에 두면 pkill 이 자기 셸을 매칭해 셸이 같이
#    죽는다(exit 144). 그래서 모든 kill 을 이 파일 안에 둔다.
#
# 사용:  bash scripts/choll_all_down.sh

echo "=========== 1단계: 구동 명령 발행자 정지 ==========="

# AI 추종 (control_node → /cmd_vel, motor_node → /wheel_speed_cmd)
pkill -f 'follow_robot_launch' 2>/dev/null || true
for n in camera_node detector_node tracker_node reid_node control_node \
         motor_node fe_bridge_node target_position_node debug_visualization_node ; do
    pkill -f "person_follow_robot/$n" 2>/dev/null || true
done

# 키보드 teleop
pkill -f 'keyboard_teleop' 2>/dev/null || true

# Nav2 — launch 를 죽여도 자식이 살아남는 경우가 있어 명시적으로 훑는다
# (2026-08-10 실측: velocity_smoother 가 살아남아 /cmd_vel 발행을 계속했다)
pkill -f 'nav.launch.py' 2>/dev/null || true
for n in nav2_controller/controller_server nav2_planner/planner_server \
         nav2_behaviors/behavior_server nav2_bt_navigator/bt_navigator \
         nav2_waypoint_follower/waypoint_follower nav2_smoother/smoother_server \
         nav2_velocity_smoother/velocity_smoother ; do
    pkill -f "$n" 2>/dev/null || true
done

sleep 2

echo "--- /cmd_vel 발행자 (0 이어야 정상) ---"
timeout 10 ros2 topic info /cmd_vel 2>/dev/null | grep -i 'publisher count' || echo "  (토픽 없음)"

echo
echo "--- /stm/pwm 확인 (0 이어야 안전) ---"
timeout 8 ros2 topic echo /stm/pwm --once 2>/dev/null || echo "  (수신 없음 — 브릿지가 이미 정지했거나 미발행)"

echo
echo "=========== 2단계: 상위 스택 정지 ==========="

pkill -f 'choll_mqtt_bridge' 2>/dev/null || true          # MQTT 브릿지
pkill -f 'interface.launch.py' 2>/dev/null || true
pkill -f 'choll_nav/goal_forwarder' 2>/dev/null || true
pkill -f 'choll_nav/cart_pose_publisher' 2>/dev/null || true

# 로컬라이제이션 (AMCL + map_server + lifecycle_manager)
pkill -f 'localization.launch.py' 2>/dev/null || true
pkill -f 'nav2_amcl/amcl' 2>/dev/null || true
pkill -f 'nav2_map_server/map_server' 2>/dev/null || true
pkill -f 'nav2_lifecycle_manager/lifecycle_manager' 2>/dev/null || true

# 매핑 모드로 돌고 있었다면
pkill -f 'slam_toolbox' 2>/dev/null || true
pkill -f 'sync_slam_toolbox_node' 2>/dev/null || true
pkill -f 'async_slam_toolbox_node' 2>/dev/null || true

sleep 2

echo "=========== 3단계: 오도메트리 · 시리얼 브릿지 ==========="

pkill -f 'ekf.launch.py' 2>/dev/null || true
pkill -f 'robot_localization/ekf_node' 2>/dev/null || true
pkill -f 'zupt_node' 2>/dev/null || true              # 🔴 빠뜨리면 재기동마다 누적된다
pkill -f 'odom_covariance_node' 2>/dev/null || true
pkill -f 'laser_odom.launch.py' 2>/dev/null || true
pkill -f 'rf2o_laser_odometry' 2>/dev/null || true

pkill -f 'stm_serial_bridge.launch.py' 2>/dev/null || true
pkill -f 'stm_serial_bridge_node' 2>/dev/null || true
pkill -f 'wheel_odometry_node' 2>/dev/null || true

sleep 2

echo "=========== 4단계: 라이다 (가장 마지막) ==========="

pkill -f 'lidar.launch.py' 2>/dev/null || true
pkill -f 'scan_mask_node' 2>/dev/null || true
pkill -f 'ydlidar_ros2_driver_node' 2>/dev/null || true

sleep 2

# ROS2 데몬 — 노드 목록 캐시가 유령 노드를 계속 보고하는 것을 막는다
ros2 daemon stop >/dev/null 2>&1 || true

echo
echo "=========== 잔존 확인 (아무것도 안 나와야 정상) ==========="
ps -eo pid,args | grep -E 'ydlidar|rf2o|ekf_node|zupt_node|scan_mask|slam_toolbox|nav2_|choll_nav|choll_mqtt|stm_serial|wheel_odometry|person_follow_robot|follow_robot_launch' \
  | grep -v grep | sed 's/\(.\{100\}\).*/\1/' || echo "  (없음) 전부 종료 완료"
