# CLAUDE.md — embedded/Lidar (Jetson Orin Nano SLAM/NAV 작업)

> Jetson Orin Nano에서 VS Code SSH 원격 + Claude Code로 작업할 때의 기준 컨텍스트.
> **사람용 셋업·검증 절차의 정본은 [README.md](README.md)** — 작업은 README의 STEP
> 순서를 따라가며, 각 단계 완료 시 README 체크리스트 기준으로 검증한다.
> 마지막 갱신: 2026-08-03 / 주요 결정이 바뀌면 이 파일도 갱신할 것.

## 0. 작업 원칙

- **한국어 고정**: 모든 대답을 한국어로 답장하시오.
- 해결책 설계 전에 기존 코드/문서(README, docs/ROS2_API.md, 각 패키지 README)가
  같은 문제를 어떻게 다루는지 먼저 확인 — 접근 방식을 새로 발명하지 말 것.
- 현재 요구사항을 충족하는 가장 단순한 구현 선택. 추측에 근거한 추상화·설정값·
  가정 계층 금지. **TODO-실측/미확정 값은 임의로 확정하지 말고 팀 확인 후 진행.**
- 동작하는 결과물 위에 기능을 하나씩 쌓을 것 — 동작하는 코드를 미완성 복잡도와
  맞바꾸지 말 것.
- 직접 구현/패키지 추가 전에 이미 설치된 의존성부터 확인.

## 1. 여기가 어디인가

- 프로젝트: **쫄래쫄래** (SSAFY C101) — 사서와 동행하며 구역별 도서 정리를 돕는
  자율주행 북카트. 핵심 기능: ①사서 추종(AI) ②RFID 슬롯 인식(RPi) ③구역 안내.
- 이 폴더 = **SLAM/NAV colcon 워크스페이스 루트** (여기서 `colcon build`).
  노트북(Ubuntu 22.04+Humble)에서 검증 완료된 것을 Jetson에 이식한 것.
- 구성: `src/choll_slam_bringup`(라이다+rf2o+slam_toolbox 설정/런치),
  `src/choll_nav`(cart_pose_publisher + goal_forwarder), `src/choll_nav2`
  (Nav2 파라미터·후진 제거 BT·런치), `src/choll_mqtt_bridge`(MQTT↔ROS2
  브릿지 — BE 브로커 연동, python3-paho-mqtt 필요). upstream 2종은
  setup_jetson.sh가 클론.
- 카트 3보드 분산 제어 중 **Jetson 담당**: AI 추종 연산 + LiDAR/SLAM/Nav2 처리.
  `/cmd_vel` → (예정) 시리얼 브릿지 → STM32 차동구동. RPi는 RFID/LED/MQTT.

## 2. Jetson 환경 특성 (노트북과 다른 점)

- JetPack 6.x = Ubuntu 22.04 arm64 + ROS2 Humble — 패키지 이름·명령은 노트북과 동일.
- **VS Code SSH 원격 작업**: RViz 같은 GUI는 SSH 터미널로 못 띄움 —
  Jetson에 모니터(7" HDMI LCD) 연결해 로컬 세션에서 실행하거나,
  같은 네트워크의 노트북에서 `ROS_DOMAIN_ID`를 맞추고 RViz만 원격 구동.
- 라이다 USB 전류 부족 가능 — 데이터 끊김/모터 정지 시 어댑터보드 **USB_PWR**에
  5V 보조 급전 (벅컨버터, 보조배터리는 리플 때문에 비권장).
- 전원 안전 (§공통): 배터리를 보드에 직결 절대 금지, Jetson은 PD 트리거
  케이블(15V/20V)로 급전. 극성 확인 후 통전.
- 현재 탑재체: **오링카**(RC카) — 모터는 `/cmd_vel`과 연결돼 있지 않으므로
  실주행이 아니라 "지도 품질 + goal→경로→cmd_vel 발행" 검증까지가 목표.

## 3. 지금 단계와 다음 작업

- 완료(노트북): 전체 빌드, /scan 11.4Hz, TF 트리, SLAM 매핑+지도 저장, choll_nav
  배선 검증(NAV2_UNAVAILABLE/NAVIGATING/ABORTED/취소), 커스텀 BT 동작 확인.
- **Jetson에서 할 일 (README STEP 순서)**: `setup_jetson.sh` → `colcon build` →
  라이다 단독(STEP A) → SLAM 스택(STEP B) → **오링카 저속 주행으로 재매핑**(STEP C,
  수평 고정·느리게·루프 클로저 — 노트북 지도는 품질 낮아 폐기) → 지도 저장 →
  Nav2 벤치 검증(STEP D, `bench:=true`, 넓은 공간에서).
- 이후: MQTT↔ROS2 브릿지(/robot_pose→position), STM32 시리얼 브릿지(구동 파트),
  카트 골조 장착 시 실측 TODO 반영.

## 4. 토픽 계약 (임의 변경 금지 — 정본: docs/ROS2_API.md)

| 토픽 | 타입 | 방향 | 비고 |
|---|---|---|---|
| `/robot_pose` | PoseStamped | 발행 10Hz | 명세 ROS2-08. frame=map, RELIABLE (BestEffort 금지) |
| `/target_position` | PointStamped | 구독 | 명세 ROS2-09 (AI 발행). 스로틀 적용 |
| `/cart/target_pose` | PoseStamped | 구독 | 단발 명령. frame_id 필수, 스로틀 없음 (제안 ROS2-14) |
| `/cart/cancel` / `/cart/nav_status` | String / String | 구독/발행(래치) | 제안 ROS2-15/16. cancel data=requestId(선택) |
| `/scan` | LaserScan | 발행 ~11Hz | 구독 측 **BestEffort** 필수 |
| `/odom_rf2o` | Odometry | 발행 10Hz | 임시. `/odom`은 휠 오도메트리 예약 |
| `/cmd_vel` | Twist | Nav2 발행 20Hz | ⚠ AI control_node와 발행 주체 충돌 — 동시 구동 금지 |

TF: `map→(slam_toolbox|AMCL 중 하나만)→odom→(rf2o)→base_link→(정적, z=0.20
TODO-실측)→laser_frame`. odom→base_link 발행자는 항상 하나. 카메라 장착 시
`base_link→camera_frame` 정적 TF 추가.

MQTT 연동(`choll_mqtt_bridge`, 정본: 패키지 README): 브로커
`your-server.example.com:1883`(CHANGE_ME/CHANGE_ME). `cmd/move/cart`의 MOVE→
`/cart/target_pose`, CANCEL→`/cart/cancel` 변환 + `/robot_pose`→
`status/position`(`{"x","y","yaw","timestamp"}`, BE 파서 실측 계약) 발행.
SELECT_TARGET은 AI `fe_bridge_node` 담당 — 이 브릿지에서 처리 금지.

## 5. 절대 규칙

- `src/ydlidar_ros2_driver`, `src/rf2o_laser_odometry`는 upstream — **직접 수정
  금지, 커밋 금지**(.gitignore 처리). 설정 변경은 항상 choll_* 쪽 yaml/launch에서.
- YDLIDAR X4 Pro: baud **128000**(115200 아님), 싱글채널(시리얼 회전속도 제어 불가).
- `bench:=true` 파라미터는 모터리스 검증 전용 — **실주행은 기본 nav2_params.yaml**.
- 후진 금지 설계: 커스텀 BT(navigate_to_pose_no_backup.xml)가 1차 방어 —
  BT/behavior 설정 변경 시 이 전제를 깨지 말 것.
- Git: 피처 브랜치(`em/feature/*`) 커밋·푸시·MR 생성까지만. develop/main 직접
  푸시·로컬 머지 금지. 커밋 `[type] subject` (≤50자, 명사형, 마침표 없음).
- 임시 산출물(build/ install/ log/ 지도 파일) 커밋 금지.

## 6. 검증 루틴 (모든 변경 후)

`colcon build` 통과 → `ruff check`(repo pyproject 기준) →
`pytest src/choll_nav/test/test_nav_logic.py`(31개, ROS 소싱 불필요) →
`ros2 topic hz /scan`(6~12Hz) → `ros2 run tf2_tools view_frames` → RViz 육안.
결과는 통과/실패 모두 `tests/TEST_LOG.md`에 원본 출력 포함 기록.
