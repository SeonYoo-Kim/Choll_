# Project Charter

## Vision

Develop an AIoT autonomous library cart that follows one librarian continuously after an initial registration period.



## Goal

Track one librarian from start to finish.

Maintain a distance of 1 meter.

Recover tracking after temporary occlusion.

Operate in real time on Jetson Orin Nano 8GB.



## Out of Scope

- Face Recognition
- Voice Recognition
- Human Pose Estimation
- Crowd Analysis



## Target Platform

- Jetson Orin Nano 8GB
- ROS2 Humble
- Python 3.10
- TensorRT



## Constraints

- No additional dataset collection
- No fine-tuning
- TensorRT inference only
- Embedded deployment
- Real-time operation



## Success Criteria

✓ 10 FPS or higher (LiDAR 스캔이 ~10 Hz라 이를 기준으로 설정)

✓ Maintain 1 meter distance

✓ Recover lost target

✓ Stable ROS2 communication

✓ Demo-ready