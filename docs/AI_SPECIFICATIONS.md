# AI Specifications

## Detector

* Model : YOLOv10s

  * Reason
    * Highest FPS after TensorRT benchmark on Jetson

  * Input
    * RGB Image

  * Output
    * Bounding Boxes


## Tracker

* Algorithm : ByteTrack

  * Reason
    * No training required
    * Fast and stable

  * Output
    * Track ID


## Re-ID

* Model : OSNet_x1_0  
  
* Embedding : 512-D  
* Training : Pretrained only  
* Fine-tuning : Not used
* Similarity : Cosine Similarity


## Memory Bank

* Initialization : 2 seconds
* Maximum Features : 20
* Update : Online, sampled every 0.3 s (per-frame updates fill the FIFO with
  near-identical views and break recovery — 2026-07-29 field finding)
* Crop quality gate : side-clipped or close-up (>50 % of frame) boxes are
  rejected (OSNet expects full-body 128x256 crops)

* Threshold : 0.85 (0.90 rejected genuine re-appearances in field tests;
  other persons scored ≤0.68)
* Replacement : FIFO



## Target Recovery

When ByteTrack loses the target, compare all detected persons using cosine similarity.
Accept the highest similarity if it exceeds the threshold **and** leads the
runner-up by at least the recovery margin (0.05) to avoid misidentification.



## Robot Controller

* Input
  * Bounding Box Center
  * LiDAR Distance

* Output
  * geometry_msgs/Twist

* Target Distance
  * 1.0 meter

* Controller
  * PID



## Performance Targets

* FPS 10+
  * 파이프라인은 더 높은 FPS도 가능하지만, LiDAR 스캔이 약 10 Hz로 들어오므로
    거리 기반 제어의 실질 상한이 10 FPS라 목표를 10으로 맞춤.
* Latency < 100 ms
* GPU Memory < 6 GB
* TensorRT Required
* ROS2 Required