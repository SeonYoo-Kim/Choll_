#!/usr/bin/env bash
# AI 재기동 전 메모리 확보 — EM 스택(라이다·SLAM·AMCL·EKF·MQTT·STM)은 건드리지 않는다.
#
# 배경 (2026-08-13 실측): reid_node 가 OSNet 을 GPU 로 올리다 CUDA OOM 으로 죽었다.
#   NvMapMemAllocInternalTagged: error 12 (ENOMEM)
#   tegrastats: RAM 4482/7620MB, **lfb 10x4MB**
# Orin Nano 는 통합 메모리라 CUDA 할당에 **연속 물리 블록**이 필요하다. lfb(최대
# 연속 빈 블록)가 4MB 면 총량이 남아도 실패한다. zram 스왑은 CUDA 할당에 못 쓴다.
#
# 🔴 gnome-shell / Xorg 는 죽이지 않는다 — 데스크톱 세션이 끊기면 RViz 를 못 띄운다.
#    죽이는 것은 데모에 불필요한 GUI 유틸리티뿐이다.
#
# 사용:  bash scripts/free_mem_for_ai.sh

echo "=== 종료 전 ==="
free -m | head -2
command -v tegrastats >/dev/null && timeout 3 tegrastats --interval 1000 2>/dev/null | head -1 | grep -o 'RAM [0-9]*/[0-9]*MB (lfb [^)]*)'

echo
echo "=== 1. AI 스택 종료 (약 1.9GB) ==="
pkill -f 'follow_robot_launch' 2>/dev/null || true
for n in camera_node detector_node tracker_node reid_node control_node \
         motor_node fe_bridge_node target_position_node debug_visualization_node ; do
    pkill -f "person_follow_robot/$n" 2>/dev/null || true
done
sleep 3

echo "=== 2. 불필요 GUI 유틸리티 종료 (약 0.4GB) ==="
# 데모와 무관한 데스크톱 앱. 데스크톱 세션(gnome-shell/Xorg)은 유지한다.
pkill -f 'update-manager' 2>/dev/null || true
pkill -f 'gnome-software' 2>/dev/null || true
pkill -f 'tracker-miner' 2>/dev/null || true      # 파일 인덱서 (있으면)
pkill -f 'evolution-' 2>/dev/null || true         # 메일/캘린더 백그라운드 (있으면)
sleep 2

echo "=== 3. 페이지 캐시 회수 (lfb 조각 완화) ==="
# 캐시를 비우면 연속 블록이 다시 생긴다. sudo 가 안 되면 건너뛴다 (치명적이지 않음).
sync
if sudo -n true 2>/dev/null; then
    sudo -n sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null \
        && echo "    drop_caches 완료" || echo "    drop_caches 실패"
    sudo -n sh -c 'echo 1 > /proc/sys/vm/compact_memory' 2>/dev/null \
        && echo "    compact_memory 완료" || true
else
    echo "    ⚠️ sudo 비밀번호가 필요해 건너뜀. 수동으로 돌리면 효과가 큽니다:"
    echo "       sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches; echo 1 > /proc/sys/vm/compact_memory'"
fi
sleep 2

echo
echo "=== 종료 후 ==="
free -m | head -2
command -v tegrastats >/dev/null && timeout 3 tegrastats --interval 1000 2>/dev/null | head -1 | grep -o 'RAM [0-9]*/[0-9]*MB (lfb [^)]*)'

echo
echo "=== EM 스택 생존 확인 (전부 남아 있어야 정상) ==="
ps -eo pid,args | grep -E 'ydlidar|rf2o|ekf_node|zupt_node|scan_mask|nav2_amcl|nav2_map_server|cart_pose_publisher|choll_mqtt|stm_serial|wheel_odometry' \
  | grep -v grep | awk '{print "  " $1 "  " $2}' | sed 's/\(.\{90\}\).*/\1/'
