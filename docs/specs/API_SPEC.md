# API 명세서 (FE-BE REST / WebSocket / EM-BE MQTT / AI-EM ROS2)

> 개발 기간 중 노션에서 관리하던 4개 인터페이스 명세의 이관본 (2026-08-11 기준).
> REST 응답 DTO 상세는 [API_CONTRACT.md](../API_CONTRACT.md), WS 페이로드 실구현은 [backend/CLAUDE.md](../../backend/CLAUDE.md) 참조.
> ROS2 표의 "위치" 열은 ai/src/person_follow_robot/person_follow_robot/ 기준 파일:라인 (2026-08-03 코드 실측).

## 공통 Path Parameter
| 이름 | 타입 | 설명 | 예시 |
|---|---|---|---|
| cartId | Number | 카트 식별자 | 1 |
| mapId | Number | 지도 식별자 | 2 |
| slotNumber | Number | 카트의 슬롯 번호 | 1~12 |

## FE-BE REST API
| API ID | 이름 | 설명 | 엔드포인트 | Method | 예시 |
|---|---|---|---|---|---|
| CART-01 | 카트 상태 조회 | 카트의 연결 상태, 동작 상태, 현재 위치와 구역을 조회 | /api/carts/{cartId} | GET | GET /api/carts/1 |
| SLOT-01 | 전체 슬롯 조회 | 전체 슬롯 정보를 조회 | /api/carts/{cartId}/slots | GET | GET /api/carts/1/slots |
| SLOT-02 | 개별 슬롯 조회 | 특정 슬롯의 책 유무, 책 정보를 조회 | /api/carts/{cartId}/slots/{slotNumber} | GET | GET /api/carts/1/slots/3 |
| MAP-01 | SLAM 지도 조회 | SLAM 지도 버전 및 지도 정보 조회 | /api/maps/{mapId} | GET | |
| MAP-02 | 책장 구역 목록 조회 | SLAM 지도의 책장 구역 목록 조회 | /api/maps/{mapId}/zones | GET | |
| TASK-01 | 도서 정리 작업 목록 조회 | 카트 적재 도서의 슬롯, 배치 구역 및 정리 상태 목록 | /api/carts/{cartId}/tasks | GET | |
| TASK-02 | 전체 정리 진행률 조회 | 대시보드 화면 기준 | /api/carts/{cartId}/tasks/progress | GET | |
| TASK-03 | 현재 구역 정리 대상 조회 | 현재 구역에서 꺼내야 하는 도서와 슬롯 조회 | /api/carts/{cartId}/current-zone/tasks | GET | |
| NAV-01 | 목적지 이동 시작 | 지도 선택 위치로 이동. x·y(지도 클릭 픽셀) 선택 필드 — 있으면 그 지점, 없으면 구역 중심. BE는 구역 스냅 없음(자유 좌표, 도달 불가 goal은 Nav2가 거부→FAILED) | /api/carts/{cartId}/navigation | POST | |
| NAV-02 | 목적지 이동 취소 | 진행 중 이동 취소·정지 | /api/carts/{cartId}/navigation | DELETE | |
| FOLLOW-01 | 사서 추종 일시정지 | | /api/carts/{cartId}/follow/pause | POST | 202 {"followId":1,"status":"PAUSED"} |
| FOLLOW-02 | 사서 추종 종료 | | /api/carts/{cartId}/follow | DELETE | |
| FOLLOW-03 | 사서 추종 대상 선택 | 영상에서 클릭한 사람(트랙 ID)을 추종 대상으로 지정. BE가 MQTT cmd/move/cart로 SELECT_TARGET 전달 | /api/carts/{cartId}/follow/target | POST | {"trackId":3} → 202 {"trackId":3,"status":"SENT"} |
| FOLLOW-04 | 사서 추종 시작 | | /api/carts/{cartId}/follow | POST | |

## FE-BE WebSocket

### 연결 정보
| 연결 주소 | 연결 주체 | 연결 시점 | 연결 종료 | 메시지 형식 | 방향 |
|---|---|---|---|---|---|
| /ws/carts/{cartId} | FE | 카트 관리 화면 진입 | 로그아웃/앱 종료 | JSON | BE→FE |
| /ws/carts/{cartId}/video | FE (시청) | 추종 대상 선택 모달 열 때 | 모달 닫을 때 | Binary (JPEG, 1메시지=1프레임) | BE→FE |
| /ws/carts/{cartId}/video/publish | 카트 (Jetson fe_bridge) | fe_bridge:=true launch 시 | launch 종료 시 | Binary (JPEG) | 카트→BE |

### 이벤트 13종
| ID | 이벤트 타입 | 설명 | 발생 조건 |
|---|---|---|---|
| WS-FE-01 | CART_POSITION_UPDATE | 카트 위치 변경 | SLAM 위치 갱신 |
| WS-FE-02 | CART_STATUS_UPDATED | 카트 상태 변경 | 동작 상태 변경 |
| WS-FE-03 | CART_CONNECTION_UPDATED | 카트 연결 상태 변경 | MQTT 연결·해제/Heartbeat 초과 |
| WS-FE-04 | SLOT_UPDATED | 슬롯 책 유무·도서 정보·오류·현재 구역 대상 여부 | 책 삽입·제거, RFID 결과, 대상 상태 변경 |
| WS-FE-05 | CURRENT_ZONE_UPDATED | 현재 책장 구역 변경 | 구역 진입/이탈 |
| WS-FE-06 | NAVIGATION_STATUS_UPDATED | 목적지 이동 진행 상태 | 접수·시작·정지·도착·취소·실패 |
| WS-FE-07 | FOLLOW_STATUS_UPDATED | 추종 준비·시작·대상 상실·종료 | 추종 상태 변경 |
| WS-FE-08 | TRACKS_UPDATED | 영상 위 사람 후보 박스 (WebRTC 대신 WS 영상(JPEG)+MQTT 트랙 중계로 구현) | AI가 status/target 5Hz 발행 + 영상 시청자 있을 때만 중계 |
| WS-FE-09 | CURRENT_ZONE_TASKS_UPDATED | 현재 구역에서 꺼낼 도서·슬롯 | 구역 진입, 적재·제거, 작업 상태 변경 |
| WS-FE-10 | TASK_PROGRESS_UPDATED | 전체·구역별 정리 진행률 | 적재·제거·정리 완료 |
| WS-FE-11 | RFID_RESCAN_COMPLETED | RFID 재인식 최종 결과 | 재인식 결과 확정 |
| WS-FE-12 | ALERT_OCCURRED | 안전·센서·통신 경고 | 사용자 확인 필요 문제 발생 |
| WS-FE-13 | ALERT_RESOLVED | 경고 해제 | 원인 해소 |

## EM-BE MQTT (토픽 prefix: carts/{cartId}/)
| ID | 이름 | Topic | 종류 | 방향 | 데이터 |
|---|---|---|---|---|---|
| MQTT-01 | 카트 위치 전송 | status/position | TELEMETRY | Jetson→BE | {"x","y","timestamp"} — SLAM 미터. BE가 아핀 계수(library_maps)로 평면도 픽셀 변환 후 구역 판정·WS 중계 |
| MQTT-02 | 카트 상태 변경 | status/cart | STATUS | Rasp→BE | 카트 상태, 변경 사유 |
| MQTT-03 | 슬롯 상태 변경 | status/slot | EVENT | Rasp→BE | {book, id, isTarget, lastDetectedAt, slotNumber, status} |
| MQTT-04 | 카트 하행 이동 | cmd/move/cart | EVENT | BE→Jetson | MOVE: {"requestId","command":"MOVE","zoneId","target":{x,y}(SLAM 미터),"pixel":{x,y}(지도 픽셀)} / CANCEL: {"requestId","command":"CANCEL"} / SELECT_TARGET: {"command":"SELECT_TARGET","trackId":3} / FOLLOW: {"requestId","command":"FOLLOW_START|FOLLOW_PAUSE|FOLLOW_STOP"} — 추종은 좌표 없음 (사서 좌표는 로봇 내부 /target_position이 연속 발행) |
| MQTT-05 | 추종 후보 트랙 전송 | status/target | TELEMETRY | Jetson→BE | {image_width, image_height, tracks} 5Hz. BE가 WS TRACKS_UPDATED로 중계 |
| MQTT-06 | 슬롯 상태 확인 요청 | cmd/check/slot | EVENT | BE→Rasp | |
| MQTT-07 | LED 점등 요청 | cmd/lit/led | EVENT | BE→Rasp | |
| MQTT-08 | 카트 이동 상태 | status/nav-result | STATUS | EM→BE | {"status":"IDLE|NAVIGATING|SUCCEEDED|ABORTED|CANCELED|REJECTED|NAV2_UNAVAILABLE"} — EM SLAM Nav가 /cart/nav_status(7종)를 MQTT 중계. BE가 NAVIGATION_STATUS_UPDATED로 변환 (2026-08-07 합의, BE 수신부 구현 완료) |

## AI-EM ROS2 토픽
| ID | Topic | 타입 | 설명 | Publisher | Subscriber | 상태 |
|---|---|---|---|---|---|---|
| ROS2-01 | /camera/image_raw | sensor_msgs/Image | 카메라 원본 영상 | camera_node | detector_node, reid_node, debug_visualization_node | 완료/완료 |
| ROS2-02 | /person_detection | vision_msgs/Detection2DArray | YOLO 사람 탐지 | detector_node | tracker_node | 완료/완료 |
| ROS2-03 | /person_tracks | vision_msgs/Detection2DArray | ByteTrack 추적 (track ID) | tracker_node | reid_node, debug_visualization_node | 완료/완료 |
| ROS2-04 | /select_target | std_msgs/Int32 | 추종 대상 수동 지정 | fe_bridge_node, 수동 CLI | reid_node | 완료/완료 |
| ROS2-05 | /target_person | vision_msgs/Detection2DArray | Re-ID 확정 추종 타겟 | reid_node | target_position_node, control_node, debug_visualization_node | 완료/완료 |
| ROS2-06 | /reid/recovery_event | std_msgs/String | Re-ID 재탐색 이벤트 | reid_node | debug_visualization_node | 완료/완료 |
| ROS2-07 | /scan | sensor_msgs/LaserScan | LiDAR 스캔 (구독 시 BEST_EFFORT QoS 필수) | ydlidar 드라이버 | control_node, target_position_node | 완료/완료 |
| ROS2-08 | /robot_pose | geometry_msgs/PoseStamped (frame=map) | 카트 SLAM 포즈 (EM→AI) | EM SLAM — **미구현** | target_position_node | 진행 중/완료 |
| ROS2-09 | /target_position | geometry_msgs/PointStamped (frame=map) | 타겟 지도 좌표 — AI 최종 출력 (AI→EM) | target_position_node | EM SLAM Nav — **미구현** | 완료/시작 전 |
| ROS2-10 | /cmd_vel | geometry_msgs/Twist | 속도 명령 (레거시 경로 — **실제 시연에 사용**) | control_node | motor_node | 완료/완료 |
| ROS2-11 | /target_distance | std_msgs/Float32 | 타겟 거리 m (실패 시 NaN) | control_node | debug_visualization_node | 완료/완료 |
| ROS2-12 | /wheel_speed_cmd | std_msgs/Int32MultiArray | 바퀴 RPM 명령 3요소 | motor_node | STM32측 | 취소/시작 전 (실제는 stm_serial_bridge가 USB Serial로 대체) |
| ROS2-13 | /debug/image | sensor_msgs/Image | 디버그 시각화 영상 | debug_visualization_node | rqt/rviz | 완료 |
| ROS2-14 | /cart/target_pose | PoseStamped | BE/수동 목적지 명령 (MQTT MOVE 브릿지 입구) | mqtt_bridge | goal_forwarder | (system-fusion 구현) |
| ROS2-15 | /cart/cancel | std_msgs/String (data=requestId) | 주행 취소 (MQTT CANCEL 브릿지 입구) | mqtt_bridge | goal_forwarder | (system-fusion 구현) |
| ROS2-16 | /cart/nav_status | std_msgs/String | 주행 상태 7종 — FE NAVIGATION_STATUS의 원천, TRANSIENT_LOCAL 래치 발행 | goal_forwarder | mqtt_bridge | (system-fusion 구현) |
| ROS2-17 | /odom_rf2o | nav_msgs/Odometry | 휠 오도메트리 전 임시 (/odom 이름은 휠 odom용 예약) | rf2o | EKF | (system-fusion 구현) |
| ROS2-18 | /map | nav_msgs/OccupancyGrid | Nav2 지도 + BE 좌표 변환(SlamCoordinateConverter) 메타데이터 소스 | map_server | Nav2, BE | (system-fusion 구현) |

## 부속 메모 (노션 원문)

### /robot_pose에 각도가 이미 들어 있음
/robot_pose는 geometry_msgs/PoseStamped 타입 — orientation 쿼터니언이 방향을 항상 포함.
```
yaw(라디안) = 2 × atan2(orientation.z, orientation.w)
yaw(도) = yaw(라디안) × 180 / π
```
BE MQTT 페이로드({"x","y","timestamp"})가 각도를 안 담기로 돼 있었을 뿐. 액션 아이템: MQTT 페이로드를 {"x","y","yaw","timestamp"}로 확장 (yaw 단위는 팀 합의 — 도 단위 추천).

### 주행 상태 7종 (/cart/nav_status, ROS2-16)
| 상태 | 의미 | 발행 시점 |
|---|---|---|
| IDLE | 대기 | 노드 기동 직후, goal 없음 |
| NAVIGATING | 주행 중 | Nav2가 goal 수락 (선점 시 재발행) |
| SUCCEEDED | 도착 | 목표 도달 |
| ABORTED | 주행 실패 | 경로 생성 불가·리커버리 실패 |
| CANCELED | 취소됨 | /cart/cancel로 중단 성공 |
| REJECTED | 접수 거부 | Nav2가 goal 거부 (드묾) |
| NAV2_UNAVAILABLE | Nav2 꺼짐 | 액션 서버 부재 — 배선 자가진단용 |

래치(TRANSIENT_LOCAL) 발행 — 나중에 구독해도 마지막 상태 즉시 수신. FE 매핑: NAVIGATING→STARTED, SUCCEEDED→ARRIVED, ABORTED→FAILED (팀 합의).
