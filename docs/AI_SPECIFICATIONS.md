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

* Threshold : 0.70 (field tests: genuine re-appearance scored <0.80 while a
  distant person in plain dark clothing scored 0.92+ — similarity alone cannot
  separate them, so the low threshold is paired with the recovery gates below)
* Replacement : FIFO
* Post-recovery pause : bank updates suspended for 2 s after a re-lock so a
  misidentified person cannot poison the bank and entrench the error



## Target Recovery

When ByteTrack loses the target, candidates pass three gates in order:

1. **Spatio-temporal feasibility** — candidate bbox centre shift and size
   ratio (height ≈ inverse distance) must be reachable from the last sighting
   given the elapsed time (limits grow over time, so long absences are
   effectively unrestricted).
2. **Similarity + margin** — best cosine similarity ≥ threshold and leads the
   runner-up by ≥0.05.
3. **Temporal confirmation** — the same candidate must win 10 consecutive
   frames (≈0.33 s at 30 fps, ≈1 s at 10 fps) before the target is re-locked.



## Robot Controller (레거시 경로 — 실제 시연에 사용)

> 2026-07-31 아키텍처 변경으로 AI의 공식 책임은 `/target_position` 발행까지로 축소됐고
> 주행은 EM Nav2로 이관됐다. 다만 이 PID 경로는 `legacy_control:=true`(launch 기본값)로
> 보존됐고, **최종 시연은 이 경로로 진행됐다** — 경위는 [RETROSPECTIVE.md](RETROSPECTIVE.md) 참조.

* Input
  * Bounding Box Center (화면 중심 오차 → 각속도)
  * LiDAR Distance (전방 거리 → 선속도)

* Output
  * geometry_msgs/Twist (`/cmd_vel`)

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