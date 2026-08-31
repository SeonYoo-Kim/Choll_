#!/bin/bash
# choll_ai.sh — AI 추종 스택만 깨끗하게 1회 기동 (중복 방지)
#
#   bash choll_ai.sh            # 단순 추종 (control_node 가 /cmd_vel 직접) ← 기본
#   bash choll_ai.sh nav2       # Nav2 모드 (AI 는 /cmd_vel_legacy 로 격리)
#   bash choll_ai.sh --down     # AI 만 내린다
#
# 🔴 왜 필요한가 (2026-08-10 실측)
#    AI 를 두 번 띄우면 fe_bridge_node 가 2개가 되어 **같은 BE 웹소켓에 영상을
#    동시에 밀어넣고 충돌**한다. FE 영상이 검은 화면이 되고 "사람을 찾는
#    중이에요"에서 멈춘다. control_node 도 2개가 되어 /cmd_vel 이 섞인다.
#    그래서 기동 전에 반드시 전부 죽이고, 죽은 것을 확인한 뒤에 띄운다.
#
# 🔴 legacy_control 의 의미
#    true  = control_node 가 /cmd_vel 직접 발행 + motor_node 기동 (단순 추종)
#    false = /cmd_vel_legacy 로 격리, motor_node 미기동 (Nav2 가 /cmd_vel 소유)
#    choll-em 별칭은 false 로 고정돼 있어 **단순 추종에는 쓸 수 없다**.
#
# ⚠️ kill 은 전부 이 파일 안에서. 명령줄에 pkill 패턴이 걸릴 문자열
#    (control_node 등)을 넣으면 자기 셸이 죽는다 (exit 144, 실측).
AI_DIR=/home/ssafy/Choll
LOGDIR=/home/ssafy/S15P11C101/ros2_ws/log/choll_up
mkdir -p "$LOGDIR"

MODE=${1:-simple}
source /opt/ros/humble/setup.bash
[ -f "$AI_DIR/ai/install/setup.bash" ] && source "$AI_DIR/ai/install/setup.bash"
export ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-42}
unset ROS_LOCALHOST_ONLY

ai_down() {
  pkill -f 'follow_robot_launch.py'
  pkill -f 'person_follow_robot/camera_node'
  pkill -f 'person_follow_robot/detector_node'
  pkill -f 'person_follow_robot/tracker_node'
  pkill -f 'person_follow_robot/reid_node'
  pkill -f 'person_follow_robot/control_node'
  pkill -f 'person_follow_robot/motor_node'
  pkill -f 'person_follow_robot/fe_bridge_node'
  pkill -f 'person_follow_robot/target_position_node'
  pkill -f 'person_follow_robot/debug_visualization_node'
  sleep 5
  # 카메라를 놓지 않으면 새 camera_node 가 열지 못한다.
  if fuser /dev/video0 >/dev/null 2>&1; then
    echo "   SIGTERM 후에도 /dev/video0 점유 — SIGKILL"
    pkill -9 -f 'person_follow_robot/'
    sleep 3
  fi
}

echo "=== 기존 AI 정리 ==="
ai_down
LEFT=$(ps -eo args | grep -c "person_follow_robot/lib")
echo "   남은 AI 노드: $LEFT 개 $([ "$LEFT" = 0 ] && echo ✅ || echo 🔴)"
echo "   /dev/video0 점유: $(fuser /dev/video0 2>/dev/null | wc -w) 개"

if [ "$MODE" = "--down" ]; then
  echo "=== AI 종료 완료 ==="
  exit 0
fi

LEGACY=$([ "$MODE" = "nav2" ] && echo false || echo true)
echo
echo "=== AI 기동 (legacy_control:=$LEGACY, 모드=$MODE) ==="
# 🔴 모델을 models/*.engine 상대경로로 찾으므로 반드시 ~/Choll 에서 실행한다.
cd "$AI_DIR" || exit 1
nohup ros2 launch person_follow_robot follow_robot_launch.py \
  fe_bridge:=true auto_select:=false \
  be_video_ws_url:=ws://your-server.example.com/ws/carts/1/video/publish \
  mqtt_host:=your-server.example.com mqtt_username:=choll mqtt_password:=CHANGE_ME \
  legacy_control:=$LEGACY \
  > "$LOGDIR/ai.log" 2>&1 &

sleep 35
echo
echo "=== 기동 결과 (각 1개여야 정상) ==="
ps -eo args | grep "person_follow_robot/lib" | grep -v grep \
  | sed 's|.*/lib/person_follow_robot/||; s/ .*//' | sort | uniq -c
echo
echo "--- 오류 ---"
grep -iE "error|Traceback|FATAL|out of memory" "$LOGDIR/ai.log" | head -5
echo "(비어 있으면 정상)"
echo
echo "다음: ros2 topic info /cmd_vel -v | grep -E 'Publisher count|Node name'"
