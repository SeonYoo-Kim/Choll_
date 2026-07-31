# System Architecture

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
      Camera Bearing + LiDAR Distance
                      ↓
   Cart Pose from SLAM (EM, ROS2 topic)
                      ↓
   Target Map Position `/target_position`
                      ↓
   ── AI scope ends here (2026-07-31) ──
                      ↓
   SLAM Navigation planning (EM) → STM32 motors
```

> Legacy path (kept for demos until SLAM integration; code reused by EM):
> image-center error + LiDAR distance → PID → `/cmd_vel` → differential
> drive (v, ω → L/R RPM) → `/wheel_speed_cmd` → STM32.

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



## ROS2 Topics

    /camera/image_raw
    ↓
    /person_detection
    ↓
    /person_tracks
    ↓
    /target_person
    ↓
    /scan
    ↓
    /cmd_vel
    ↓
    /wheel_speed_cmd   (Int32MultiArray [제어종류, left_rpm, right_rpm] → STM32, micro-ROS.
                        제어종류: 0=모터, 1=LED. 규격: docs/JETSON_TO_STM.md)

    /target_distance   (Float32, control_node → debug_visualization_node:
                        LiDAR로 측정한 타겟 거리[m], 디버그 오버레이 표시용.
                        타겟은 보이지만 유효 LiDAR 거리가 없으면 NaN)

    /robot_pose        (geometry_msgs/PoseStamped frame=map, SLAM(EM) → target_position_node:
                        카트 현재 포즈. position.x/y[m] + orientation 쿼터니언(yaw).
                        AI가 이름·타입 선정, EM이 이 규격으로 발행하기로 확정 — 2026-07-31)

    /target_position   (geometry_msgs/PointStamped frame=map, target_position_node → SLAM Nav(EM):
                        사서의 지도 좌표[m]. 카트 포즈 + 카메라 방위각 + LiDAR 거리 융합.
                        미관측/거리 실패/포즈 stale(1s) 시 미발행)



## ROS2 Nodes

    camera_node
    ↓
    detector_node
    ↓
    tracker_node
    ↓
    reid_node
    ↓
    control_node
    ↓
    motor_node
