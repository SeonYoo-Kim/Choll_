#!/bin/bash
# choll_up.sh — 젯슨 EM 스택 원커맨드 기동 (별칭: choll-up)
#
#   choll-up                                   # 기본 지도로 전부 기동
#   choll-up --map ~/maps/library_v2.yaml      # 데모장 지도로 교체  ← 자주 쓸 형태
#   choll-up --init 1.2 -0.4 90                # 초기 위치 x y yaw[deg] 지정
#   choll-up --simple-follow                   # 단순 추종 모드 (아래 참조)
#   choll-up --no-ai                           # AI 추종 스택 제외 (구역 이동만)
#   choll-up --no-nav2                         # 위치 발행까지만 (지도 제작·점검)
#
# 🔴 주행 모드는 둘 중 하나만 — /cmd_vel 발행자는 항상 정확히 1개여야 한다.
#   (기본) Nav2 모드   : velocity_smoother 가 /cmd_vel 소유.
#                        AI 는 legacy_control:=false 로 /cmd_vel_legacy 에 격리.
#                        구역 이동 O / 추종은 Nav2 goal 경유(반응 느림).
#   --simple-follow    : AI control_node 가 /cmd_vel 직접 소유. Nav2 미기동.
#                        추종 즉응 O / **구역 이동 불가**.
#                        위치 발행(SLAM·AMCL→/robot_pose→MQTT)은 양쪽 다 동작한다
#                        — /cmd_vel 을 안 건드리기 때문. RFID·LED 구역 판정도 유지.
#   choll-up --linear 0.25 --angular 0.35      # 주행 성향 조절 (아래 참조)
#   choll-up --down                            # 전부 안전 순서로 종료
#
# 속도 인자 (2026-08-10)
#   --linear  <m/s>    직진/후진 최대. 비우면 nav.launch.py 기본값 0.45
#   --angular <rad/s>  회전 최대.     비우면 nav.launch.py 기본값 0.4
#   값은 여기서 해석하지 않고 demo.launch.py -> nav.launch.py 로 그대로 흘려보낸다.
#   실제 적용 지점(DWB / velocity_smoother)은 nav.launch.py 를 볼 것.
#
# 무엇을 하는가 (demo.launch.py 가 안 하는 것들)
#   ① 낡은 프로세스 정리 + 시리얼 포트 해제 확인
#   ② 모터 브릿지 기동 (ros2_ws — 다른 워크스페이스라 런치에 못 넣는다)
#   ③ demo.launch.py 기동 (라이다 → rf2o → EKF → AMCL → Nav2 → 위치 → MQTT)
#   ④ AMCL 라이프사이클이 inactive 로 멈췄으면 강제 활성화
#      (CPU 부하 시 전환 응답이 타임아웃나는 것을 2026-08-10 실측)
#   ⑤ 초기 위치 발행 — RViz 없이 map->base_link 를 세운다
#   ⑥ 기동 검증 후 AI 스택 기동 (순서 중요: AI 를 먼저 띄우면 ④가 터진다)
#   ⑦ 합격/불합격 요약 출력
#
# ⚠️ kill 은 전부 이 스크립트 "파일 안"에서 한다. 명령줄에 pkill -f 를 쓰면
#    패턴이 자기 자신의 cmdline 에 걸려 스스로를 죽인다(exit 144, 실측 3회).
set -o pipefail

REPO=/home/ssafy/S15P11C101
LIDAR_WS=$REPO/embedded/Lidar
ROS2_WS=$REPO/ros2_ws
AI_DIR=/home/ssafy/Choll
LOGDIR=$ROS2_WS/log/choll_up

MAP=${CHOLL_MAP:-$HOME/maps/library_map.yaml}
INIT_X=0.0; INIT_Y=0.0; INIT_YAW_DEG=0.0
WITH_AI=1; WITH_NAV2=1; WITH_MOTOR=1; DO_DOWN=0
# 단순 추종 모드: AI 가 /cmd_vel 을 직접 몬다 (legacy_control:=true).
SIMPLE_FOLLOW=0
CLIENT_ID=choll-jetson-bridge
# 빈 값 = "지정 안 함". 기본값은 여기 적지 않는다 — 정본은 nav.launch.py 의
# DEFAULT_MAX_*_VEL 이고, 두 곳에 적으면 한쪽만 고쳤을 때 조용히 갈린다.
MAX_LINEAR=""; MAX_ANGULAR=""

while [ $# -gt 0 ]; do
  case "$1" in
    --map)      MAP="$2"; shift 2 ;;
    --init)     INIT_X="$2"; INIT_Y="$3"; INIT_YAW_DEG="$4"; shift 4 ;;
    --simple-follow) SIMPLE_FOLLOW=1; WITH_NAV2=0; shift ;;
    --no-ai)    WITH_AI=0; shift ;;
    --no-nav2)  WITH_NAV2=0; shift ;;
    --no-motor) WITH_MOTOR=0; shift ;;
    --linear)   MAX_LINEAR="$2"; shift 2 ;;
    --angular)  MAX_ANGULAR="$2"; shift 2 ;;
    --client-id) CLIENT_ID="$2"; shift 2 ;;
    --down)     DO_DOWN=1; shift ;;
    -h|--help)  sed -n '2,40p' "$0"; exit 0 ;;
    *) echo "알 수 없는 인자: $1 (--help 참조)"; exit 2 ;;
  esac
done

mkdir -p "$LOGDIR"
source /opt/ros/humble/setup.bash
[ -f "$ROS2_WS/install/setup.bash" ]  && source "$ROS2_WS/install/setup.bash"
[ -f "$LIDAR_WS/install/setup.bash" ] && source "$LIDAR_WS/install/setup.bash"
[ -f "$AI_DIR/ai/install/setup.bash" ] && source "$AI_DIR/ai/install/setup.bash"
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-42}
unset ROS_LOCALHOST_ONLY

# ── 공용: 안전 종료 ────────────────────────────────────────────────────────
choll_down() {
  echo "① /cmd_vel 발행자 정지 (AI · Nav2 · teleop)"
  pkill -f 'follow_robot_launch.py'; pkill -f 'control_node'; pkill -f 'motor_node'
  pkill -f 'camera_node'; pkill -f 'detector_node'; pkill -f 'tracker_node'
  pkill -f 'reid_node'; pkill -f 'fe_bridge_node'; pkill -f 'target_position_node'
  pkill -f 'debug_visualization_node'; pkill -f 'teleop_keys'
  # 🔴 nav.launch.py(런치 부모)만 죽이면 Nav2 노드들이 살아남는다 — 2026-08-10 실측.
  #    그 상태로 --simple-follow 를 켜면 velocity_smoother 와 control_node 가
  #    /cmd_vel 을 동시에 발행해(Publisher count: 2) 명령이 섞인다.
  #    자식 노드를 이름으로 직접 죽여야 한다.
  pkill -f 'nav.launch.py'
  pkill -f 'nav2_velocity_smoother'; pkill -f 'velocity_smoother'
  pkill -f 'nav2_controller/controller_server'; pkill -f 'controller_server'
  pkill -f 'nav2_planner/planner_server'; pkill -f 'planner_server'
  pkill -f 'nav2_bt_navigator'; pkill -f 'bt_navigator'
  pkill -f 'nav2_behaviors'; pkill -f 'behavior_server'
  pkill -f 'nav2_smoother'; pkill -f 'smoother_server'
  pkill -f 'nav2_waypoint_follower'; pkill -f 'waypoint_follower'
  pkill -f 'lifecycle_manager_navigation'
  sleep 3

  echo "② 정지 확인 — /stm/pwm 이 0,0 이어야 안전하다"
  timeout 12 ros2 topic echo --once --csv /stm/pwm 2>/dev/null | tail -1

  echo "③ 위치·MQTT·Nav2·SLAM·라이다"
  pkill -f 'demo.launch.py'; pkill -f 'interface.launch.py'
  pkill -f 'cart_pose_publisher'; pkill -f 'goal_forwarder'
  pkill -f 'bridge.launch.py'; pkill -f 'mqtt_bridge'
  pkill -f 'localization.launch.py'; pkill -f 'amcl'; pkill -f 'map_server'
  pkill -f 'bringup.launch.py'; pkill -f 'async_slam_toolbox_node'
  pkill -f 'ekf.launch.py'; pkill -f 'ekf_node'
  pkill -f 'odom_covariance_node'; pkill -f 'zupt_node'
  pkill -f 'laser_odom.launch.py'; pkill -f 'rf2o_laser_odometry_node'
  pkill -f 'lidar.launch.py'; pkill -f 'ydlidar_ros2_driver_node'
  pkill -f 'scan_mask_node'; pkill -f 'static_transform_publisher'
  sleep 3

  echo "④ 모터 브릿지 (SIGTERM 으로 안 죽는다 — SIGKILL 폴백 필수)"
  pkill -f 'wheel_odometry_node'; pkill -f 'stm_serial_bridge'
  sleep 3
  if fuser /dev/ttyACM0 >/dev/null 2>&1; then
    echo "   SIGTERM 실패 → SIGKILL"
    pkill -9 -f 'stm_serial_bridge'; sleep 2
  fi
}

if [ "$DO_DOWN" = 1 ]; then
  echo "=== 안전 순서로 종료 ==="
  choll_down
  ros2 daemon stop >/dev/null 2>&1
  sleep 2
  pkill -f 'ros2cli.daemon' 2>/dev/null
  echo
  echo "=== 최종 ==="
  fuser -v /dev/ttyACM0 /dev/ttyUSB0 2>&1 || echo "  시리얼 포트 점유 없음 ✅"
  exit 0
fi

# ── 사전 점검 ──────────────────────────────────────────────────────────────
if [ ! -f "$MAP" ]; then
  echo "🔴 지도 파일이 없다: $MAP"
  echo "   사용 가능한 지도:"; ls -1t "$HOME"/maps/*.yaml 2>/dev/null | sed 's/^/     /'
  exit 1
fi

echo "════════════════════════════════════════════════════════════"
echo " 쫄래쫄래 EM 스택 기동"
echo "   지도       : $MAP"
echo "   초기 위치  : x=$INIT_X y=$INIT_Y yaw=${INIT_YAW_DEG}deg"
echo "   Nav2       : $([ $WITH_NAV2 = 1 ] && echo 예 || echo 아니오)"
echo "   직진 상한  : ${MAX_LINEAR:-기본값 (nav.launch.py DEFAULT_MAX_LINEAR_VEL)}"
echo "   회전 상한  : ${MAX_ANGULAR:-기본값 (nav.launch.py DEFAULT_MAX_ANGULAR_VEL)}"
echo "   모터       : $([ $WITH_MOTOR = 1 ] && echo 예 || echo 아니오)"
echo "   AI 추종    : $([ $WITH_AI = 1 ] && echo 예 || echo 아니오)"
if [ "$SIMPLE_FOLLOW" = 1 ]; then
  echo "   주행 모드  : 단순 추종 (control_node 가 /cmd_vel 직접) — 구역 이동 불가"
else
  echo "   주행 모드  : Nav2 (velocity_smoother 가 /cmd_vel) — 구역 이동 가능"
fi
echo "   로그       : $LOGDIR"
echo "════════════════════════════════════════════════════════════"
echo

echo "▶ [1/7] 기존 프로세스 정리"
choll_down
ros2 daemon stop >/dev/null 2>&1; sleep 2
pkill -f 'ros2cli.daemon' 2>/dev/null; sleep 1
ros2 daemon start >/dev/null 2>&1; sleep 2
HOLD=$(fuser /dev/ttyACM0 2>/dev/null | wc -w)
echo "   /dev/ttyACM0 점유: $HOLD 개 $([ "$HOLD" = 0 ] && echo ✅ || echo 🔴)"

if [ "$WITH_MOTOR" = 1 ]; then
  echo "▶ [2/7] 모터 브릿지 + 휠 오도메트리"
  nohup ros2 launch stm_serial_bridge stm_serial_bridge.launch.py \
    mode:=hardware speed_profile:=nav2 > "$LOGDIR/motor.log" 2>&1 &
  sleep 8
  nohup ros2 run stm_serial_bridge wheel_odometry_node --ros-args \
    --params-file "$ROS2_WS/install/stm_serial_bridge/share/stm_serial_bridge/config/wheel_odometry.yaml" \
    > "$LOGDIR/wheel_odom.log" 2>&1 &
  sleep 3
else
  echo "▶ [2/7] 모터 브릿지 건너뜀 (--no-motor)"
fi

echo "▶ [3/7] EM 스택 (라이다 → rf2o → EKF → AMCL → Nav2 → 위치 → MQTT)"
# 🔴 왜 demo.launch.py 를 안 쓰고 여기서 하나씩 띄우는가 (2026-08-10 실측)
#    `IncludeLaunchDescription` 을 `TimerAction` 안에 넣으면 `map` 치환이
#    nav2_bringup 의 RewrittenYaml 까지 전달되지 않는다. map_server 가
#      "parameter 'yaml_filename' is not initialized"
#    로 configure 에 실패하고 lifecycle_manager 가 bringup 을 abort 한다.
#    증상은 "/robot_pose 무음" 하나로만 드러나 원인을 찾기 어렵다.
#    CLI 로 `ros2 launch ... map:=<경로>` 를 직접 부르는 경로는 확실히 동작하므로
#    (restart_localize.sh 로 반복 검증) 그 형태를 그대로 쓴다.
# 지정한 것만 넘긴다 — 빈 값을 넘기면 nav.launch.py 가 float('') 로 죽는다.
SPEED_ARGS=""
[ -n "$MAX_LINEAR" ]  && SPEED_ARGS="$SPEED_ARGS max_linear_vel:=$MAX_LINEAR"
[ -n "$MAX_ANGULAR" ] && SPEED_ARGS="$SPEED_ARGS max_angular_vel:=$MAX_ANGULAR"

stage() {  # $1=설명  $2=대기초  $3...=ros2 launch 인자
  local desc=$1 wait_s=$2; shift 2
  local log="$LOGDIR/$(echo "$desc" | tr ' /' '__').log"
  echo "   · $desc"
  nohup ros2 launch "$@" > "$log" 2>&1 &
  sleep "$wait_s"
}

# 지연은 의존 순서에서 온다. 라이다가 /scan 을 내기 전에 rf2o 가 뜨면 스캔매칭이
# 빈 입력으로 시작하고, EKF 없이 AMCL 이 뜨면 odom->base_link 가 없어 map->odom
# 을 못 만든다.
stage "lidar"        6 choll_slam_bringup lidar.launch.py
stage "rf2o"         4 choll_slam_bringup laser_odom.launch.py publish_tf:=false
stage "ekf_zupt"     4 choll_slam_bringup ekf.launch.py
stage "localization" 14 choll_nav2 localization.launch.py map:="$MAP"
if [ "$WITH_NAV2" = 1 ]; then
  # shellcheck disable=SC2086  # 빈 인자를 단어 분리로 없애려는 의도
  stage "nav2" 18 choll_nav2 nav.launch.py $SPEED_ARGS
fi
stage "interface"    6 choll_nav interface.launch.py \
  approach_distance:=1.0 follow_gate_enabled:=true
stage "mqtt"         6 choll_mqtt_bridge bridge.launch.py client_id:="$CLIENT_ID"

echo "▶ [4/7] map_server·AMCL 활성화 대기"
# lifecycle_manager 가 알아서 올리는 게 정상이지만 두 가지로 실패한다:
#   - CPU 부하로 change_state 응답이 타임아웃 -> inactive 에서 멈춤
#   - map_server configure 실패(지도 경로 문제) -> unconfigured 에서 abort
# 둘 다 조용히 실패하고 그 결과는 "/robot_pose 무음"으로만 드러난다. 직접 민다.
for attempt in $(seq 1 12); do
  ALL_ACTIVE=1
  for n in map_server amcl; do
    ST=$(timeout 15 ros2 lifecycle get /$n 2>/dev/null | head -1)
    case "$ST" in
      *active*)  ;;
      *unconfigured*) ALL_ACTIVE=0
        timeout 30 ros2 lifecycle set /$n configure >/dev/null 2>&1 ;;
      *inactive*)     ALL_ACTIVE=0
        timeout 30 ros2 lifecycle set /$n activate  >/dev/null 2>&1 ;;
      *)              ALL_ACTIVE=0 ;;
    esac
  done
  [ "$ALL_ACTIVE" = 1 ] && break
  sleep 5
done
for n in map_server amcl; do
  echo "   /$n : $(timeout 15 ros2 lifecycle get /$n 2>/dev/null | head -1)"
done

echo "▶ [5/7] 초기 위치 발행 (RViz 없이 map->base_link 를 세운다)"
YAW_RAD=$(python3 -c "import math;print(math.radians($INIT_YAW_DEG))")
QZ=$(python3 -c "import math;print(math.sin($YAW_RAD/2))")
QW=$(python3 -c "import math;print(math.cos($YAW_RAD/2))")
timeout 25 ros2 topic pub --once /initialpose \
  geometry_msgs/msg/PoseWithCovarianceStamped \
  "{header: {frame_id: 'map'}, pose: {pose: {position: {x: $INIT_X, y: $INIT_Y, z: 0.0}, \
orientation: {x: 0.0, y: 0.0, z: $QZ, w: $QW}}, \
covariance: [0.25,0,0,0,0,0, 0,0.25,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0.068]}}" \
  >/dev/null 2>&1
sleep 5
# AMCL 은 초기 pose 를 받아야 map->odom 을 내기 시작한다. 한 번에 안 잡히는
# 경우가 있어 /robot_pose 가 나올 때까지 최대 3회 재발행한다.
for retry in 1 2 3; do
  timeout 8 ros2 topic hz /robot_pose --window 5 2>/dev/null \
    | grep -q "average rate" && break
  echo "   /robot_pose 무음 — 초기 위치 재발행 ($retry/3)"
  timeout 25 ros2 topic pub --once /initialpose \
    geometry_msgs/msg/PoseWithCovarianceStamped \
    "{header: {frame_id: 'map'}, pose: {pose: {position: {x: $INIT_X, y: $INIT_Y, z: 0.0}, \
orientation: {x: 0.0, y: 0.0, z: $QZ, w: $QW}}, \
covariance: [0.25,0,0,0,0,0, 0,0.25,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0.068]}}" \
    >/dev/null 2>&1
  sleep 5
done

echo "▶ [6/7] 기동 검증"
PASS=1
check() {  # $1=이름  $2=실측  $3=합격조건 설명  $4=합격여부(0/1)
  if [ "$4" = 1 ]; then printf "   ✅ %-22s %s\n" "$1" "$2"
  else printf "   🔴 %-22s %s   (기대: %s)\n" "$1" "$2" "$3"; PASS=0; fi
}

SCAN=$(timeout 10 ros2 topic hz /scan --window 15 2>/dev/null | grep -oE "average rate: [0-9.]+" | head -1 | grep -oE "[0-9.]+$")
check "/scan" "${SCAN:-무음} Hz" "6~12 Hz" \
  "$(python3 -c "print(1 if ${SCAN:-0} > 6 and ${SCAN:-0} < 13 else 0)")"

POSE=$(timeout 10 ros2 topic hz /robot_pose --window 15 2>/dev/null | grep -oE "average rate: [0-9.]+" | head -1 | grep -oE "[0-9.]+$")
check "/robot_pose" "${POSE:-무음} Hz" "8~12 Hz (TF map->base_link 성립)" \
  "$(python3 -c "print(1 if ${POSE:-0} > 8 and ${POSE:-0} < 13 else 0)")"

if [ "$WITH_NAV2" = 1 ]; then
  NPUB=$(timeout 20 ros2 topic info /cmd_vel -v 2>/dev/null | grep -c "Node name")
  # Publisher/Subscriber 를 합쳐 세므로 발행자 수는 별도로 뽑는다
  NP=$(timeout 20 ros2 topic info /cmd_vel 2>/dev/null | grep "Publisher count" | grep -oE "[0-9]+")
  check "/cmd_vel 발행자" "${NP:-?} 개" "정확히 1개 (velocity_smoother)" \
    "$([ "${NP:-0}" = 1 ] && echo 1 || echo 0)"
fi

if [ "$WITH_MOTOR" = 1 ]; then
  ENC=$(timeout 10 ros2 topic hz /stm/encoder_total --window 15 2>/dev/null | grep -oE "average rate: [0-9.]+" | head -1 | grep -oE "[0-9.]+$")
  check "/stm/encoder_total" "${ENC:-무음} Hz" "약 10 Hz (ZUPT 판정 입력)" \
    "$(python3 -c "print(1 if ${ENC:-0} > 5 else 0)")"
fi

MQ=$(grep -c "MQTT 접속·구독 완료" "$LOGDIR/em_stack.log" 2>/dev/null)
check "MQTT 접속" "$([ "${MQ:-0}" -ge 1 ] && echo 성공 || echo 실패)" "rc=0 접속·구독 완료" \
  "$([ "${MQ:-0}" -ge 1 ] && echo 1 || echo 0)"

# 단순 추종이면 control_node 가 /cmd_vel 을 잡고 motor_node 도 함께 뜬다.
LEGACY=$([ "$SIMPLE_FOLLOW" = 1 ] && echo true || echo false)
if [ "$WITH_AI" = 1 ]; then
  echo "▶ [7/7] AI 추종 스택 (EM 검증 후에 띄운다 — 순서가 중요)"
  cd "$AI_DIR" || exit 1   # 모델을 models/*.engine 상대경로로 찾는다
  nohup ros2 launch person_follow_robot follow_robot_launch.py \
    fe_bridge:=true auto_select:=false \
    be_video_ws_url:=ws://your-server.example.com/ws/carts/1/video/publish \
    mqtt_host:=your-server.example.com mqtt_username:=choll mqtt_password:=CHANGE_ME \
    legacy_control:=$LEGACY \
    > "$LOGDIR/ai.log" 2>&1 &
  sleep 35
  if pgrep -f "person_follow_robot/reid_node" >/dev/null; then
    echo "   ✅ AI 기동 (reid_node 생존)"
  else
    echo "   🔴 reid_node 가 없다 — CUDA OOM 가능. $LOGDIR/ai.log 확인"
    PASS=0
  fi
else
  echo "▶ [7/7] AI 건너뜀 (--no-ai). 필요하면 별도 터미널에서 choll-em"
fi

echo
echo "════════════════════════════════════════════════════════════"
if [ "$PASS" = 1 ]; then
  echo " ✅ 기동 완료 — 데모 준비됨"
else
  echo " ⚠️ 일부 항목 불합격 — 위 🔴 항목과 $LOGDIR/*.log 확인"
fi
echo "════════════════════════════════════════════════════════════"
echo
echo " 다음 확인:"
echo "   ros2 topic info /cmd_vel -v          # 발행자 1개인지"
echo "   python3 $ROS2_WS/log/phase4_20260808/follow_watch.py 60"
echo
echo " 🔴 위치가 지도와 안 맞으면 RViz 에서 2D Pose Estimate 를 다시 찍거나"
echo "    choll-up --init <x> <y> <yaw도> 로 재기동할 것."
echo " 🔴 추종 대상 선택은 카메라에서 2~3m 물러나 화면 중앙에서."
echo " 🔴 추종과 구역 이동을 동시에 걸지 말 것."
echo
echo " 종료: choll-up --down"
