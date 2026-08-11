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



## 실전 트러블슈팅 (실기 검증 사례)

### 1. 동일 의상 인물 오인식 → 연속 10프레임 이동거리 게이팅

같은 (팀 단체복) 의상을 입은 두 사람이 화면에 있으면 OSNet 외형 특징만으로는
구분이 안 돼, 타겟을 놓쳤다 되찾을 때 엉뚱한 사람에게 붙는 문제가 실기에서 발생했다.
위 Re-acquisition Gate의 **①시공간 타당성(마지막 목격 지점에서 도달 가능한 이동거리 제한)과
③연속 10프레임 동일 후보 확인**을 조합해 극복 — 외형 점수가 높아도 물리적으로
불가능한 위치의 후보는 기각되고, 한 순간의 오매칭이 즉시 타겟을 바꾸지 못한다.

![동일 의상 상황에서의 Re-ID 복구 — RECOVERED ID/SIM 배너](assets/reid-recovery-10frame-gate.jpg)

### 2. bbox 중앙 거리 오측정 → 가로 범위 내 최근접 LiDAR 거리

타겟 거리를 bbox **중앙 픽셀의 방위각 하나**로 LiDAR에서 읽으면, 사람 몸 중앙이
공교롭게 팔·몸통 사이 틈이거나 반사가 약한 옷일 때 **뒷배경(벽)의 거리**가 잡혀
카트가 갑자기 가속하는 문제가 있었다. bbox **가로축이 커버하는 각도 범위 전체**를
조회해 그중 **최근접 유효 거리**를 타겟 거리로 채택하도록 변경
(`control_node.py`의 `min_valid_range_in_span` — bbox 폭→각도 반폭 환산 포함).

![bbox 가로 범위 최근접 거리 측정 — TARGET DIST 오버레이](assets/lidar-bbox-min-dist.jpg)

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