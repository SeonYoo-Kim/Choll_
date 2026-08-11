# choll_nav — 쫄래쫄래 SLAM/NAV 인터페이스

카트 현재 위치 발행(`cart_pose_publisher`)과 목표 수신 → Nav2 전달
(`goal_forwarder`)을 담당하는 ROS2 Humble 패키지.

## 토픽 계약 (AI-EM ROS2 명세서 기준 — 대조표: embedded/Lidar/docs/ROS2_API.md)

| 토픽 | 타입 | 방향 | 설명 |
|---|---|---|---|
| `/robot_pose` | PoseStamped | 발행 10Hz | 명세서 ROS2-08 (AI 확정 계약 2026-07-31). frame=map, RELIABLE. 추가 발행 토픽은 `pose_topics` 파라미터로 확장 |
| `/target_position` | PointStamped | 구독 | AI가 발행하는 목표 지점 (방향 없음 → auto_orient). 스로틀 적용 |
| `/cart/target_pose` | PoseStamped | 구독 | 수동/BE 목표. **frame_id 필수**, map 외 프레임 TF 자동 변환. **스로틀 없이 항상 선점** |
| `/cart/cancel` | String | 구독 | 주행 취소. data=requestId (선택, 빈 문자열 허용 — BE 명령 추적용) |
| `/cart/nav_status` | String | 발행(래치) | IDLE / NAVIGATING / SUCCEEDED / ABORTED / CANCELED / REJECTED / NAV2_UNAVAILABLE |

## 주요 파라미터 (정본: launch/interface.launch.py)

- `approach_distance` (0.0): 목표 앞 유지 거리[m]. 사서 추종 시 1.0 권장
- `auto_orient` (True): 방향 미지정 시 로봇→목표 방향 자동 설정
- `min_goal_interval_sec` (1.0) / `min_goal_move_dist` (0.3): AI 스트림 goal 스로틀
  (간격은 상태 무관 항상 적용, 이동 거리는 주행 중·성공 직후 적용 — 플래핑 방지)
- `pose_topics`: 위치 발행 토픽 목록 (기본 `["/robot_pose"]`, 배열에 추가 가능)

## 실행

```bash
ros2 launch choll_nav interface.launch.py                        # 기본
ros2 launch choll_nav interface.launch.py approach_distance:=1.0 # 사서 추종
ros2 launch choll_nav view.launch.py                             # RViz (QoS 반영)
```

## Nav2 없이 검증 (배선 확인)

SLAM 스택(map→base_link TF)이 떠 있는 상태에서:

```bash
ros2 topic echo /robot_pose            # 10Hz 위치
ros2 topic echo /cart/nav_status       # IDLE
ros2 topic pub --once /cart/target_pose geometry_msgs/msg/PoseStamped \
  "{header: {frame_id: map}, pose: {position: {x: 1.0, y: 0.5}}}"
# → nav_status가 NAV2_UNAVAILABLE이면 정상 (Nav2 미기동 상태)
```

## 순수 로직 테스트 (ROS 불필요)

```bash
python3 -m pytest src/choll_nav/test/test_nav_logic.py -q
```
