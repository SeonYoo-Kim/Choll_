#!/usr/bin/env bash
# 단순 사서 추종 — 전체 스택 원커맨드 기동 (전원 켠 직후 상태에서 바로 실행 가능).
#
# ┌─ 구성 ──────────────────────────────────────────────────────────────────┐
# │ 구동:   AI control_node → /cmd_vel → stm_serial_bridge → STM32          │
# │         (legacy_control:=true. motor_node 도 함께 뜬다)                  │
# │ 위치:   라이다 → rf2o + 휠 + ZUPT → EKF → AMCL → /robot_pose            │
# │             → choll_mqtt_bridge → MQTT status/position → BE/FE 지도      │
# └─────────────────────────────────────────────────────────────────────────┘
#
# 🔴 Nav2 와 goal_forwarder 는 일부러 띄우지 않는다.
#    - Nav2 velocity_smoother 와 AI control_node 가 동시에 /cmd_vel 을 발행하면
#      두 명령이 번갈아 실려 카트가 예측 불가하게 움직인다. 발행자는 항상 1개.
#    - goal_forwarder 는 Nav2 없이 남으면 FOLLOW_START 이후 /target_position 마다
#      NAV2_UNAVAILABLE 을 status/nav-result 로 올려 BE 이동 세션을 망친다.
#      단순 추종은 goal_forwarder 를 경유하지 않는다.
#
# 🔴 AMCL 은 초기 위치가 없으면 map→odom 을 내지 않는다 (nav2_params.yaml 에
#    set_initial_pose 가 없다). --init 으로 주거나, RViz 2D Pose Estimate 로 찍어야
#    /robot_pose 가 나오고 BE 로 위치가 간다.
#    또한 update_min_d: 0.25 라서 **움직여야** AMCL 이 보정한다 — 서 있으면 안 맞는다.
#
# 🔴 --follow-only : 지도 없는 곳에서 추종만 시연할 때. 위치추정 스택을 통째로
#    생략한다. control_node 는 /target_person(카메라 방위각)과 /scan(라이다 거리)만
#    구독하므로 지도·TF·오도메트리가 전혀 필요 없다 — 지도 밖에서도 그대로 따라간다.
#    지도 밖에서 AMCL 을 켜 두면 스캔이 지도와 안 맞아 발산하고 FE 지도의 카트가
#    엉뚱한 데를 헤맨다. 켜는 게 오히려 해롭다.
#
# 사용:
#   bash scripts/simple_follow_up.sh --follow-only --fe       # 🔴 지도 없는 시연용
#   bash scripts/simple_follow_up.sh --follow-only            #    + 최근접 자동 선택
#   bash scripts/simple_follow_up.sh --fe --init 1.2 -0.4 90  # 지도 안 (위치 발행)
#   bash scripts/simple_follow_up.sh --map ~/maps/library_v2.yaml
#   bash scripts/simple_follow_up.sh --no-ai                  # 위치 스택만 (추종 없이)
#
# 종료:  bash scripts/choll_all_down.sh

# set -u 는 쓰지 않는다 — /opt/ros/humble/setup.bash 가 AMENT_TRACE_SETUP_FILES 를
# unbound 로 읽어 즉시 죽는다.
set -o pipefail

MAP="$HOME/maps/library_v3.yaml"
FE_MODE=0
RUN_AI=1
LOCALIZE=1          # 0 이면 rf2o/EKF/ZUPT/AMCL/map_server/pose/MQTT 전부 생략
INIT_X=""; INIT_Y=""; INIT_YAW=""
# 팀원이 실기에서 쓰던 값 (speed_profile:=slow 위에 max_wheel_rad_s 로 덮어쓴다).
# 프로파일보다 launch 인자가 우선한다.
SPEED_PROFILE="slow"
MAX_WHEEL_RAD_S="8.5"

while [ $# -gt 0 ]; do
    case "$1" in
        --fe)          FE_MODE=1; shift ;;
        --no-ai)       RUN_AI=0; shift ;;
        --follow-only) LOCALIZE=0; shift ;;
        --map)         MAP="$2"; shift 2 ;;
        --init)        INIT_X="$2"; INIT_Y="$3"; INIT_YAW="$4"; shift 4 ;;
        *) echo "알 수 없는 인자: $1"; exit 1 ;;
    esac
done

if [ "$LOCALIZE" = "1" ] && [ ! -f "$MAP" ]; then
    echo "🔴 지도 파일이 없습니다: $MAP"
    ls "$HOME/maps/"*.yaml
    echo "지도 없이 추종만 하려면 --follow-only 를 쓰세요."
    exit 1
fi

LOG=~/choll_logs/$(date +%m%d_%H%M%S)
mkdir -p "$LOG"

source /opt/ros/humble/setup.bash
source ~/S15P11C101/embedded/Lidar/install/setup.bash
source ~/S15P11C101/ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=42

if [ "$LOCALIZE" = "1" ]; then
    echo "모드: 추종 + 위치발행 (지도: $MAP)"
else
    echo "모드: 추종만 (--follow-only) — 지도·SLAM·AMCL·MQTT위치 전부 생략"
    echo "      control_node 는 /target_person 과 /scan 만 구독하므로 지도가 필요 없다."
    echo "      ⚠️ FE 지도에 카트 위치는 안 나온다 (status/position 미발행)."
fi
echo "로그: $LOG"
echo

# ── 0. 기존 프로세스 정리 ─────────────────────────────────────────────────
# 중복 기동은 이 프로젝트에서 반복된 실패 원인이다 — zupt 2개(→ /odom_zupt 18.9Hz),
# fe_bridge_node 2개(→ 같은 BE WebSocket 을 다투어 FE 영상이 검게 나옴).
echo "=== 0. 기존 프로세스 정리 ==="
bash ~/S15P11C101/embedded/Lidar/scripts/choll_all_down.sh > "$LOG/00_down.log" 2>&1
echo "    완료 (로그: $LOG/00_down.log)"

# ── 1. STM32 시리얼 브릿지 ────────────────────────────────────────────────
# 가장 먼저: ZUPT 가 /stm/encoder_total 을, EKF 가 /wheel/odom 을 필요로 한다.
echo "=== 1. STM32 시리얼 브릿지 + 휠 오도메트리 ==="
ros2 launch stm_serial_bridge stm_serial_bridge.launch.py \
    mode:=hardware speed_profile:="$SPEED_PROFILE" max_wheel_rad_s:="$MAX_WHEEL_RAD_S" \
    > "$LOG/01_stm.log" 2>&1 &
sleep 4
# 휠 오도메트리는 EKF 입력(odom1)일 뿐이다. 추종만 할 땐 소비자가 없다.
if [ "$LOCALIZE" = "1" ]; then
    ros2 run stm_serial_bridge wheel_odometry_node --ros-args \
        --params-file ~/S15P11C101/ros2_ws/install/stm_serial_bridge/share/stm_serial_bridge/config/wheel_odometry.yaml \
        > "$LOG/02_wheel_odom.log" 2>&1 &
fi
sleep 3
if timeout 8 ros2 topic echo /stm/connected --once 2>/dev/null | grep -q 'true'; then
    echo "    STM 연결 OK"
else
    echo "    ⚠️ STM 연결 확인 실패 — $LOG/01_stm.log 확인. NUCLEO RESET 한 번 눌러볼 것"
fi

# ── 2. 라이다 (+ 자기차폐 마스킹) ──────────────────────────────────────────
# /scan_raw (원본, rf2o 전용) → scan_mask_node → /scan (마스킹, SLAM/AI 용)
echo "=== 2. 라이다 ==="
ros2 launch choll_slam_bringup lidar.launch.py > "$LOG/03_lidar.log" 2>&1 &
sleep 6
HZ=$(timeout 12 ros2 topic hz /scan 2>/dev/null | grep -o 'average rate: [0-9.]*' | head -1)
echo "    /scan ${HZ:-측정 실패} (기대 6~12Hz)"

if [ "$LOCALIZE" = "0" ]; then
    # ── 추종만 모드 ───────────────────────────────────────────────────────
    # control_node 는 /target_person 과 /scan 만 구독한다 (TF·지도·오도메트리
    # 일절 안 씀). 그래서 지도 밖에서도 추종은 그대로 동작한다.
    # 지도 밖에서 AMCL 을 켜 두면 스캔이 지도와 안 맞아 발산하고 /robot_pose 가
    # 엉뚱한 좌표를 내보낸다 — 켜는 게 오히려 해롭다.
    echo "=== 3~8. 위치추정 스택 전체 생략 (--follow-only) ==="
    echo "    생략: rf2o · EKF · ZUPT · AMCL · map_server · cart_pose_publisher · MQTT브릿지"
    echo "    절약: 약 540MB (Orin Nano 통합메모리 — reid_node CUDA 할당 여유 확보)"
else
    # ── 3. 레이저 오도메트리 ──────────────────────────────────────────────
    # 🔴 publish_tf:=false — odom→base_link 발행은 EKF 가 독점한다. 발행자는 항상 1개.
    # 🔴 rf2o 입력은 /scan_raw. 마스킹된 /scan 을 주면 정지 중 yaw −0.4°/s 로 드리프트한다.
    echo "=== 3. rf2o 레이저 오도메트리 (publish_tf=false) ==="
    ros2 launch choll_slam_bringup laser_odom.launch.py publish_tf:=false \
        > "$LOG/04_rf2o.log" 2>&1 &
    sleep 4

    # ── 4. EKF 융합 (+ 공분산 중계 + ZUPT) ────────────────────────────────
    # odom0=/odom_rf2o_cov(vx,vy,vyaw)  odom1=/wheel/odom(vx만 — 좌측 슬립으로 yaw 못 씀)
    # odom2=/odom_zupt(정지 시 영속도). 정지 90초 yaw 표류 24° → 2.91° 로 개선된 조합.
    echo "=== 4. EKF + ZUPT ==="
    ros2 launch choll_slam_bringup ekf.launch.py > "$LOG/05_ekf.log" 2>&1 &
    sleep 5
    HZ=$(timeout 10 ros2 topic hz /odometry/filtered 2>/dev/null | grep -o 'average rate: [0-9.]*' | head -1)
    echo "    /odometry/filtered ${HZ:-측정 실패} (기대 20Hz)"

    # ── 5. AMCL 로컬라이제이션 ────────────────────────────────────────────
    # 저장된 지도 안에서 위치를 잡는다. 매핑 모드와 달리 매번 같은 좌표가 나와서
    # BE 구역 판정이 성립한다 (BE 캘리브레이션의 전제).
    echo "=== 5. AMCL + map_server ==="
    ros2 launch choll_nav2 localization.launch.py map:="$MAP" > "$LOG/06_amcl.log" 2>&1 &
    sleep 8

    # 🔴 autostart:=true 인데도 lifecycle 이 inactive 에서 멈추는 일이 있다
    #    (2026-08-13 실측: 메모리 압박 하에서 map_server/amcl 둘 다 inactive[2]).
    #    inactive 면 map→odom TF 가 안 나오고 /robot_pose 가 영영 안 뜬다.
    #    그래서 상태를 확인하고 직접 밀어 올린다. 이미 active 면 no-op 이다.
    for node in map_server amcl ; do
        state=$(timeout 10 ros2 lifecycle get "/$node" 2>/dev/null | head -1)
        case "$state" in
            active*) echo "    /$node 이미 active" ;;
            *)
                echo "    /$node 상태='$state' → activate 시도"
                timeout 20 ros2 lifecycle set "/$node" configure >/dev/null 2>&1
                timeout 20 ros2 lifecycle set "/$node" activate  >/dev/null 2>&1
                sleep 2
                echo "    /$node → $(timeout 10 ros2 lifecycle get "/$node" 2>/dev/null | head -1)"
                ;;
        esac
    done

    # ── 6. 초기 위치 ──────────────────────────────────────────────────────
    if [ -n "$INIT_X" ]; then
        echo "=== 6. 초기 위치 주입 ($INIT_X, $INIT_Y, ${INIT_YAW}°) ==="
        QZ=$(python3 -c "import math;print(math.sin(math.radians($INIT_YAW)/2))")
        QW=$(python3 -c "import math;print(math.cos(math.radians($INIT_YAW)/2))")
        # AMCL 이 구독을 붙이기 전에 쏘면 조용히 사라진다 → 여러 번 던진다.
        for i in 1 2 3 4 5; do
            timeout 6 ros2 topic pub --once /initialpose \
                geometry_msgs/msg/PoseWithCovarianceStamped \
                "{header: {frame_id: 'map'}, pose: {pose: {position: {x: $INIT_X, y: $INIT_Y, z: 0.0}, orientation: {z: $QZ, w: $QW}}, covariance: [0.25,0,0,0,0,0, 0,0.25,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0,0,0,0.068]}}" \
                > /dev/null 2>&1
            sleep 1
        done
        echo "    5회 발행 완료"
    else
        echo "=== 6. 초기 위치 — 건너뜀 ==="
        echo "    ⚠️ RViz 에서 2D Pose Estimate 로 찍어야 /robot_pose 가 나옵니다."
        echo "       (또는 --init x y yaw 로 재실행)"
    fi

    # ── 7. /robot_pose 발행 ───────────────────────────────────────────────
    # 🔴 interface.launch.py 를 쓰지 않는다 — 그건 goal_forwarder 를 함께 띄운다.
    #    단순 추종에서는 goal_forwarder 가 있으면 안 된다(상단 주석 참조).
    echo "=== 7. cart_pose_publisher (/robot_pose) ==="
    ros2 run choll_nav cart_pose_publisher --ros-args \
        -p pose_topics:="['/robot_pose']" -p publish_rate_hz:=10.0 \
        -p map_frame:=map -p base_frame:=base_link \
        > "$LOG/07_pose.log" 2>&1 &
    sleep 3
    HZ=$(timeout 10 ros2 topic hz /robot_pose 2>/dev/null | grep -o 'average rate: [0-9.]*' | head -1)
    if [ -n "$HZ" ]; then
        echo "    /robot_pose $HZ (기대 10Hz)"
    else
        echo "    ⚠️ /robot_pose 없음 — map→odom TF 가 없다는 뜻. 초기 위치를 찍어야 합니다."
    fi

    # ── 8. MQTT 브릿지 ────────────────────────────────────────────────────
    # /robot_pose → status/position (2Hz). 브로커 your-server.example.com:1883
    echo "=== 8. MQTT 브릿지 ==="
    ros2 launch choll_mqtt_bridge bridge.launch.py > "$LOG/08_mqtt.log" 2>&1 &
    sleep 4
    grep -qi 'connect\|접속\|연결' "$LOG/08_mqtt.log" && echo "    브로커 로그 있음" \
        || echo "    ⚠️ 브로커 접속 로그 없음 — $LOG/08_mqtt.log 확인"
fi

# ── 9. AI 추종 ────────────────────────────────────────────────────────────
if [ "$RUN_AI" = "0" ]; then
    echo "=== 9. AI — 건너뜀 (--no-ai) ==="
else
    echo "=== 9. /cmd_vel 발행자 사전 확인 ==="
    PUBS=$(timeout 10 ros2 topic info /cmd_vel 2>/dev/null | grep -oP 'Publisher count: \K[0-9]+')
    echo "    현재 발행자: ${PUBS:-0} (0 이어야 정상)"
    if [ "${PUBS:-0}" != "0" ]; then
        echo "    🔴 이미 누가 /cmd_vel 을 잡고 있습니다. 중단합니다."
        echo "       ros2 topic info /cmd_vel -v  로 확인 후 다시 실행하세요."
        exit 1
    fi

    echo "=== 9. AI 추종 기동 (legacy_control:=true) ==="
    # 🔴 모델을 models/*.engine 상대경로로 찾으므로 ~/Choll 에서 실행해야 한다.
    cd ~/Choll || exit 1
    source ~/Choll/ai/install/setup.bash

    # 🔴 map_target:=false — target_position_node 는 EM goal_forwarder 용
    #    /target_position 을 낸다. 단순 추종에는 소비자가 없다.
    # 🔴 debug_viz:=false  — 오버레이 영상은 디버그용. FE 영상은 fe_bridge_node 가
    #    따로 보내므로 FE 화면에 영향 없다.
    #    둘 다 끄면 약 215MB 절약 → reid_node 의 OSNet CUDA 할당 여유가 생긴다
    #    (2026-08-13: 메모리 부족으로 reid_node 가 CUDA OOM 으로 죽어 추종 불가했다).
    if [ "$FE_MODE" = "1" ]; then
        # FE 대상 선택 모드. be_video_ws_url 은 포트 없이 80 (bashrc choll-em 과 동일).
        ros2 launch person_follow_robot follow_robot_launch.py \
            legacy_control:=true \
            map_target:=false debug_viz:=false \
            fe_bridge:=true auto_select:=false \
            be_video_ws_url:=ws://your-server.example.com/ws/carts/1/video/publish \
            mqtt_host:=your-server.example.com \
            mqtt_username:=choll mqtt_password:=CHANGE_ME \
            2>&1 | tee "$LOG/09_ai.log"
    else
        ros2 launch person_follow_robot follow_robot_launch.py \
            legacy_control:=true auto_select:=true \
            map_target:=false debug_viz:=false \
            2>&1 | tee "$LOG/09_ai.log"
    fi
fi
