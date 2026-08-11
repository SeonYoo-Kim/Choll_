# 쫄래쫄래 — 빌드·배포·실행 가이드 (SETUP)

각 구성 요소를 빌드·실행하고, 로컬에서 전체 사슬을 재현하는 방법을 정리한 문서입니다.
(개발 당시 제출용 포팅 매뉴얼의 공개판 — 서버 주소·계정은 placeholder로 표기)

**목차**

1. [시스템 구성 개요](#1-시스템-구성-개요)
2. [Backend](#2-backend)
3. [Frontend](#3-frontend)
4. [Jetson — AI (person_follow_robot)](#4-jetson--ai-person_follow_robot)
5. [Jetson — SLAM·Nav2 (embedded/Lidar)](#5-jetson--slamnav2-embeddedlidar)
6. [Jetson — Serial Bridge (ros2_ws)](#6-jetson--serial-bridge-ros2_ws)
7. [STM32 모터 제어](#7-stm32-모터-제어)
8. [라즈베리파이 RFID·LED](#8-라즈베리파이-rfidled)
9. [CI/CD](#9-cicd)
10. [하드웨어 없이 로컬 E2E 재현](#10-하드웨어-없이-로컬-e2e-재현)

---

## 1. 시스템 구성 개요

```
FE(웹, nginx:80) ←REST /api·WebSocket /ws→ BE(Spring Boot:8080) ←MQTT(mosquitto:1883)→ 카트
                                                                        │
        카트(하드웨어) = Jetson Orin Nano ─ USB Serial ─ STM32(모터)     │
                       + 라즈베리파이(RFID 슬롯 5개 + LED) ──────────────┘
```

| 구성 요소 | 위치 | 스택 | 실행 형태 |
|-----------|------|------|-----------|
| Frontend (사서용 웹) | 서버 | React 18 + TS + Vite → nginx | Docker `choll-web` (:80) |
| Backend (허브 서버) | 서버 | Java 21 + Spring Boot 4.1.0 | Docker `choll-backend` (:8080, 내부) |
| MySQL 8.4 | 서버 | Docker 컨테이너 | `choll-net` 네트워크 |
| MQTT 브로커 | 서버 | Eclipse Mosquitto | `choll-net` 네트워크 (:1883) |
| AI (인식·추종) | Jetson Orin Nano 8GB | ROS2 Humble + TensorRT | `~/Choll/ai` colcon 워크스페이스 |
| SLAM·Nav2 (자율주행) | Jetson | slam_toolbox + AMCL + Nav2 | `~/Choll/embedded/Lidar` colcon 워크스페이스 |
| Serial Bridge | Jetson | ROS2 Humble | `~/Choll/ros2_ws` colcon 워크스페이스 |
| 모터 제어 | STM32 NUCLEO-F446RE | STM32CubeIDE (C, HAL) | 펌웨어 플래시 |
| RFID·LED | Raspberry Pi | Python (venv) | systemd `cart.service` |

---

## 2. Backend

### 사용 제품 및 버전

| 항목 | 값 |
|------|-----|
| 언어 / JVM | Java 21 (Eclipse Temurin — Docker `eclipse-temurin:21-jdk`/`21-jre`) |
| 프레임워크 | Spring Boot 4.1.0 (Spring Data JPA, Spring Integration MQTT, WebSocket, springdoc-openapi) |
| 빌드 | Gradle 9.5.1 (Wrapper 포함 — `./gradlew`) |
| WAS | 내장 Tomcat, 포트 8080 |
| DB | MySQL 8.4 |
| 브로커 | Eclipse Mosquitto (MQTT, 계정 인증) |

### 환경 변수

설정 정본은 [backend/src/main/resources/application.properties](../backend/src/main/resources/application.properties)이며
모든 값은 환경 변수로 오버라이드됩니다. 기동 시 `./.env` 또는 `./backend/.env`를 자동으로 읽습니다 (저장소에 커밋하지 않음).

| 환경 변수 | 기본값 | 설명 |
|-----------|--------|------|
| `DB_URL` | `jdbc:mysql://localhost:3306/chollae?serverTimezone=Asia/Seoul&characterEncoding=UTF-8` | MySQL 접속 URL |
| `DB_USERNAME` / `DB_PASSWORD` | `root` / `CHANGE_ME` | DB 계정 |
| `MQTT_ENABLED` | `false` | MQTT 연동 on/off (REST만 확인할 땐 false) |
| `MQTT_BROKER_URL` | `tcp://localhost:1883` | 브로커 주소 (배포: `tcp://mosquitto:1883`) |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | (빈 값) | 브로커 계정 (인증 브로커면 필수) |
| `MQTT_POSITION_UNIT` | `pixels` | 카트 위치 좌표 단위. `meters`면 SLAM 미터→지도 픽셀 아핀 변환 수행 |
| `MQTT_MAP_ID` / `MQTT_CART_ID` | `2` / `1` | 좌표 변환용 지도 ID / 이벤트를 귀속할 카트 ID |
| `BOOK_IMPORT_ENABLED` / `BOOK_IMPORT_PATH` | `false` / (빈 값) | 도서 CSV 초기 적재 ([BOOK_DATA_IMPORT.md](../backend/BOOK_DATA_IMPORT.md)) |
| `CART_OFFLINE_TIMEOUT_SECONDS` | `15` | 하트비트 무신호 시 OFFLINE 전환 |
| `WS_POSITION_TEST_ENABLED` | `false` | FE 연결 확인용 가짜 위치 발행기 |

### 로컬 빌드·실행

```bash
# 0) 사전 준비: JDK 21, Docker

# 1) MySQL 8.4 기동
docker run -d --name chollae-mysql -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=CHANGE_ME -e MYSQL_DATABASE=chollae mysql:8.4

# 2) 스키마·시드 적재 — JPA ddl-auto=update로 스키마는 자동 생성되므로 시드만 순서대로
docker exec -i chollae-mysql mysql -uroot -pCHANGE_ME chollae < backend/src/main/resources/db/test-room-3zones.sql
docker exec -i chollae-mysql mysql -uroot -pCHANGE_ME chollae < backend/src/main/resources/db/test-room-bookshelves.sql
docker exec -i chollae-mysql mysql -uroot -pCHANGE_ME chollae < backend/src/main/resources/db/cart-slot-seed.sql
docker exec -i chollae-mysql mysql -uroot -pCHANGE_ME chollae < backend/src/main/resources/db/library-map-affine-initial.sql
# 도서 마스터 데이터는 공공데이터 CSV 적재 절차(BOOK_DATA_IMPORT.md) 참조

# 3) (MQTT 확인 시) mosquitto 기동 — REST만 확인하면 생략 (MQTT_ENABLED=false)
docker run -d --name mosquitto -p 1883:1883 eclipse-mosquitto

# 4) 저장소 루트 또는 backend/에 .env 작성 (최소 DB_PASSWORD)

# 5) 빌드·실행
cd backend
./gradlew bootRun            # 개발 실행
./gradlew bootJar -x test    # 패키징
./gradlew test               # 테스트 (브로커 없이 동작)
```

- 기동 확인: `http://localhost:8080/swagger-ui/index.html`
- 지도·구역·슬롯 시드가 없으면 위치 변환·구역 판정이 동작하지 않습니다.

---

## 3. Frontend

### 사용 제품 및 버전

Node.js ≥ 22, pnpm 10 (corepack), React 18 + TypeScript + Vite, TanStack Query 5 + Zustand 5,
Ant Design 5, SCSS + CSS Modules, axios + orval + MSW, Vitest + Playwright, 배포는 nginx 1.27.

### 환경 변수 (`frontend/.env.development` — 커밋됨, 비밀값 없음)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `VITE_ENABLE_MSW` | `false` | `true`면 BE 없이 화면만 확인 (API 모킹) |
| `VITE_API_BASE_URL` | (빈 값) | 비워두면 same-origin `/api` (dev proxy/nginx 중계) |
| `VITE_WS_URL` | (빈 값) | 비워두면 `ws://<현재 호스트>/ws/...` |
| `VITE_BE_ORIGIN` | `http://localhost:8080` | dev proxy가 중계할 BE 오리진 |

개인 오버라이드는 `.env.development.local`(git 미추적)에 작성합니다.

### 빌드·실행

```bash
cd frontend
pnpm install
pnpm dev            # http://localhost:5173
pnpm build          # tsc + 프로덕션 빌드 → dist/
pnpm lint / pnpm test / pnpm test:e2e
pnpm api:gen        # openapi.yaml → src/shared/api/generated
```

배포: [frontend/Dockerfile](../frontend/Dockerfile)이 빌드 후 nginx로 서빙,
[nginx.conf](../frontend/nginx.conf)가 `/api`→BE(REST), `/ws`→BE(WebSocket)로 리버스 프록시.

---

## 4. Jetson — AI (person_follow_robot)

| 항목 | 값 |
|------|-----|
| 하드웨어 | Jetson Orin Nano 8GB + USB RGB 카메라 + YDLIDAR X4Pro |
| OS / ROS | Ubuntu 22.04 (JetPack 6.2), ROS2 Humble — [install_ros2_humble.sh](../install_ros2_humble.sh) |
| AI 스택 | YOLOv10s (TensorRT `.engine`), ByteTrack, OSNet (torchreid) — 추론 전용 |

**모델 파일 (git 미포함)**: TensorRT 엔진은 디바이스 종속 — Jetson에서 yolov10s ONNX를
`trtexec`로 변환해 저장소 루트 `models/yolov10s.engine`에 배치. OSNet 가중치는 torchreid가 자동 다운로드.

```bash
# 빌드 (Jetson의 ~/Choll 기준)
cd ~/Choll/ai
colcon build --symlink-install
source install/setup.bash

# 실행 — 반드시 저장소 루트에서 (models/ 상대 경로)
cd ~/Choll
ros2 launch person_follow_robot follow_robot_launch.py
```

주요 launch 인자:

| 인자 | 기본값 | 설명 |
|------|--------|------|
| `auto_select` | `true` | 최근접 인물 자동 선택. `false`면 FE/CLI 선택 대기 |
| `legacy_control` | `true` | **true = AI PID가 `/cmd_vel` 직접 발행 (단순 추종 — 실제 시연 구성)**. false = motor_node 미기동, `/cmd_vel_legacy`로 격리 (Nav2에 바퀴 양보) |
| `fe_bridge` | `false` | FE 타겟 선택 브릿지 (영상·트랙 하행, SELECT_TARGET 상행) |
| `be_video_ws_url` | `ws://localhost:8080/ws/carts/1/video/publish` | BE 영상 릴레이 endpoint |
| `mqtt_host` 등 | `localhost` | 브로커 접속 정보 (fe_bridge용) |
| `threshold` | `0.70` | Re-ID 코사인 유사도 임계값 |

시연 구성 실행 예 (FE 화면 클릭으로 타겟 선택):

```bash
cd ~/Choll
ros2 launch person_follow_robot follow_robot_launch.py \
  fe_bridge:=true auto_select:=false \
  be_video_ws_url:=ws://<서버주소>:8080/ws/carts/1/video/publish \
  mqtt_host:=<서버주소> mqtt_username:=<계정> mqtt_password:=<비밀번호>
```

테스트:

```bash
pytest ai/test/                                   # 프레임워크 독립 로직 (ROS 불필요)
cd ai && colcon test --packages-select person_follow_robot
```

---

## 5. Jetson — SLAM·Nav2 (embedded/Lidar)

계획 아키텍처의 자율주행 스택입니다 (매핑·localization·경로계획·MQTT 브릿지).
실기 통합 결과와 한계는 [RETROSPECTIVE.md](RETROSPECTIVE.md)를 참조하세요.

```bash
cd ~/Choll/embedded/Lidar
colcon build --symlink-install
source install/setup.bash

# 1) 매핑 (지도 작성 — 1회)
ros2 launch choll_slam_bringup slam.launch.py     # slam_toolbox + EKF + LiDAR

# 2) localization + Nav2 (작성된 지도로 주행)
ros2 launch choll_nav2 localization.launch.py map:=<지도.yaml>
ros2 launch choll_nav2 nav.launch.py

# 3) BE 연동 인터페이스 (MQTT ↔ ROS2 브릿지 + goal 변환)
ros2 launch choll_nav interface.launch.py         # goal_forwarder + cart_pose_publisher
ros2 launch choll_mqtt_bridge bridge.launch.py    # cmd/move/cart ↔ /cart/target_pose 등
```

주의: Nav2(velocity_smoother)가 `/cmd_vel`을 소유하므로 AI 쪽은 `legacy_control:=false`로
실행해야 합니다 — 동시에 켜면 `/cmd_vel` 발행자가 둘이 되어 충돌합니다.

---

## 6. Jetson — Serial Bridge (ros2_ws)

`/cmd_vel`(Twist) → 차동구동 좌우 바퀴 각속도 → STM32 USB Serial 명령(`SET_WHEEL_VEL,<L>,<R>`) 중계,
STM STATUS 패킷(10Hz) → `/stm/*` 토픽 발행.

```bash
cd ~/Choll/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash

# 전제: STM32(NUCLEO-F446RE)가 USB 연결돼 /dev/ttyACM0 존재 (115200 8N1)
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.065}}"
```

- `/cmd_vel`이 끊기면 watchdog이 약 0.5초 후 정지 명령을 보냅니다 (STM 자체 Timeout과 별개).
- AI 전체 launch와 Serial Bridge 실기 테스트를 동시에 실행하지 마세요 (`/cmd_vel` 발행 충돌).

---

## 7. STM32 모터 제어

| 항목 | 값 |
|------|-----|
| 보드 | STM32 NUCLEO-F446RE |
| IDE | STM32CubeIDE (CubeMX 설정 정본: `.ioc`) |
| 통신 | USART2 (ST-LINK VCP), 115200 8N1 |
| 프로토콜 | [embedded/motor/docs/serial_protocol.md](../embedded/motor/docs/serial_protocol.md) (정본) |
| 소스 | `embedded/motor/stm32_workspace/` |

1. STM32CubeIDE에서 프로젝트 Import → `.ioc` 수정 없이 Build → ST-LINK로 플래시.
2. 검증: `embedded/motor/tools/motor_serial_test`(Python W/A/S/D 툴) 또는 Serial Bridge로 `/cmd_vel` 구동.

정지 상태 4단계: Operational(STOP/Timeout) / Latched Safe(B1 버튼) / Emergency(ESTOP) / Stall Fault(`RESET_STALL`로만 해제).

---

## 8. 라즈베리파이 RFID·LED

| 항목 | 값 |
|------|-----|
| 하드웨어 | Raspberry Pi + MFRC522 RFID 리더 5개(SPI, 슬롯 1~5) + WS281x LED 스트립 |
| 런타임 | Python 3 venv — `spidev`, `lgpio`, `paho-mqtt`, `rpi_ws281x` |
| 소스 | [embedded/rfid/main.py](../embedded/rfid/main.py) (RFID+LED+MQTT 통합) |
| MQTT 발행 | `status/slot`(DETECTED/REMOVED), `status/cart`(하트비트 5초 + LWT) |
| MQTT 구독 | `cmd/lit/led` — `{"slot_id":[1,3]}` 수신 시 해당 슬롯 빨강 깜빡임 (`[]`면 중지) |

브로커 주소·계정·슬롯↔GPIO 매핑은 `main.py` 상단 User Config 상수로 관리합니다 (배포 전 환경에 맞게 수정).

```bash
# systemd 자동 실행 (등록 절차: embedded/rfid/라즈베리파이 부팅 시 자동실행.md)
systemctl status cart
journalctl -u cart -f

# 수동 실행 (서비스와 GPIO 충돌 — 먼저 내릴 것)
sudo systemctl stop cart
~/cart/.venv/bin/python -u main.py
```

LED 의미: 초록 = 빈 슬롯, 빨강 = 책 있음, 빨강 깜빡임 = 현재 구역에서 꺼낼 책.

---

## 9. CI/CD

`main` 브랜치 머지 시 웹훅으로 Jenkins가 루트 [Jenkinsfile](../Jenkinsfile)을 실행합니다:

```
Backend Test → Build Images (choll-backend / choll-web) → Deploy (docker compose) → Cleanup
```

배포 특이사항:

1. `.env`는 저장소에 없음 — Jenkins Secret file 자격증명(`choll-app-env`)으로 주입.
2. 파이프라인이 `.env`의 CRLF·BOM을 `sed`로 제거 (Windows에서 만든 `.env`로 DB 인증이 실패한 사고 예방).
3. 외부 Docker 네트워크 `choll-net` 선행 생성 필요 — mosquitto·MySQL 컨테이너와 공유.
4. backend 컨테이너는 호스트 포트를 열지 않고 web(nginx :80)을 통해서만 노출.
5. CI 테스트는 `MQTT_ENABLED=false`로 브로커 없이 동작.

---

## 10. 하드웨어 없이 로컬 E2E 재현

카트 실물 없이 FE→BE→MQTT 왕복을 재현하는 개발 도구가 있습니다:

```bash
# 1) MySQL + mosquitto + BE + FE 로컬 기동 (2·3장)
# 2) 가짜 카트 — cmd/move/cart를 구독해 등속 이동하며 status/position 발행
python scripts/fake_jetson.py --broker localhost

# (시연 비상용이었던 수동 위치 발행기 — 사람이 좌표를 찍어 카트 위치를 대행)
python scripts/manual_position.py --broker localhost
```

지도 탭에서 목적지를 클릭하면 가짜 카트가 이동하고, 구역 진입 팝업·슬롯 LED 명령·정리 진행률까지
전체 사슬이 동작합니다. (FE만 확인하려면 `VITE_ENABLE_MSW=true`로 BE도 생략 가능)

## 부록 — 외부 데이터 출처

- 도서 마스터 데이터: 공공데이터포털 "서울특별시 동작구 도서관 보유도서 현황" CSV
  (https://www.data.go.kr/data/15038435/fileData.do — 파일 다운로드 방식, 키 불필요).
  적재 절차는 [backend/BOOK_DATA_IMPORT.md](../backend/BOOK_DATA_IMPORT.md).
- OSNet(Re-ID) 가중치: torchreid가 공개 저장소에서 자동 다운로드.
- 그 외 가입형(API 키 발급형) 외부 서비스는 사용하지 않습니다.
