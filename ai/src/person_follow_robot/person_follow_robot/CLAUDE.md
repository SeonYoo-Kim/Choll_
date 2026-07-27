# CLAUDE.md — ROS2 노드 소스

7개 노드가 토픽으로 느슨하게 결합된 파이프라인입니다. **각 노드 = 단일 책임(SRP).**
노드를 수정하기 전에 아래 토픽 계약과 "Known Gaps"를 먼저 확인하세요.

## 노드별 책임

| 노드 | 파일 | 책임 |
|------|------|------|
| CameraNode | camera_node.py | 카메라/영상 → RGB 프레임 발행. AI 추론과 분리. 영상 입력 시 EOF에서 되감기. |
| DetectorNode | detector_node.py | YOLOv10s TensorRT로 사람만 검출. `.engine` 파일 필수. Ultralytics 래퍼 사용. |
| TrackerNode | tracker_node.py | supervision ByteTrack으로 검출에 track ID 부여. `ByteTrackAdapter`가 버전별 인자명을 흡수. |
| ReidNode | reid_node.py | **핵심.** OSNet 512-D 임베딩 + Memory Bank(FIFO, 최대 20) + 초기 등록(2초) + 추적 실패 시 코사인 유사도 재탐색. |
| ControlNode | control_node.py | 화면 중심 오차 + LiDAR 거리 → PID → `cmd_vel`. 15Hz 루프. 측정 거리를 `/target_distance`로 공유. |
| MotorNode | motor_node.py | `/cmd_vel` → 차동구동 역기구학(v,ω→좌우 RPM) → `/wheel_speed_cmd` 10Hz 발행. cmd 끊기면 [0,0]. |
| DebugVisualizationNode | debug_visualization_node.py | 트랙/타겟/재탐색 이벤트 + 타겟 거리(박스 우상단, m)를 프레임에 오버레이, `/debug/image` 발행 및 선택적 mp4 저장. |

## 토픽 계약 (변경 시 양쪽 노드 + SYSTEM_ARCHITECTURE.md 동시 갱신)

| 토픽 | 타입 | 발행 | 구독 |
|------|------|------|------|
| `/camera/image_raw` | sensor_msgs/Image | camera | detector, reid, debug |
| `/person_detection` | vision_msgs/Detection2DArray | detector | tracker |
| `/person_tracks` | vision_msgs/Detection2DArray (`.id`=track id) | tracker | reid, debug |
| `/select_target` | std_msgs/Int32 | (사용자/CLI) | reid |
| `/target_person` | vision_msgs/Detection2DArray | reid | control, debug |
| `/reid/recovery_event` | std_msgs/String | reid | debug |
| `/cmd_vel` | geometry_msgs/Twist | control | motor |
| `/scan` | sensor_msgs/LaserScan | (LiDAR 드라이버) | control |
| `/target_distance` | std_msgs/Float32 (m, LiDAR 측정. NaN=측정 실패) | control | debug |
| `/wheel_speed_cmd` | std_msgs/Int32MultiArray (`[left_rpm, right_rpm]`) | motor | (STM32, micro-ROS) |

`vision_msgs` BoundingBox2D의 center는 배포판에 따라 `.position.x`(신형) 또는 `.x`(구형) 레이아웃이 다릅니다.
`_get_bbox_center` / `_set_bbox_center` 헬퍼가 양쪽을 처리하므로 **center를 직접 접근하지 말고 헬퍼를 쓰세요.**

## Known Gaps (알려진 통합 불일치 — 건드리기 전 확인)

1. **조립 후 확정해야 하는 값들 (현재 placeholder).**
   - `wheel_separation_m` (motor_node, 현재 0.30): 좌우 바퀴 중심 간 거리 실측 후 launch에서 교체.
   - `max_rpm` (motor_node, 현재 200): 모터 스펙 확정 시 조정.
   - `lidar_yaw_offset_deg` (control_node, 현재 0.0): LiDAR 0°축이 카메라 광축과 다르면 보정.
     캘리브레이션: 사람을 화면 정중앙에 세우고 LiDAR에서 잡히는 각도가 곧 오프셋.
   - 회전 방향 실기 검증: REP 103(+ω=좌회전) 기준으로 구현됨. 실기에서 반대로 돌면
     STM32 배선/모터 극성 확인 (코드 부호를 임의로 뒤집지 말 것).

2. **STM32까지 실제 전달은 micro-ROS agent 필요.** motor_node는 `/wheel_speed_cmd`를
   발행할 뿐이며, Jetson에서 micro-ROS agent가 UART로 브릿지해야 STM32에 도달합니다
   ([JETSON_TO_STM.md](../../../../docs/JETSON_TO_STM.md)). agent 실행은 EM 파트와 협의.

> ~~motor_node 스텁~~ — **해결됨.** 차동구동 역기구학(`cmd_vel_to_wheel_rpms`) +
> `/wheel_speed_cmd` 10Hz 발행 + cmd_vel 타임아웃 시 정지. 순수 로직 테스트: `tests/test_motor_logic.py`.
> ~~launch에 control/motor 미포함~~ — **해결됨.** follow_robot_launch.py가 7개 노드 전부 실행.

> ~~control_node ↔ reid_node 계약 단절~~ — **해결됨.** control_node가 `/target_person`(Detection2DArray)을
> 직접 구독하도록 재작성 (타임아웃 정지 + PID 리셋 포함). 순수 로직 테스트: `tests/test_control_logic.py`.

## 코딩 규칙 (이 디렉토리에 강제됨)

- **Type Hint + Docstring 필수** (`ruff` D/ANN 규칙). 신형 노드(detector/tracker/reid)의 스타일을 따르세요:
  dataclass로 프레임워크 독립 자료구조를 만들고, 무거운 의존성(torch/ultralytics/supervision)은 지연 import.
- **전역 변수 금지.** 상태는 노드 인스턴스 필드로.
- **콜백은 예외를 삼키고 로깅**해 파이프라인이 죽지 않게 한다 (detector `_image_callback` 참조).
- 모델/무거운 자원은 lazy-load하고 실패 시 `fatal` 로그 후 `raise` (detector/tracker/reid의 `__init__` 참조).
- 새 파라미터는 `declare_parameter` → launch 파일 기본값 → 문서 순으로 반영.
