# ROS2 API 명세 대조표 — embedded/Lidar (SLAM/NAV)

> 기준: 노션 "AI-EM ROS2 명세서" (2026-07-31 실측 기준, ROS2-01~13) ↔
> `embedded/Lidar` 패키지 실사용 인터페이스 (2026-08-03 코드 실측).
> 갱신 시 노션 명세서와 이 문서를 함께 수정할 것.

## 표 A. 명세서에 있는 API — 구현 현황 (EM 관련분)

| 메시지 ID | Topic | 메시지 타입 | 명세서 상태 | 실제 구현 | 비고 |
|---|---|---|---|---|---|
| ROS2-07 | `/scan` | sensor_msgs/LaserScan | 완료 | ✅ ydlidar 드라이버 발행(~11Hz, 센서 QoS). rf2o·slam_toolbox·Nav2 costmap×2가 구독 | 구독 측 **BEST_EFFORT** 필수 (Nav2 costmap은 기본이 센서 QoS라 설정 불필요) |
| ROS2-08 | `/robot_pose` | geometry_msgs/PoseStamped | 진행 중 (EM 미구현) | ✅ **구현 완료** — `cart_pose_publisher`가 TF map→base_link에서 10Hz 발행, frame=map, RELIABLE | **노션 상태를 "완료"로, Publisher를 `cart_pose_publisher`로 갱신 요청**. odom 프레임 포즈 금지 규약 준수 |
| ROS2-09 | `/target_position` | geometry_msgs/PointStamped | 진행 중 (EM 미구현) | ✅ **구현 완료** — `goal_forwarder`가 구독 → auto_orient(방향 자동)·approach_distance(1.0m 권장) 보정 후 Nav2 전달. 스로틀: 간격 1s(상시)+이동 0.3m(주행 중/성공 후) | **노션 상태를 "완료"로, Subscriber를 `goal_forwarder`로 갱신 요청** |
| ROS2-10 | `/cmd_vel` | geometry_msgs/Twist | 완료 (데모용 보존) | ⚠️ **발행 주체 충돌** — 명세는 AI `control_node`→`motor_node`(추종 데모). NAV 스택에서는 **Nav2 velocity_smoother가 발행**(20Hz, \|v\|≤0.3·\|ω\|≤0.6 클램프; 리커버리 중엔 behavior_server 직접 발행) | 추종 데모와 Nav2를 **동시에 켜면 이중 발행 충돌** — 운영 모드 일원화 팀 합의 필요 (명세서 방향은 ROS2-09→Nav2 경로) |
| ROS2-12 | `/wheel_speed_cmd` | std_msgs/Int32MultiArray | **취소** | 미사용 (Lidar 패키지에 생산/소비 없음) | 취소는 STM32 ASCII 시리얼(`SET_WHEEL_VEL`, rad/s) 확정 방향과 일치. ⚠️ `embedded/CLAUDE.md` 인터페이스 계약 절이 아직 이 토픽을 계약으로 서술 — JETSON_TO_STM.md 정본 확정 후 갱신 필요 |

ROS2-01~06, 11, 13은 AI 파트 내부 토픽으로 Lidar 패키지와 무관 (사용하지 않음).

### 중복 정리 이력 (2026-08-03)

- `/cart/pose` (PoseStamped, 10Hz) — **ROS2-08 `/robot_pose`와 동일 내용의 이름만 다른
  중복 발행이어서 제거**, `/robot_pose`로 일원화. BE MQTT 브릿지도 `/robot_pose`를
  구독하면 됨. 추가 발행 토픽이 필요하면 `pose_topics` 파라미터 배열에 추가
  (`choll_nav/launch/interface.launch.py`).

## 표 B. 명세서에 없는 사용 중 API — 명세서 추가 제안 (노션 붙여넣기용)

| 메시지 ID(제안) | Topic | 메시지 타입 | 기능 설명 | Publisher | Subscriber | 사용 이유 |
|---|---|---|---|---|---|---|
| ROS2-14 | `/cart/target_pose` | geometry_msgs/PoseStamped | 단발성 목적지 이동 명령 (BE·수동). **header.frame_id 필수** — map 외 프레임은 TF 자동 변환 | (예정) MQTT→ROS2 브릿지 (`choll/cart/cmd` MOVE), 수동 테스트 | goal_forwarder | ROS2-09(AI 연속 스트림·PointStamped)와 달리 ①방향 지정 가능 ②임의 프레임 허용 ③**스로틀 없이 즉시 선점**(사용자 명령 유실 방지). 웹 "구역 이동" 기능의 ROS 측 입구 |
| ROS2-15 | `/cart/cancel` | std_msgs/String | 주행 취소. **data = requestId** (선택, 빈 문자열 허용) — BE `choll/cart/cmd`의 requestId를 그대로 실어 명령↔결과(CANCELED) 추적 가능 | (예정) MQTT→ROS2 브릿지 (`choll/cart/cmd` CANCEL) | goal_forwarder | 웹 취소 버튼의 ROS 측 입구. goal 응답 대기 창에 도착해도 유실되지 않도록 구현됨. Empty 대신 String을 쓰는 이유: requestId 추적성 (2026-08-03 변경) |
| ROS2-16 | `/cart/nav_status` | std_msgs/String | 주행 상태: IDLE·NAVIGATING·SUCCEEDED·ABORTED·CANCELED·REJECTED·NAV2_UNAVAILABLE (래치 발행, 변화 시에만) | goal_forwarder | (예정) ROS2→MQTT 브릿지 → BE/FE | FE `NAVIGATION_STATUS`(ACCEPTED/STARTED/ARRIVED/CANCELLED/FAILED) 이벤트의 원천 데이터. **값 매핑 팀 합의 필요** (예: NAVIGATING→STARTED, SUCCEEDED→ARRIVED). Nav2 미기동 시 NAV2_UNAVAILABLE로 배선 자가진단 가능 |
| ROS2-17 | `/odom_rf2o` | nav_msgs/Odometry | 레이저 스캔매칭 오도메트리 (10Hz) + TF odom→base_link | rf2o_laser_odometry (외부) | Nav2 (bt_navigator·controller·velocity_smoother) | STM32 휠 오도메트리 도입 전 임시. **`/odom` 이름은 향후 휠 오도메트리용으로 예약**되어 있어 충돌 회피를 위해 별도 이름 사용. 휠 odom 도입 시 rf2o 제거 또는 EKF 융합으로 전환 |
| ROS2-18 | `/map` | nav_msgs/OccupancyGrid | SLAM 점유 격자 지도 (0.05m/셀, TRANSIENT_LOCAL 래치) | slam_toolbox (매핑) / map_server (저장 지도 모드) | Nav2 global costmap, RViz | Nav2 경로계획의 기반 지도. 저장본(`~/maps/library_map.yaml`)의 resolution·origin이 BE `SlamCoordinateConverter`(미터↔픽셀 변환)의 입력값 |

## 부록 1. 내부 전용 인터페이스 (명세 등재 불필요 — 팀 계약 아님)

| 분류 | 이름 | 근거 |
|---|---|---|
| Nav2 내부 토픽 | `/cmd_vel_nav`(controller→smoother), `/plan`, `/local_plan`, `/local_costmap/*`, `/global_costmap/*`, `/map_updates`, DWB 디버그 토픽 | Nav2 노드 간 배선 — 외부 파트가 구독/발행할 일 없음 |
| 드라이버 부산물 | `/point_cloud` (ydlidar) | 아무도 구독 안 함 (드라이버 기본 발행) |
| 위치추정 모드 전용 | `/initialpose`, `/amcl_pose`, `/particle_cloud` | 저장 지도 모드에서 RViz 2D Pose Estimate용 |
| 액션 | `navigate_to_pose` (goal_forwarder→bt_navigator), follow_path·compute_path_to_pose·spin·wait 등 | Nav2 표준 — 팀 인터페이스는 ROS2-09/14가 감쌈 |
| 서비스 | `/slam_toolbox/serialize_map` (지도 저장 절차), costmap clear (BT 리커버리가 호출) | 운영 절차용 — README에 기재 |
| TF | `map→odom`(slam_toolbox/AMCL 중 하나만)→`base_link`(rf2o)→`laser_frame`(정적, z=0.20 TODO-실측). 카메라 장착 시 `base_link→camera_frame` 추가 예정 | 프레임 이름이 사실상의 계약 — 임의 변경 금지 |

## 부록 2. 명세서·문서 후속 조치 체크리스트

- [ ] 노션: ROS2-08/09 상태 "완료" + Publisher/Subscriber 노드명 기입
- [ ] 노션: 표 B(ROS2-14~18) 행 추가
- [ ] 팀 합의: `/cmd_vel` 발행 주체 일원화 (AI 추종을 ROS2-09→Nav2 경로로 통일할지)
- [ ] 팀 합의: `/cart/nav_status` ↔ FE NAVIGATION_STATUS 값 매핑
- [ ] `embedded/CLAUDE.md`: 취소된 ROS2-12(micro-ROS `/wheel_speed_cmd`) 서술을
      JETSON_TO_STM.md 정본 확정 후 실제 프로토콜(ASCII 시리얼)로 교체
