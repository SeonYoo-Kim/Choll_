#!/usr/bin/env bash
#
# stm_serial_bridge 통합 검증 — 하드웨어 없이 반복 실행 가능한 워크플로우.
#
# 실제 장치(/dev/ttyACM*)를 절대 열지 않는다. mock 이 만든 PTY 만 사용한다.
#
# 3개 시나리오를 순서대로 돌리고 각 로그를 파일로 남긴다:
#
#   1. connect   : mock STATUS -> /stm/* 6개 토픽 발행 확인
#   2. cmd_vel   : /cmd_vel -> SET_WHEEL_VEL -> mock -> STATUS -> encoder_total 변화 확인
#   3. disconnect: STATUS 중단 -> status_timeout_sec -> connected=false 확인
#
# 사용법:
#   bash scripts/verify_bridge_mock.sh                  # 로그는 ros2_ws/log/bridge_verify/ 에
#   bash scripts/verify_bridge_mock.sh --log-dir /tmp/x
#
# 기본 로그 위치를 `log/` 아래로 둔 이유: 저장소 .gitignore 가 이미 `log/` 를 무시하므로
# 검증 로그가 git 추적 대상으로 새지 않는다.
#
# 종료 코드: 전부 통과 0, 하나라도 실패 1.
#
# ⚠️ 시나리오마다 launch 를 완전히 정리하고 다음으로 넘어간다. 이전 시나리오의
#    브리지가 살아남으면 같은 토픽에 두 노드가 발행해 결과가 오염되므로,
#    프로세스 그룹 단위로 종료하고 마지막에 잔존 프로세스를 검사한다.

set -uo pipefail

LOG_DIR="./log/bridge_verify"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --log-dir) LOG_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# 다른 머신의 /cmd_vel 이 우리 노드에 닿지 않게 격리한다. 이 스크립트 안에서만 유효하다.
export ROS_LOCALHOST_ONLY=1

MOCK_PTY_LINK="/tmp/stm_serial_bridge_mock_pty"

WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$WORKSPACE_DIR" || exit 1

if [[ ! -f install/setup.bash ]]; then
  echo "install/setup.bash 가 없다. 먼저 빌드할 것:" >&2
  echo "  cd $WORKSPACE_DIR && colcon build --symlink-install" >&2
  exit 1
fi

# ROS 의 setup.bash 는 미설정 변수를 참조하므로 이 구간만 `set -u` 를 끈다.
set +u
# shellcheck disable=SC1091
source /opt/ros/humble/setup.bash
# shellcheck disable=SC1091
source install/setup.bash
set -u

RUN_STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${LOG_DIR}/${RUN_STAMP}"
mkdir -p "$LOG_DIR" || exit 1

echo "======================================================================"
echo " stm_serial_bridge mock 통합 검증"
echo " 워크스페이스: $WORKSPACE_DIR"
echo " 로그        : $LOG_DIR"
echo " ROS_LOCALHOST_ONLY=$ROS_LOCALHOST_ONLY (다른 머신과 격리)"
echo "======================================================================"

MY_PGID="$(ps -o pgid= -p $$ 2>/dev/null | tr -d ' ')"
LAUNCH_PID=""
LAUNCH_PGID=""

# launch 와 그 자식(mock_stm, 브리지 노드)을 모두 정리한다.
# 중간에 실패하거나 Ctrl+C 로 빠져나가도 고아가 남지 않게 trap 으로 항상 부른다.
cleanup() {
  if [[ -n "$LAUNCH_PID" ]]; then
    local target
    if [[ -n "$LAUNCH_PGID" ]]; then
      target="-$LAUNCH_PGID"   # 프로세스 그룹 전체
    else
      target="$LAUNCH_PID"     # 그룹을 못 만든 경우의 최소 동작
    fi
    kill -INT "$target" 2>/dev/null
    for _ in $(seq 1 60); do
      kill -0 "$target" 2>/dev/null || break
      sleep 0.2
    done
    kill -KILL "$target" 2>/dev/null
    wait "$LAUNCH_PID" 2>/dev/null
    LAUNCH_PID=""
    LAUNCH_PGID=""
  fi
  rm -f "$MOCK_PTY_LINK"
}
trap 'cleanup; exit 130' INT TERM
trap cleanup EXIT

start_launch() {
  # $1 = 로그 파일, 나머지 = launch 인자
  local log_file="$1"; shift
  rm -f "$MOCK_PTY_LINK"

  # setsid 로 별도 프로세스 그룹에 띄운다 — 그래야 자식까지 한 번에 정리할 수 있다.
  setsid ros2 launch stm_serial_bridge stm_serial_bridge.launch.py mode:=mock "$@" \
    >"$log_file" 2>&1 &
  LAUNCH_PID=$!

  LAUNCH_PGID="$(ps -o pgid= -p "$LAUNCH_PID" 2>/dev/null | tr -d ' ')"
  if [[ -z "$LAUNCH_PGID" || "$LAUNCH_PGID" == "$MY_PGID" ]]; then
    # 새 그룹이 만들어지지 않았다. 그룹 kill 은 이 스크립트까지 죽이므로 쓰지 않는다.
    LAUNCH_PGID=""
    echo "  경고: 별도 프로세스 그룹을 만들지 못했다 — 종료 시 자식이 남을 수 있다" >&2
  fi

  # mock 이 PTY 를 만들고 브리지가 기동해 STATUS 를 받기까지 기다린다.
  sleep 6
  if ! kill -0 "$LAUNCH_PID" 2>/dev/null; then
    echo "  launch 가 기동하지 못했다. 로그: $log_file" >&2
    return 1
  fi
  return 0
}

FAILURES=0
record() {
  # $1 = 시나리오 이름, $2 = 종료 코드
  if [[ "$2" -eq 0 ]]; then
    echo "  ---> ✅ $1 통과"
  else
    echo "  ---> ❌ $1 실패 (exit $2)"
    FAILURES=$((FAILURES + 1))
  fi
}

# ---------------------------------------------------------------------------
echo ""
echo "[1/3] connect — mock STATUS 가 /stm/* 6개 토픽으로 발행되는가"
# ---------------------------------------------------------------------------
if start_launch "$LOG_DIR/1_connect_launch.log"; then
  ros2 run stm_serial_bridge check_stm_topics --timeout-sec 10 \
    2>&1 | tee "$LOG_DIR/1_connect_check.log"
  record "connect" "${PIPESTATUS[0]}"
else
  record "connect" 1
fi
cleanup

# ---------------------------------------------------------------------------
echo ""
echo "[2/3] cmd_vel — /cmd_vel 이 mock 까지 갔다가 encoder_total 변화로 돌아오는가"
# ---------------------------------------------------------------------------
if start_launch "$LOG_DIR/2_cmdvel_launch.log"; then
  # max_wheel_rad_s=1.0 기준 linear.x=0.065 -> 좌우 1.0 rad/s (상한 이내)
  timeout 8 ros2 topic pub -r 20 /cmd_vel geometry_msgs/msg/Twist \
    "{linear: {x: 0.065}, angular: {z: 0.0}}" \
    >"$LOG_DIR/2_cmdvel_pub.log" 2>&1 &
  CMD_PID=$!
  sleep 1
  # 1초 간격으로 두 번 읽어 누적 count 가 실제로 증가했는지 본다.
  FIRST="$(timeout 5 ros2 topic echo --once --field data /stm/encoder_total 2>/dev/null)"
  sleep 1
  SECOND="$(timeout 5 ros2 topic echo --once --field data /stm/encoder_total 2>/dev/null)"
  kill -INT "$CMD_PID" 2>/dev/null
  wait "$CMD_PID" 2>/dev/null

  {
    echo "encoder_total 1차: $FIRST"
    echo "encoder_total 2차: $SECOND"
  } | tee "$LOG_DIR/2_cmdvel_check.log"

  if [[ -n "$FIRST" && -n "$SECOND" && "$FIRST" != "$SECOND" ]]; then
    echo "  누적 count 가 변화했다 (TX -> mock -> STATUS -> 토픽 왕복 성립)" \
      | tee -a "$LOG_DIR/2_cmdvel_check.log"
    record "cmd_vel" 0
  else
    echo "  누적 count 가 변하지 않았다" | tee -a "$LOG_DIR/2_cmdvel_check.log"
    record "cmd_vel" 1
  fi
else
  record "cmd_vel" 1
fi
cleanup

# ---------------------------------------------------------------------------
echo ""
echo "[3/3] disconnect — STATUS 중단 후 status_timeout_sec 로 connected=false 가 되는가"
# ---------------------------------------------------------------------------
if start_launch "$LOG_DIR/3_disconnect_launch.log" mock_stop_after_sec:=9.0; then
  ros2 run stm_serial_bridge check_stm_topics --expect-disconnect --timeout-sec 15 \
    2>&1 | tee "$LOG_DIR/3_disconnect_check.log"
  record "disconnect" "${PIPESTATUS[0]}"
else
  record "disconnect" 1
fi
cleanup

# ---------------------------------------------------------------------------
# 잔존 프로세스 검사 — 고아가 남으면 다음 실행 결과가 오염된다.
# ---------------------------------------------------------------------------
sleep 1
LEFTOVER="$(pgrep -af 'stm_serial_bridge_node|mock_stm' || true)"
if [[ -n "$LEFTOVER" ]]; then
  echo ""
  echo "  ❌ 잔존 프로세스가 있다 — 수동으로 정리할 것:"
  echo "$LEFTOVER"
  FAILURES=$((FAILURES + 1))
fi

# ---------------------------------------------------------------------------
echo ""
echo "======================================================================"
if [[ "$FAILURES" -eq 0 ]]; then
  echo " 결과: ✅ 3개 시나리오 전부 통과 (잔존 프로세스 없음)"
else
  echo " 결과: ❌ $FAILURES 개 항목 실패"
fi
echo " 로그: $LOG_DIR"
echo ""
echo " ⚠️ 이 검증은 하드웨어 없이 '경로와 형식'만 확인한다. 다음은 검증되지 않는다:"
echo "    - wheel_actual_rad_s 의 수치 정확도 (엔코더 스케일 12.1% 미확정)"
echo "    - 실제 모터 구동·전류·부하, 실제 USB Serial 전기적 특성"
echo "    - 실제 Stall 발생 시 펌웨어의 FAULT 판정"
echo "======================================================================"

[[ "$FAILURES" -eq 0 ]] || exit 1
exit 0
