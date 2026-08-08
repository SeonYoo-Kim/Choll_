# ROS2 API 명세 대조표 — embedded/Lidar (SLAM/NAV)

> 기준: 노션 "AI-EM ROS2 명세서" (2026-07-31 실측 기준, ROS2-01~13) ↔
> `embedded/Lidar` 패키지 실사용 인터페이스 (2026-08-03 코드 실측).
> 갱신 시 노션 명세서와 이 문서를 함께 수정할 것.

## 표 A. 명세서에 있는 API — 구현 현황 (EM 관련분)

| 메시지 ID | Topic | 메시지 타입 | 명세서 상태 | 실제 구현 | 비고 |
|---|---|---|---|---|---|
| ROS2-07 | `/scan` | sensor_msgs/LaserScan | 완료 | ✅ **`scan_mask_node` 발행**(~11Hz, 센서 QoS) — 드라이버 원본(`/scan_raw`)에서 카트 자기차폐 7섹터(83/430빔, 19.3%)를 NaN으로 만든 것. slam_toolbox·Nav2 costmap×2·AI가 구독 | 구독 측 **BEST_EFFORT** 필수 (Nav2 costmap은 기본이 센서 QoS라 설정 불필요). 2026-08-07 발행 주체 변경 — 토픽명·타입·QoS는 불변이라 구독 측 영향 없음 |
| ROS2-08 | `/robot_pose` | geometry_msgs/PoseStamped | 진행 중 (EM 미구현) | ✅ **구현 완료** — `cart_pose_publisher`가 TF map→base_link에서 10Hz 발행, frame=map, RELIABLE | **노션 상태를 "완료"로, Publisher를 `cart_pose_publisher`로 갱신 요청**. odom 프레임 포즈 금지 규약 준수 |
| ROS2-09 | `/target_position` | geometry_msgs/PointStamped | 진행 중 (EM 미구현) | ✅ **구현 완료** — `goal_forwarder`가 구독 → auto_orient(방향 자동)·approach_distance(1.0m 권장) 보정 후 Nav2 전달. 스로틀: 간격 1s(상시)+이동 0.3m(주행 중/성공 후) | **노션 상태를 "완료"로, Subscriber를 `goal_forwarder`로 갱신 요청** |
| ROS2-10 | `/cmd_vel` | geometry_msgs/Twist | 완료 (데모용 보존) | ⚠️ **발행 주체 충돌** — 명세는 AI `control_node`→`motor_node`(추종 데모). NAV 스택에서는 **Nav2 velocity_smoother가 발행**(20Hz, **\|v\|≤0.15·\|ω\|≤1.2 클램프 — 2026-08-07 변경**; 리커버리 중엔 behavior_server 직접 발행) | 🔴 2026-08-07 클램프 재배분: 회전 0.6 rad/s는 바퀴 1.754 = PWM 17로 모터 데드존(20) 미만이라 카트가 아예 회전하지 못해 Nav2가 150초간 NAVIGATING에 갇혔다(tests/TEST_LOG.md). 직진 0.3→0.15, 회전 0.6→1.2로 재배분. 추종 데모와 Nav2를 **동시에 켜면 이중 발행 충돌** — 운영 모드 일원화 팀 합의 필요 (명세서 방향은 ROS2-09→Nav2 경로) |
| ROS2-12 | `/wheel_speed_cmd` | std_msgs/Int32MultiArray | **취소** | 미사용 (Lidar 패키지에 생산/소비 없음) | 취소는 STM32 ASCII 시리얼(`SET_WHEEL_VEL`, rad/s) 확정 방향과 일치. ⚠️ `embedded/CLAUDE.md` 인터페이스 계약 절이 아직 이 토픽을 계약으로 서술 — JETSON_TO_STM.md 정본 확정 후 갱신 필요 |

ROS2-01~06, 11, 13은 AI 파트 내부 토픽으로 Lidar 패키지와 무관 (사용하지 않음).

### 중복 정리 이력 (2026-08-03~05)

- `/cart/pose` (PoseStamped, 10Hz) — **ROS2-08 `/robot_pose`와 동일 내용의 이름만 다른
  중복 발행이어서 제거**, `/robot_pose`로 일원화. BE MQTT 브릿지도 `/robot_pose`를
  구독하면 됨. 추가 발행 토픽이 필요하면 `pose_topics` 파라미터 배열에 추가
  (`choll_nav/launch/interface.launch.py`).
- MQTT-04 SELECT_TARGET — **AI `fe_bridge_node`가 이미 `/select_target`(ROS2-04) 변환
  담당**(backend/CLAUDE.md 실측, 2026-08-04 확인). choll_mqtt_bridge는 이중 발행 방지를
  위해 이 명령을 무시한다.
- MQTT-01 `status/position` 페이로드 — BE 파서(`MqttPositionMessageHandler`) 실측으로
  `{"x","y","timestamp"(ISO-8601, 선택)}` 확정. EM은 `yaw`(라디안, CCW+)를 추가 송신
  (BE 파서 확장 제안 상태). mapId는 페이로드에 없음(BE `mqtt.map-id` 설정).

## 표 B. 명세서에 없는 사용 중 API — 명세서 추가 제안 (노션 붙여넣기용)

| 메시지 ID(제안) | Topic | 메시지 타입 | 기능 설명 | Publisher | Subscriber | 사용 이유 |
|---|---|---|---|---|---|---|
| ROS2-14 | `/cart/target_pose` | geometry_msgs/PoseStamped | 단발성 목적지 이동 명령 (BE·수동). **header.frame_id 필수** — map 외 프레임은 TF 자동 변환 | **choll_mqtt_bridge `mqtt_bridge`** (MQTT-04 `cmd/move/cart` MOVE의 `target{x,y}` 변환 — 구현 완료), 수동 테스트 | goal_forwarder | ROS2-09(AI 연속 스트림·PointStamped)와 달리 ①방향 지정 가능 ②임의 프레임 허용 ③**스로틀 없이 즉시 선점**(사용자 명령 유실 방지). 웹 "구역 이동" 기능의 ROS 측 입구 |
| ROS2-15 | `/cart/cancel` | std_msgs/String | 주행 취소. **data = requestId** (선택, 빈 문자열 허용) — MQTT-04 CANCEL의 requestId를 그대로 실어 명령↔결과(CANCELED) 추적 가능 | **choll_mqtt_bridge `mqtt_bridge`** (MQTT-04 CANCEL 변환 — 구현 완료) | goal_forwarder | 웹 취소 버튼의 ROS 측 입구. goal 응답 대기 창에 도착해도 유실되지 않도록 구현됨. Empty 대신 String을 쓰는 이유: requestId 추적성 (2026-08-03 변경) |
| ROS2-16 | `/cart/nav_status` | std_msgs/String | 주행 상태: IDLE·NAVIGATING·SUCCEEDED·ABORTED·CANCELED·REJECTED·NAV2_UNAVAILABLE (래치 발행, 변화 시에만) | goal_forwarder | (예정) choll_mqtt_bridge — 상행 `status/nav` `{"requestId","status"}` 신설 합의 후 발행 추가 | FE `NAVIGATION_STATUS`(ACCEPTED/STARTED/ARRIVED/CANCELLED/FAILED) 이벤트의 원천 데이터. BE는 STARTED/ARRIVED/FAILED를 "카트 상행 결과 토픽 확정 후"로 보류 중(backend/CLAUDE.md). **값 매핑 팀 합의 필요** |
| ROS2-17 | `/odom_rf2o` | nav_msgs/Odometry | 레이저 스캔매칭 오도메트리 (10Hz). TF는 `publish_tf` 인자에 따라 발행/미발행 | rf2o_laser_odometry (외부) | `odom_covariance_node`(EKF 모드), Nav2 (bt_navigator·controller·velocity_smoother) | ⚠️ **공분산이 전부 0이다** — upstream이 채우지 않는다(2026-08-08 소스 확인). EKF에 직접 넣으면 "오차 없음"으로 읽히므로 `odom_covariance_node` 중계 필수. **`/odom` 이름은 휠 오도메트리용으로 예약** |
| ROS2-18 | `/map` | nav_msgs/OccupancyGrid | SLAM 점유 격자 지도 (0.05m/셀, TRANSIENT_LOCAL 래치) | slam_toolbox (매핑) / map_server (저장 지도 모드) | Nav2 global costmap, RViz | Nav2 경로계획의 기반 지도. 저장본(`~/maps/library_map.yaml`)의 resolution·origin이 BE `SlamCoordinateConverter`(미터↔픽셀 변환)의 입력값 |

## 부록 1. 내부 전용 인터페이스 (명세 등재 불필요 — 팀 계약 아님)

| 분류 | 이름 | 근거 |
|---|---|---|
| Nav2 내부 토픽 | `/cmd_vel_nav`(controller→smoother), `/plan`, `/local_plan`, `/local_costmap/*`, `/global_costmap/*`, `/map_updates`, DWB 디버그 토픽 | Nav2 노드 간 배선 — 외부 파트가 구독/발행할 일 없음 |
| 마스킹 전 원본 스캔 | `/scan_raw` (ydlidar 드라이버, 센서 QoS ~11Hz) — 구독자는 **rf2o와 `scan_mask_node` 둘만** | 🔴 rf2o는 **반드시 원본**을 써야 한다: 마스킹된 스캔을 주면 range 이미지 경계에서 허위 gradient가 생겨 정지 상태에서도 yaw가 −0.4 deg/s로 단조 드리프트한다(2026-08-07 실측, `tests/TEST_LOG.md`). 다른 파트는 `/scan`만 쓸 것 |
| 드라이버 부산물 | `/point_cloud_raw` (ydlidar) | 아무도 구독 안 함 (드라이버 기본 발행. `/scan`→`/scan_raw` 리맵과 함께 이름이 바뀜) |
| 위치추정 모드 전용 | `/initialpose`, `/amcl_pose`, `/particle_cloud` | 저장 지도 모드에서 RViz 2D Pose Estimate용 |
| 액션 | `navigate_to_pose` (goal_forwarder→bt_navigator), follow_path·compute_path_to_pose·spin·wait 등 | Nav2 표준 — 팀 인터페이스는 ROS2-09/14가 감쌈 |
| 서비스 | `/slam_toolbox/serialize_map` (지도 저장 절차), costmap clear (BT 리커버리가 호출) | 운영 절차용 — README에 기재 |
| 오도메트리 융합 (2026-08-08 신설) | `/wheel/odom`(stm_serial_bridge `wheel_odometry_node`, 별도 워크스페이스), `/odom_rf2o_cov`(`odom_covariance_node` 중계), `/odometry/filtered`(EKF 출력) | 융합 설계 정본은 `src/choll_slam_bringup/config/ekf.yaml` 상단 주석. 요지: **yaw는 rf2o, vx는 휠, 휠 yaw는 버린다**(좌측 구동 슬립 전진 4.79%/후진 11.86%, 밀기 대조 0.74% → 구동계 문제) |
| TF | `map→odom`(slam_toolbox/AMCL 중 하나만)→`base_link`(**rf2o 또는 EKF 중 하나만**)→`laser_frame`(정적, x=0.30 y=0.0 **z=0.32 실측 2026-08-07**). 카메라 장착 시 `base_link→camera_frame` 추가 예정 | 프레임 이름이 사실상의 계약 — 임의 변경 금지. 🔴 `ekf:=true` 면 rf2o `publish_tf`가 자동으로 false가 된다(`bringup.launch.py`) — 둘 다 발행하면 TF 트리가 깨진다 |

## 부록 2. 명세서·문서 후속 조치 체크리스트

- [ ] 노션: ROS2-08/09 상태 "완료" + Publisher/Subscriber 노드명 기입
- [ ] 노션: 표 B(ROS2-14~18) 행 추가
- [ ] 팀 합의: `/cmd_vel` 발행 주체 일원화 (AI 추종을 ROS2-09→Nav2 경로로 통일할지)
- [ ] 팀 합의: `/cart/nav_status` ↔ FE NAVIGATION_STATUS 값 매핑
- [ ] `embedded/CLAUDE.md`: 취소된 ROS2-12(micro-ROS `/wheel_speed_cmd`) 서술을
      JETSON_TO_STM.md 정본 확정 후 실제 프로토콜(ASCII 시리얼)로 교체
