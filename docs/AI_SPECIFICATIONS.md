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
* Update : Online

* Threshold : 0.90
* Replacement : FIFO



## Target Recovery

When ByteTrack loses the target, compare all detected persons using cosine similarity.  
Select the highest similarity.



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