# System Architecture

## AI Pipeline

```
                 RGB Camera
                      ↓
        YOLOv10s TensorRT (Person Detection)
                      ↓
            ByteTrack (Assign Track IDs)
                      ↓
      Operator selects librarian (2 seconds)
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
      Image Center Error Calculation
                      ↓
       LiDAR Distance Measurement
                      ↓
      PID Controller (Keep 1.0 m)
                      ↓
          Publish `/cmd_vel`
                      ↓
    Differential Drive (v, ω → L/R RPM)
                      ↓
     Publish `/wheel_speed_cmd` → STM32
```

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
    /wheel_speed_cmd   (Int32MultiArray [left_rpm, right_rpm] → STM32, micro-ROS)



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
