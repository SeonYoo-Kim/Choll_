# System Architecture

## 전체 시스템 구성

```
┌─ 사서용 웹 (React) ─────────────────────────────────────────────┐
│  홈(추종 제어·진행률) · 슬롯 보드 · 지도(실시간 위치·목적지 클릭) │
└───────────── REST /api ─┬─ WebSocket /ws (이벤트·영상) ─────────┘
                          │
┌─ Backend (Spring Boot) ─┴───────────────────────────────────────┐
│  REST API · WS 이벤트 13종 중계 · MQTT↔WS 브릿지                │
│  좌표 변환 (SLAM 미터 ↔ 평면도 픽셀, 아핀 6계수) · 구역 판정    │
└──────────────────── MQTT (mosquitto) ───────────────────────────┘
      ↑ status/position·cart·slot·target·nav-result    ↓ cmd/move/cart·cmd/lit/led
┌─ 카트 ───────────────────────────────────────────────────────────┐
│  Jetson Orin Nano: AI 파이프라인(ai/) + SLAM·Nav2(embedded/Lidar/)│
│    └ USB Serial ─ STM32 NUCLEO-F446RE (모터 PI 제어, ros2_ws/)   │
│  Raspberry Pi: RFID 리더 5기 + 슬롯 LED (embedded/rfid/)          │
└──────────────────────────────────────────────────────────────────┘
```

세부 계약: [specs/API_SPEC.md](specs/API_SPEC.md) (REST/WS/MQTT/ROS2 전체),
[JETSON_TO_STM.md](JETSON_TO_STM.md) (Jetson↔STM32).

## AI Pipeline

```
                 RGB Camera
                      ↓
        YOLOv10s TensorRT (Person Detection)
                      ↓
            ByteTrack (Assign Track IDs)
                      ↓
   Auto-select nearest person (largest bbox,
     0.5 s stable) → register for 2 seconds
     (또는 FE 영상 클릭 → SELECT_TARGET)
                      ↓
       OSNet Feature Extraction (512-D)
                      ↓
          Memory Bank Initialization
                      │
          ┌───────────┴───────────┐
          ↓                       ↓
   Tracking Success         Target Lost
          │                       │
          │               Re-ID Matching
          │                       │
          └───────────┬───────────┘
                      ↓
          Update Target Track ID
                      ↓
      ┌───────────────┴────────────────┐
      ↓ (계획 경로)                     ↓ (레거시 경로 — 실제 시연 구성)
 Camera Bearing + LiDAR Distance   Image-center error + LiDAR distance
      ↓                                 ↓
 Cart Pose from SLAM (/robot_pose)   PID (control_node)
      ↓                                 ↓
 /target_position (지도 좌표)        /cmd_vel → motor_node → STM32
      ↓
 EM Nav2 경로계획 → /cmd_vel → STM32
```

두 경로는 launch 인자 `legacy_control`로 전환한다:

| `legacy_control` | 동작 | 상태 |
|---|---|---|
| `true` (기본값) | control_node PID가 `/cmd_vel` 직접 발행 — **단순 추종. 최종 시연에 사용** | 실기 검증 완료 |
| `false` | motor_node 미기동, AI 출력은 `/cmd_vel_legacy`로 격리 — Nav2가 `/cmd_vel` 소유, `/target_position`을 goal로 소비 | 배선 완료, 실기 검증 부족 |

계획 경로가 시연에 쓰이지 못한 경위는 [RETROSPECTIVE.md](RETROSPECTIVE.md) 참조.
`/cmd_vel` 발행자는 동시에 하나여야 한다 — 두 경로를 함께 켜면 충돌한다 (실제 발생 사례 있음).

## Tracking Strategy

    Initial Registration
    ↓
    Memory Bank Creation
    ↓
    Normal Tracking
    ↓
    Target Lost
    ↓
    Re-ID Matching
    ↓
    Recover Target

## ROS2 Topics (AI 워크스페이스)

    /camera/image_raw
    ↓
    /person_detection
    ↓
    /person_tracks
    ↓
    /target_person
    ↓ (+ /scan)
    ├─ /target_position   (계획 경로 출력)
    └─ /cmd_vel           (레거시 경로 출력)

    /target_distance   (Float32, control_node → debug_visualization_node:
                        LiDAR로 측정한 타겟 거리[m], 디버그 오버레이 표시용.
                        타겟은 보이지만 유효 LiDAR 거리가 없으면 NaN)

    /robot_pose        (geometry_msgs/PoseStamped frame=map, SLAM(EM) → target_position_node:
                        카트 현재 포즈. 계약은 2026-07-31 확정 — 단 실배선은 미완,
                        검증은 수동 발행 포즈로만 수행됨. RETROSPECTIVE.md §3.5)

    /target_position   (geometry_msgs/PointStamped frame=map, target_position_node → EM goal_forwarder:
                        사서의 지도 좌표[m]. 카트 포즈 + 카메라 방위각 + LiDAR 거리 융합.
                        미관측/거리 실패/포즈 stale(1s) 시 미발행)

    /cmd_vel           (geometry_msgs/Twist → ros2_ws의 stm_serial_bridge가 USB Serial로 STM32에 중계.
                        구 /wheel_speed_cmd micro-ROS 계약은 폐기 — docs/JETSON_TO_STM.md)

EM(SLAM·Nav2) 쪽 토픽(/cart/target_pose, /cart/cancel, /cart/nav_status, /cart/follow_mode 등)은
[specs/API_SPEC.md](specs/API_SPEC.md)의 ROS2 표 참조.

## ROS2 Nodes (AI 워크스페이스)

    camera_node
    ↓
    detector_node
    ↓
    tracker_node
    ↓
    reid_node
    ├─ target_position_node   (계획 경로 — /target_position 발행)
    ├─ control_node → motor_node   (레거시 경로 — 시연 사용)
    ├─ debug_visualization_node
    └─ fe_bridge_node   (fe_bridge:=true 시 — BE 영상 릴레이 + SELECT_TARGET 중계)

## 워크스페이스 경계

| 워크스페이스 | 담당 | 주요 패키지 |
|---|---|---|
| `ai/` | 인지·추종 (이 문서의 AI Pipeline) | person_follow_robot |
| `embedded/Lidar/` | SLAM·Nav2·MQTT 브릿지 | choll_slam_bringup, choll_nav2, choll_nav, choll_mqtt_bridge |
| `ros2_ws/` | 모터 구동 (`/cmd_vel`→STM32) | stm_serial_bridge, cart_teleop |
