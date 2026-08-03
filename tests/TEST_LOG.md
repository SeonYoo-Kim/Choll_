# Test Log

파트 공통 테스트 실행 기록입니다. **에이전트든 사람이든, 테스트를 돌렸으면 결과를 여기에 남깁니다.**
목적: "테스트 통과했다"는 말을 사람이 눈으로 검증할 수 있게 하는 것.

> **AI 파트 기록은 [ai/test/TEST_LOG.md](../ai/test/TEST_LOG.md)로 이동했습니다.** 여기에는 FE/BE/EM 및
> 여러 파트에 걸친 검증 기록을 남깁니다.

## 기록 규칙

- **최신 항목이 맨 위** (이 문단 바로 아래에 추가).
- 항목 형식: `## 날짜 시각 — 결과 요약 (실행자)` + 환경·명령·커밋 + 접힌 전체 출력(`<details>`).
- **실패도 기록한다.** 실패 → 수정 → 재실행이면 두 번 다 남겨서 이력이 보이게 한다.
- 원본 출력은 `<details>` 블록에 그대로 붙인다 (요약만 믿지 말고 검증 가능하게).

---

## 2026-08-03 16:05 — ✅ main 승격 리허설: 로컬 가상 머지 + Jenkins Test 단계 재현 통과 (Claude)

- **목적**: develop(+슬롯 LED 브랜치)을 main에 머지·배포했을 때 파이프라인이 깨지는지 사전 확인
- **방법**: 임시 worktree에서 `origin/main`(c9b54d6) ← `backend/feature/slot-led-command`(d7d795f,
  develop 1fb0dba 포함) 가상 머지 → Jenkinsfile Backend Test 단계와 동일 조건으로 테스트
  (`MQTT_ENABLED=false`, `WS_POSITION_TEST_ENABLED=false`, DB 자격증명만 주입)
- **결과**:
  - 가상 머지: **충돌 없음 (clean merge)**
  - BE: `gradlew test` BUILD SUCCESSFUL — **22 suites, 66 tests, 0 failures** (contextLoads 포함)
  - AI: `pytest ai/test/` **114 passed**
  - FE: main 대비 `frontend/` **변경 0** — 지난 성공 배포와 동일 소스로 이미지 빌드
  - 이미지 빌드 단계(docker build)는 로컬에 docker가 없어 미검증 — BE는 컴파일 검증됨, FE는 무변경이라 잔여 위험 낮음
- **⚠️ 파이프라인은 통과해도, 배포 직후 카트 연동이 끊긴다 (코드가 아니라 운영 이슈)**:
  1. **RPi 실카트가 아직 옛 토픽 발행** (`choll/cart/rfid`, `carts/status`) — 새 BE는 `status/slot`·
     `status/cart` 구독이라 하트비트 15초 뒤 카트 OFFLINE, RFID 이벤트 유실. **RPi 반영과 동시 배포 필수.**
  2. **Jenkins 시크릿 `choll-app-env`가 compose `env_file`로 통째 주입됨** — 그 안에
     `MQTT_POSITION_TOPIC=carts/+/telemetry/position` 같은 옛 값이 남아 있으면 새 코드 기본값을
     **덮어써서 토픽 개편이 서버에서 무효화**된다 (과거 MQTT_POSITION_TEST.md가 .env에 넣도록 안내했었음).
     → main 머지 전 시크릿 파일에서 `MQTT_*_TOPIC` 라인 제거 또는 신값 갱신 필수.
  3. Jetson도 pull + colcon 재빌드 전까지 옛 `choll/cart/tracks` 발행 → TRACKS_UPDATED·타겟 선택 단절.
- **배포 후 확인 절차**: 405 프로브 + `mosquitto_sub -t 'status/#' -v`(EC2 브로커)로 신토픽 수신 확인
- **[추기 16:20] 위 운영 리스크 3종 해소 확인** (사용자 확인, 2026-08-03):
  - ① ③: RPi·Jetson 모두 실기에서 신토픽 코드로 구동 중
  - ②: 배포용 시크릿 .env 내용 확인 — `MQTT_*_TOPIC` 핀 없음 (DB_*, MQTT_ENABLED/BROKER_URL/계정,
    WS_POSITION_TEST_ENABLED뿐) → 코드 기본값이 그대로 적용됨. **수정 불필요, main 머지 가능 상태.**
  - 남은 조건부 1건: EM이 SLAM 미터 좌표 발행을 시작하면 `MQTT_POSITION_UNIT=meters` 추가
    + `library_maps` id=2에 실제 map.yaml 값 입력 (그 전까지 기본 pixels가 맞음)

- **명령**: `backend/gradlew.bat -p backend test --console=plain`
- **환경**: Windows 11, OpenJDK 21, MySQL(EC2 Docker). 브로커 없이 단위 테스트만
- **커밋**: `1fb0dba`(develop, MR !58 머지 후) 기준 — 브랜치 `backend/feature/slot-led-command`
- **신규 기능**: 카트의 **구역이 바뀔 때** 그 구역에서 내려놓을 슬롯 번호를 MQTT `cmd/lit/led`로 발행.
  페이로드 `{"slot_id":[1,3,5]}` — 그 시점에 켜져 있어야 할 슬롯 전체 (카트 1대 가정, cartId 없음).
  **BE 범위는 발행까지** — 구독·점등 제어는 라즈베리파이(EM) 몫
  - `SlotLedService` 신규 — 대상 조회 + 발행. MQTT 비활성이면 경고 후 무시
  - `SlotService.findTargetSlotNumbers()` 신규 — 기존 `isTarget`(책의 서가 구역 == 카트 현재 구역) 재사용
  - `CartPositionTelemetryService`에 **구역 전이 감지**(`zoneChanged`) 추가 — 갱신 전
    `cart.getCurrentZone()`과 비교. 같은 구역 유지면 발행하지 않음
  - `MqttCommandPublisher.publishLed()` 추가 — 토픽별 발행을 `publishTo(topic, payload)`로 분리
    (기존 `publish()` 호출처 NavigationService·FollowTargetService는 무영향)
  - 설정: `mqtt.led-topic`(기본 `cmd/lit/led`)
- **발행 규칙** (2026-08-03 협의):
  - 구역 진입/구역 간 이동 → 새 구역의 대상 목록 발행
  - **구역 이탈 → 빈 목록 `[]` 발행(소등)** — 책을 남기고 나가도 LED가 켜진 채 남지 않도록
  - 구역 밖 → 대상 없는 구역: 켤 것도 끌 것도 없어 미발행
  - 책이 빠졌을 때(RFID REMOVED)의 소등은 라즈베리파이 몫 — BE는 재발행하지 않음
- **결과**: 22 suites, **66 tests, 0 failures, 0 errors** (신규 7: SlotLedServiceTest 4 —
  점등/이탈 시 빈 목록/미발행/MQTT 비활성, CartPositionTelemetryServiceTest 3 — 진입/동일 구역 유지/이탈)
- **슬롯 번호 범위**: DB는 1~12번이지만 실물 RFID 리더는 5개만 설치(재정상). RFID 없는 슬롯은
  책이 인식되지 않아 `isTarget`이 될 수 없으므로 `slot_id`에도 나오지 않는다 — 불일치 아님
- **미검증**: 브로커 실연동 미실시. 라즈베리파이 구독·점등부는 EM 담당

<details>
<summary>gradle test 출력 + JUnit XML 집계</summary>

```
BUILD SUCCESSFUL
```

```
# build/test-results/test/*.xml 집계
tests=66 failures=0 errors=0 suites=22
```

</details>

## 2026-08-03 14:52 — ✅ MQTT 토픽 개편, develop 리베이스 후 BE 59 tests 통과 (Claude)

- **명령**: `backend/gradlew.bat -p backend test --console=plain`
- **환경**: Windows 11, OpenJDK 21, MySQL(EC2 Docker). 브로커 없이 단위 테스트만
- **커밋**: `d6ab80c`(develop) 위로 리베이스 — 브랜치 `refactor/mqtt-topic-rename`
  (SLAM 미터→픽셀 변환이 먼저 develop에 머지돼 `application.properties`·`backend/CLAUDE.md`·
  이 로그에서 충돌 → 양쪽 다 살려 해결. `mqtt.position-unit`·`mqtt.map-id`는 그대로 두고
  토픽 값만 교체)
- **변경**: MQTT 토픽 전면 개편 (`ai/`·`backend/` 양쪽 동시 적용).
  네이밍 규칙 = **상행(카트·AI→BE) `status/*`, 하행(BE→카트) `cmd/*`** (선행 슬래시 없음)

  | 구 토픽 | 신 토픽 | 방향 |
  |---------|---------|------|
  | `carts/{cartId}/telemetry/position` | `status/position` | 카트→BE |
  | `carts/status` | `status/cart` | 카트→BE (하트비트) |
  | `choll/cart/rfid` | `status/slot` | 카트→BE |
  | `choll/cart/cmd` | `cmd/move/cart` | BE→카트 (MOVE/CANCEL/SELECT_TARGET) |
  | `choll/cart/tracks` | `status/target` | AI→BE (추종 후보 트랙) |

- **구조 변경(주의)**: 새 위치 토픽에 cartId가 없어, `MqttPositionMessageHandler`가
  토픽 정규식(`^carts/(\d+)/telemetry/position$`)에서 cartId를 뽑던 방식을 폐기하고
  하트비트·RFID·tracks와 동일하게 `mqtt.cart-id`(기본 1)로 귀속하도록 변경.
  토픽 검증은 주입된 `mqtt.position-topic`과 정확 비교. **이제 수신 4종 모두 cartId가
  토픽에 없으므로 다중 카트 도입 시 EM과 재협의 필요.**
- **결과**: 21 suites, **59 tests, 0 failures, 0 errors**
  (내 변경으로 늘어난 테스트는 없음 — 토픽 상수만 갱신. 59는 develop의 SLAM 변환 테스트 4개 포함)
- **적용 범위**: `ai/`·`backend/`와 공용 E2E 도구(`tests/tools/fake_jetson.py`의 트랙 발행).
  FE(`frontend/`)·`docs/`에는 MQTT 토픽 문자열이 없어 변경 없음.
  **EM 파트(`embedded/`)는 이 MR에서 제외** — 실카트 코드는 EM 담당자가 별도 반영 예정.
  TEST_LOG의 과거 기록은 실행 증거라 옛 토픽명 그대로 보존.
- **미검증 / ⚠️ 배포 시 주의**: 브로커 실연동 E2E는 돌리지 않음 (단위 테스트만).
  - **EM 반영 전까지 실카트↔BE 통신 단절** — `embedded/rfid/rfid_mqtt.py`가 아직 옛 토픽
    (`choll/cart/rfid`, `carts/status`)으로 발행하므로, BE만 먼저 배포하면 슬롯·하트비트를 못 받는다.
    **BE 배포와 EM 반영은 함께 나가야 한다.**
  - EC2 브로커에 남은 옛 `carts/status` retained LWT도 새 `status/cart`로 자동 이관되지 않음.
- **AI 파트 기록**: [ai/test/TEST_LOG.md](../ai/test/TEST_LOG.md) 2026-08-03 항목

<details>
<summary>gradle test 출력 (마지막 부분) + JUnit XML 집계</summary>

```
BUILD SUCCESSFUL in 19s
```

```
# build/test-results/test/*.xml 집계
tests=59 failures=0 errors=0 suites=21
```

</details>

## 2026-08-03 — ✅ EM+ROS2 실기: STM32 STATUS → Serial Bridge → ROS2 수신 확인 + 좌우 매핑 실측 확정 (relu, 실기)

- **대상 커밋**: `d6bbe29` "[feat] STM STATUS 수신 및 ROS2 상태 토픽 발행" (`em/feature/motor-control`)
- **대상 코드**: `ros2_ws/src/stm_serial_bridge` (STM32 펌웨어는 변경 없음, UART Protocol v1 그대로)
- **환경**: Ubuntu + ROS2 Humble, 실제 STM32 USB Serial 연결, `serial_port=/dev/ttyACM0`, `baud_rate=115200`
- **⚠️ 바퀴를 공중에 띄운 상태에서 진행 — 바닥 주행 아님**
- **`/cmd_vel` 발행 수단**: `ros2 topic pub` (`teleop_twist_keyboard` 미사용 — 키보드 teleop은 여전히 미완료 항목)
- **Bridge 파라미터**: `dry_run=false`, `rx_poll_hz=50.0`, `status_timeout_sec=0.5`,
  `max_wheel_rad_s=2.0`, `tx_rate_hz=20.0`, `cmd_vel_timeout_sec=0.5`,
  `wheel_radius_m=0.065`, `wheel_separation_m=0.30`
- **실행자**: relu (사람이 직접 실기 수행). 이 항목은 사용자 보고를 받아 Claude가 대신 기록함.

### 결과: 수신 경로(STM32 → Bridge → ROS2) 실기 연동 완료

| # | 확인 항목 | 결과 |
|---|---|---|
| 1 | STM STATUS 패킷이 USB Serial로 Bridge에 수신 | ✅ |
| 2 | Bridge 로그의 `STATUS #N` 번호가 계속 증가 | ✅ |
| 3 | `STM → SerialLink → LineDecoder → parse_packet() → Publisher` 전 구간 동작 | ✅ |
| 4 | `/stm/connected` = `true` | ✅ |
| 5 | connected가 **포트 open이 아니라 유효 STATUS 수신** 기준임을 확인 | ✅ |
| 6 | `/stm/fault` 초기값 = `NONE` | ✅ |
| 7 | STATUS 주기 (`ros2 topic hz /stm/wheel_actual_rad_s`) | ✅ **약 9.995~9.999 Hz** |
| 8 | 펌웨어 STATUS 10Hz 설정과 일치 | ✅ |
| 9 | `in_waiting` 기반 `read_available()`이 실제 `/dev/ttyACM0`에서 동작 | ✅ |
| 10 | `/stm/encoder_total`로 양쪽 누적값 수신 | ✅ |
| 11 | `/stm/wheel_actual_rad_s`로 양쪽 실제 속도 수신 | ✅ |
| 12 | `ros2 topic pub --once` 후 약 0.5초에 watchdog 자동 정지(`0.000,0.000`) | ✅ |
| 13 | 송신 경로(ROS2 → STM) 재확인 | ✅ |

7번은 PTY에서만 확인됐던 `in_waiting` 폴링이 실제 USB CDC 드라이버에서도 정상 동작함을
보여준다 — 이전 기록에서 "실기에서 확인 필요"로 남겨둔 위험이 해소됐다.

### ★ 좌우 매핑 실측 확정

그동안 "코드 주석 기준이며 실측 미확정"으로 남아 있던 항목이 이번에 확정됐다.

```
물리 왼쪽  바퀴 ↔ STM 논리 Left  ↔ /stm/encoder_total[0] ↔ /stm/wheel_actual_rad_s[0]
물리 오른쪽 바퀴 ↔ STM 논리 Right ↔ /stm/encoder_total[1] ↔ /stm/wheel_actual_rad_s[1]
```

| 조작 | 관측 |
|---|---|
| 물리 왼쪽 바퀴를 돌림 | `encoder_total[0]`만 변화 |
| 물리 오른쪽 바퀴를 돌림 | `encoder_total[1]`만 변화 |
| `SET_WHEEL_VEL,2.000,0.000` (`linear.x=0.065, angular.z=-0.433333`) | 물리 왼쪽만 회전, `encoder_total[0]`만 변화 |
| `SET_WHEEL_VEL,0.000,2.000` (`linear.x=0.065, angular.z=+0.433333`) | 물리 오른쪽만 회전, `encoder_total[1]`만 변화 |
| 왼쪽만 전진 | `wheel_actual_rad_s` = `[양수, 0 근처]` |
| 오른쪽만 전진 | `[0 근처, 양수]` |
| 왼쪽만 후진 | `[음수, 0 근처]` |
| 오른쪽만 후진 | `[0 근처, 음수]` |

→ **PWM 출력 채널과 엔코더 입력 채널의 좌우 짝이 정상**이다. 이전에 우려했던
"엔코더만 교차되어 Left PI가 오른쪽 실측값을 오차 입력으로 쓰는" 상태가 **아님**을 확인했다.
전진 양수 / 후진 음수 부호도 좌우 모두 정상.

### 실기 중 발견하고 해결한 사항 (하드웨어)

- SSAFY로 장비를 이동하는 과정에서 일부 배선이 빠져 있었다.
- 초기에는 왼쪽 모터 또는 왼쪽 엔코더가 동작하지 않는 현상이 나타났다.
- 배선을 재확인·재연결한 뒤 재시험하여 양쪽 모터 구동, 양쪽 엔코더 값, 좌우 매핑 모두 정상 확인.
- **코드 결함이 아니라 이동 과정의 하드웨어 배선 문제였다.**

### 아직 검증하지 않은 것

1. STATUS 중단 후 `/stm/connected=false` 전환 및 재연결 복귀
2. USB 강제 분리 시 RX fatal error 처리(종료 코드 1, TX/RX 타이머 취소)
3. 실제 Stall 발생과 `/stm/fault` 전이(`STALL_LEFT`/`STALL_RIGHT`/`STALL_BOTH`)
4. `FAULT_CLEARED,STALL` 수신
5. `RESET_STALL` 송신 (브리지 미구현)
6. 엔코더 1회전당 정확한 카운트 수 및 `MOTOR_ENCODER_QUADRATURE_MULTIPLIER`(현재 4.0f) 검증
7. 실제 바닥 주행
8. `wheel_separation_m=0.30` 실측 확정 (여전히 플레이스홀더)
9. STATUS 수신이 끊겼을 때 주행 명령을 강제로 0으로 만드는 추가 안전 정책

### ⚠️ 이 기록의 한계

이 저장소 규칙은 원본 출력을 `<details>`로 남겨 검증 가능하게 하는 것인데, 이번 실기도
**콘솔 원본 출력이 확보되지 않았다.** 위 수치 중 근거가 있는 것은 사용자가 보고한
STATUS 주기(약 9.995~9.999Hz)뿐이며, 아래는 **관측되지 않았으므로 기록하지 않는다**:

- 각 토픽의 구체적 target/actual/pwm/encoder 수치
- watchdog 정지까지의 정확한 경과 시간(로그 타임스탬프 차)
- 손 회전 시 엔코더 카운트 절댓값(→ quadrature 배율 검증에 필요했던 값)
- 실행 호스트(Jetson / 개발 PC)

다음 실기에서는 노드 콘솔 출력(`STATUS #N ...`, `TX tx#N ...`, `watchdog state: ...`)을
`tee`로 파일에 남겨 함께 첨부할 것.

### 참고: 같은 커밋의 자동화 테스트 결과 (2026-08-03, Claude, PTY/단위 테스트)

실기와 별개로 하드웨어 없이 돌린 결과다.

- `colcon build --symlink-install` — 경고·에러 0
- `python3 -m pytest src/stm_serial_bridge/test/ -q` — **298 passed**
  (차동구동 9 + 프로토콜 10 + SerialLink 53 + watchdog 26 + limiter 28 + 패킷파서 96 +
  라인디코더 34 + RX 노드 42)
- PTY 통합: `master → read_available() → feed() → parse_packet() → Publisher` 경로 확인
- `connected` 경계값(정확히 `status_timeout_sec`)에서 false 전환, 비STATUS 패킷은
  timeout을 갱신하지 않음, `STALL_RESET,OK` 단독으로 fault가 NONE이 되지 않음 등 확인

## 2026-08-03 — ✅ BE 59 tests, SLAM 미터→이미지 픽셀 변환 추가 (Claude)

- **명령**: `backend/gradlew.bat test`
- **환경**: Windows 11, Microsoft OpenJDK 21.0.12, MySQL(EC2 Docker)
- **결과**: BUILD SUCCESSFUL, 59 tests, 0 failures (신규 4: SlamCoordinateConverterTest 3, 텔레메트리 meters 모드 1)
- **변경**: EM 협의(위치는 SLAM 미터로 발행, BE가 변환)에 따라 `SlamCoordinateConverter` 신설.
  `픽셀x=(x-originX)/resolution`, `픽셀y=height-(y-originY)/resolution` (ROS 규약 세로축 뒤집기).
  `mqtt.position-unit`(기본 pixels)·`mqtt.map-id`(기본 2)로 제어 — EM 발행 시작 시 meters 전환
- **활성화 전제**: `library_maps` id=2 행에 EM의 실제 map.yaml 값(resolution·origin)과
  FE가 쓰는 지도 이미지 크기가 정확히 들어가야 함

## 2026-08-02 — ✅ EM+ROS2 실기: `/cmd_vel` → Serial Bridge → STM32 → 모터 구동 확인 (relu, 실기)

- **대상 커밋**: `b4293b0` "[feat] ROS2 <-> STM serial Bridge 추가." (`em/feature/motor-control`)
- **대상 코드**: `ros2_ws/src/stm_serial_bridge` (STM32 펌웨어는 변경 없음, UART Protocol v1 그대로)
- **하드웨어**: STM32 NUCLEO-F446RE + BTS7960 + DC 모터 2개(엔코더), USB Serial(USART2/ST-LINK VCP, 115200 8N1)
- **실행자**: relu (사람이 직접 실기 수행). 이 항목은 사용자 보고를 받아 Claude가 대신 기록함.
- **`/cmd_vel` 발행 수단**: `ros2 topic pub` (`teleop_twist_keyboard`는 사용하지 않음 — 키보드
  teleop 실기는 여전히 미완료 항목)

### 결과: 송신 경로(ROS2 → Bridge → STM32 → Motor) 실기 연동 완료

| # | 확인 항목 | 결과 |
|---|---|---|
| 1 | ROS2 `/cmd_vel` 토픽 발행 | ✅ |
| 2 | `stm_serial_bridge` 노드의 `/cmd_vel` 수신 | ✅ |
| 3 | 차동구동 계산 → 좌우 바퀴 각속도 변환 | ✅ |
| 4 | `SET_WHEEL_VEL,<left_rad_s>,<right_rad_s>` USB Serial 전달 | ✅ |
| 5 | STM32가 명령 수신해 양쪽 모터 실제 구동 | ✅ |
| 6 | 전진 / 후진 | ✅ |
| 7 | 좌회전 / 우회전 | ✅ |
| 8 | `/cmd_vel` 중단 시 watchdog 자동 정지 (약 0.5초) | ✅ |
| 9 | ROS2 → Bridge → STM32 → Motor 전체 송신 경로 | ✅ |

8번은 Bridge의 `command_watchdog`이 `timed_out`으로 전환해 `SET_WHEEL_VEL,0.000,0.000`을
계속 내보내는 동작이다. STM32 자체의 Communication Timeout(`MOTION_CONTROLLER_COMM_TIMEOUT_MS`)과는
별개의 상위 안전장치이며, 이번 실기에서는 상위(Bridge) 쪽이 먼저 동작한 것으로 확인됐다.

### 아직 검증되지 않은 것 (STM → ROS2 수신 경로 전체)

1. STM32가 보내는 `STATUS` 패킷을 Bridge가 수신 — **미구현** (`serial_link.py`에 `read()` 없음)
2. `STATUS` 문자열 파싱 — 미구현
3. actual wheel velocity / PWM / encoder total의 ROS2 토픽 발행 — 미구현
4. 잘못된 패킷·수신 끊김 처리 — 미구현
5. STATUS 수신 경로 실기 테스트 — 미수행

### ⚠️ 이 기록의 한계 (검증 가능성 관련)

이 저장소의 기록 규칙은 "원본 출력을 `<details>`로 남겨 사람이 검증 가능하게" 하는 것인데,
이번 실기는 **콘솔 원본 출력이 확보되지 않았다.** 아래 항목도 미기록이다:

- 실행 호스트 (Jetson Orin Nano / 개발 PC 중 어디였는지)
- 실제 `serial_port` 값, `max_wheel_rad_s` 사용값, `tx_rate_hz`·`cmd_vel_timeout_sec` 값
- 바퀴 공중 상태였는지 지면 주행이었는지
- 좌우 회전 방향이 명령과 일치했는지에 대한 정량 근거
  (엔코더 좌우 매핑 `TIM2`=Left / `TIM8`=Right는 여전히 코드 주석 기준이며 실측 미확정)

따라서 이 항목은 **"동작을 확인했다"는 사람의 관찰 기록**이며, 재현 가능한 로그 근거는 없다.
다음 실기에서는 노드 콘솔 출력(`TX tx#N state=... command='...'`)과 사용 파라미터를 함께 남길 것.

### 참고: 같은 커밋의 자동화 테스트 결과 (2026-08-02, Claude, PTY/단위 테스트)

실기와 별개로 하드웨어 없이 돌린 결과다.

- `colcon build --symlink-install` — 경고·에러 0
- `python3 -m pytest src/stm_serial_bridge/test/ -q` — **112 passed**
  (차동구동 9 + 프로토콜 10 + SerialLink 39 + watchdog 26 + limiter 28)
- PTY(`pty.openpty()`) 통합: 54~57 프레임 전부 ASCII·CRLF 종단, 깨진/빈 프레임 0, 평균 20.00 Hz,
  `waiting(0,0)` → `active` → `timed_out(0,0)` 전이 확인
- `max_wheel_rad_s=2.0`에서 원본 `1.923/4.231` → `0.909/2.000` 비례 축소, 제한 전 프레임 PTY 송신 0건
- write 실패(PTY master close → `[Errno 5]`) 시 `Serial TX failed` 1회 + 0.22초 내 자동 종료, 종료 코드 1

## 2026-08-02 13:45 — ✅ BE 55 tests + FE 타겟 선택 릴레이 3종 E2E 통과 (Claude)

- **명령**: `backend/gradlew.bat test`, 이후 `bootRun`(8081, **MQTT_BROKER_URL=tcp://localhost:1883 강제**)
  + 가짜 Jetson(Python: mp4→JPEG WS 발행) + 가짜 FE(Node WS 리스너) + mosquitto_pub/sub + curl
- **환경**: Windows 11, OpenJDK 21.0.12, MySQL(AWS RDS), Mosquitto 로컬 브로커
- **브랜치**: `backend/feature/video-select-relay`
- **결과**: 18→**19 suites, 55 tests**, 0 failures (신규 7: MqttTracksMessageHandlerTest 4, FollowTargetServiceTest 3)
- **신규 기능 E2E**:
  - 영상 릴레이: `/ws/carts/1/video/publish`(발행) → `/ws/carts/1/video`(시청).
    98프레임/10초(9.7fps, ~40KB JPEG) 손실 0, 시청측 저장 JPEG 디코딩 정상(640×480)
  - 트랙 릴레이: MQTT `choll/cart/tracks` → WS `TRACKS_UPDATED` 페이로드 원형 그대로 수신
  - 타겟 선택: `POST /api/carts/1/follow/target {trackId:16}` → 202 `{SENT}` →
    MQTT `choll/cart/cmd {"command":"SELECT_TARGET","trackId":16}` 수신 확인
- **추가(14:00) 브라우저 시각 검증**: BE 정적 테스트 페이지
  `http://localhost:8081/target-select-test.html` (FE 참조 구현으로 커밋) +
  `tests/tools/fake_jetson.py`(result01.mp4→JPEG WS + 가짜 이동 트랙 MQTT 5Hz)로
  영상 렌더링(271프레임)·박스 실시간 갱신·**박스 클릭→202 SENT→MQTT SELECT_TARGET** 확인
- **트러블슈팅 2건** (재발 방지 기록):
  - `ServletServerContainerFactoryBean`이 테스트 mock 서블릿 컨텍스트에서 기동 실패
    → 세션별 `setBinaryMessageSizeLimit(1MB)`로 대체
  - **backend/.env의 MQTT_BROKER_URL이 EC2 브로커**라 로컬 pub/sub과 분리돼 침묵
    → E2E는 반드시 `MQTT_BROKER_URL=tcp://localhost:1883` 오버라이드로 실행할 것.
    EC2 브로커에는 실카트 LWT(retained carts/status)가 살아 있음 — 테스트 트래픽 금지

<details>
<summary>E2E 원본 출력 (가짜 FE 수신 로그·cmd 구독)</summary>

```text
# fake_jetson.py
connected: ws://localhost:8081/ws/carts/1/video/publish
sent 98 frames in 10.1s (~9.7 fps)

# fake_fe.mjs (발췌)
[video] frame #1 (38560 bytes) saved
[video] frame #80 (40644 bytes) saved
[events] {"type":"TRACKS_UPDATED","payload":{"image_width":640,"image_height":480,"tracks":[{"id":16,"x":220,"y":30,"w":180,"h":420},{"id":23,"x":20,"y":180,"w":60,"h":120}]}}
[video] total frames=98, last=39245 bytes

# mosquitto_sub -t choll/cart/cmd -v
choll/cart/cmd {"command":"SELECT_TARGET","trackId":16}

# REST 응답
{"trackId":16,"status":"SENT"}
```

</details>


## 2026-07-31 — ✅ BE 48 tests, MQTT 브로커 인증 설정 추가 후 통과 (Claude)

- **명령**: `backend/gradlew.bat test`
- **환경**: Windows 11, Microsoft OpenJDK 21.0.12, MySQL(AWS RDS)
- **결과**: BUILD SUCCESSFUL (18 suites, 48 tests, 0 failures)
- **변경**: EC2 Mosquitto가 인증 필수가 되어 `mqtt.username`/`mqtt.password` 설정 추가
  (빈 값이면 기존처럼 익명 접속 — 로컬 개발 영향 없음). CI/CD 파일 신규:
  `Jenkinsfile`, `backend/Dockerfile`, `frontend/Dockerfile`+`nginx.conf`, `infra/docker-compose.app.yml`

## 2026-07-31 — ✅ BE 48 tests + TaskProgress에 totalSlots 추가 검증 (Claude)

- **명령**: `backend/gradlew.bat test`, 이후 `bootRun`(8081) + `GET /api/carts/1/tasks/progress`
- **환경**: Windows 11, Microsoft OpenJDK 21.0.12, MySQL(AWS RDS)
- **결과**: 18 suites, 48 tests, 0 failures, 0 errors
- **변경**: 진행률 분모를 슬롯 개수로 쓰기로 한 팀 결정에 따라 `TaskProgress`에 `totalSlots`(카트 슬롯 수, DB 카운트) 추가.
  FE 계산식: `percent = (totalSlots - remainingBooks) / totalSlots` (빈 카트 100%, 6권 50%)
- **E2E**: `{"totalSlots":12,"totalBooks":27,"shelvedBooks":27,"remainingBooks":0,...}` — DB 슬롯 12개 반영 확인

## 2026-07-31 11:37 — ✅ BE 48 tests, 슬롯 30→12 축소 반영 후 전체 통과 (Claude)

- **명령**: `backend/gradlew.bat test`
- **환경**: Windows 11, Microsoft OpenJDK 21, MySQL(AWS RDS)
- **브랜치**: `develop` (ed719a8 이후 작업 트리, 커밋 전)
- **결과**: 18 suites, 48 tests, 0 failures, 0 errors
- **변경 범위**: 슬롯 개수 30→12 — `cart-slot-seed.sql`(12행 + 13번 이후 DELETE),
  `Slot.java` 체크 제약 `between 1 and 12`, `SlotService.Response` Swagger `maximum="12"`,
  `SlotServiceTests` 슬롯 번호 30→12, `CART_SLOT.md`·`bookDB.md` 문서 갱신
- ⚠️ 운영 DB의 기존 `slots_chk_1 CHECK (1~30)` 제약은 ddl-auto=update로 변경되지 않음 —
  시드 재실행으로 13~30번 행 삭제는 되지만, 제약 자체를 12로 조이려면 수동 ALTER 필요

<details>
<summary>gradlew test 원본 출력 (요약부)</summary>

```text
> Task :compileJava
> Task :processResources
> Task :classes
> Task :compileTestJava
> Task :testClasses
> Task :test

BUILD SUCCESSFUL in 19s
4 actionable tasks: 4 executed

# build/test-results/test/*.xml 집계
suites=18 tests=48 failures=0 errors=0
```

</details>

## 2026-07-30 17:40 — ✅ BE 48 tests + NAV 명령 하행·Task 진행률 E2E 통과 (Claude)

- **명령**: `backend/gradlew.bat test`, 이후 `bootRun`(8081) + REST 호출 + `mosquitto_sub -t "choll/cart/cmd"` + Node WS 리스너
- **환경**: Windows 11, Microsoft OpenJDK 21.0.12, MySQL(AWS RDS), Mosquitto 로컬 브로커
- **브랜치**: `develop` (109b1b7 이후 작업 트리, 커밋 전)
- **결과**: 18 suites, 48 tests, 0 failures, 0 errors (신규 9개: NavigationServiceTest 6, TaskServiceTests 3 추가)
- **검증 범위**:
  - NAV-01 `POST /navigation {zoneId:8}` → 202 `{navigationId:1, ACCEPTED}` + 카트 MOVING
    + MQTT `choll/cart/cmd {"requestId":1,"command":"MOVE","zoneId":8,"x":775.0,"y":505.0}` (Z7 bbox 중심)
    + WS `NAVIGATION_STATUS_UPDATED {ACCEPTED}`
  - 중복 시작 → 400, NAV-02 `DELETE` → 204 + 카트 IDLE + MQTT CANCEL + WS `{CANCELLED}`
  - SortingTask: RFID DETECTED → 작업 생성, REMOVED → 완료.
    진행률 `{total:1, shelved:0→1, remaining:1→0}` REST·WS(`TASK_PROGRESS_UPDATED`) 동시 확인 — shelvedBooks 하드코딩 0 해소
- **부수 검증**: FE 이벤트 이중 수신 제보 → 단일 리스너로 1회 수신 확인(BE 정상). 원인은 FE CartSocket의
  StrictMode 재연결 경합(소켓 2개 생존)으로 진단.

<details>
<summary>E2E: MQTT 명령 발행 + WS 수신 원본</summary>

```text
# mosquitto_sub -t "choll/cart/cmd" -v
choll/cart/cmd {"requestId":1,"command":"MOVE","zoneId":8,"x":775.0,"y":505.0}
choll/cart/cmd {"requestId":1,"command":"CANCEL","zoneId":8,"x":null,"y":null}

# WS 리스너 (/ws/carts/1)
MSG {"type":"NAVIGATION_STATUS_UPDATED","payload":{"navigationId":1,"status":"ACCEPTED","destinationZoneId":8,"failReason":null}}
MSG {"type":"NAVIGATION_STATUS_UPDATED","payload":{"navigationId":1,"status":"CANCELLED","destinationZoneId":8,"failReason":null}}
MSG {"type":"SLOT_UPDATED","payload":{"id":5,"slotNumber":5,"status":"OCCUPIED","isTarget":false,"book":{...,"title":"이불 여행",...}}}
MSG {"type":"TASK_PROGRESS_UPDATED","payload":{"totalBooks":1,"shelvedBooks":0,"remainingBooks":1,"currentZoneSlotNumbers":[]}}
MSG {"type":"SLOT_UPDATED","payload":{"id":5,"slotNumber":5,"status":"EMPTY","isTarget":false,"book":null,...}}
MSG {"type":"TASK_PROGRESS_UPDATED","payload":{"totalBooks":1,"shelvedBooks":1,"remainingBooks":0,"currentZoneSlotNumbers":[]}}

# REST: GET /tasks/progress
{"totalBooks":1,"shelvedBooks":0,"remainingBooks":1,"currentZoneSlotNumbers":[]}   (DETECTED 후)
{"totalBooks":1,"shelvedBooks":1,"remainingBooks":0,"currentZoneSlotNumbers":[]}   (REMOVED 후)
```

</details>

## 2026-07-30 14:20 — ✅ BE 39 tests + 하트비트 토픽 변경(carts/status) 검증 (Claude)

- **명령**: `backend/gradlew.bat test`, 이후 `bootRun`(8081) + `mosquitto_pub -t "carts/status" -m '{}'`
- **환경**: Windows 11, Microsoft OpenJDK 21.0.12, MySQL(AWS RDS), Mosquitto 로컬 브로커
- **브랜치**: `develop` (5aed143 이후 작업 트리, 커밋 전)
- **결과**: 17 suites, 39 tests, 0 failures, 0 errors
  (토픽에서 cartId 파싱이 사라져 `ignoresUnsupportedTopics` 테스트 1개 제거 → 40→39)
- **변경**: EM 협의로 하트비트 토픽 `carts/+/status` → `carts/status` (cartId 미포함).
  `mqtt.rfid-cart-id`를 공용 `mqtt.cart-id`로 통합 (하트비트·RFID 공용 귀속 설정)
- **E2E**: 기동 직후 `"online":false` → `carts/status` 빈 페이로드 1건 발행 → `"online":true` (REST 교차 확인)

## 2026-07-30 13:26 — ✅ BE 40 tests + 하트비트 ONLINE/OFFLINE E2E 통과 (Claude)

- **명령**: `backend/gradlew.bat test`, 이후 `bootRun`(포트 8081, MQTT_CLIENT_ID 분리) + `mosquitto_pub` + Node WS 리스너
- **환경**: Windows 11, Microsoft OpenJDK 21.0.12, MySQL(AWS RDS), Mosquitto 로컬 브로커
- **브랜치**: `backend/feature/mqtt-ws-bridge` (2f0b442 이후 작업 트리, 커밋 전)
- **결과**: 17 suites, 40 tests, 0 failures, 0 errors (신규 8개: CartConnectionServiceTest 5, MqttHeartbeatMessageHandlerTest 3)
- **검증 범위**:
  - `carts/1/status` 하트비트 수신 → OFFLINE 카트 ONLINE 전환 + WS `CART_CONNECTION_UPDATED {online:true}`
  - 무신호 15초(+워치독 5초 주기) → OFFLINE 전환 + WS `{online:false}` (13:05:00 수신 → 13:05:20 전환, 정확히 타임아웃+주기)
  - RFID 태깅도 생존 신호로 처리 (검증 중 실물 태깅에도 OFFLINE 전환되는 결함 발견 → markAlive 연결로 수정 후 재검증)
  - 위치 텔레메트리 markAlive 경유로 전환 이벤트 공유
- **주의**: 생존 판정이 페이로드 timestamp 기준 — 과거 timestamp를 보내면 즉시 OFFLINE 재전환됨(테스트 중 재현).
  카트 시계 동기화(NTP) 전제. 수신 시각 기준으로 바꿀지 EM과 논의 필요.

<details>
<summary>E2E: WS 수신 원본 (하트비트·워치독·RFID 생존신호)</summary>

```text
# 시나리오 1: 하트비트 → ONLINE, 무신호 20초 → OFFLINE (KST 13:05)
[2026-07-30T04:05:04.989Z] MSG {"type":"CART_CONNECTION_UPDATED","payload":{"online":true,"lastSeenAt":"2026-07-30T13:05:00"}}
[2026-07-30T04:05:20.000Z] MSG {"type":"CART_CONNECTION_UPDATED","payload":{"online":false,"lastSeenAt":"2026-07-30T13:05:00"}}
# (같은 구간에 실물 RFID 태깅 SLOT_UPDATED 다수 수신 — 태깅 중에도 OFFLINE 전환된 것이 결함 발견 계기)

# 시나리오 2 (markAlive 연결 후 재기동): RFID DETECTED만으로 ONLINE 전환
[2026-07-30T04:26:39.858Z] MSG {"type":"CART_CONNECTION_UPDATED","payload":{"online":true,"lastSeenAt":"2026-07-30T13:15:00"}}
[2026-07-30T04:26:39.885Z] MSG {"type":"SLOT_UPDATED","payload":{"id":5,"slotNumber":5,"status":"OCCUPIED",...}}
# 페이로드 timestamp(13:15)가 실제 시각(13:26)보다 과거라 워치독이 즉시 OFFLINE 재전환 — timestamp 기준 판정의 특성
[2026-07-30T04:26:41.703Z] MSG {"type":"CART_CONNECTION_UPDATED","payload":{"online":false,"lastSeenAt":"2026-07-30T13:15:00"}}
```

REST 교차 확인: 하트비트 후 `GET /api/carts/1` → `"online":true`, 무신호 후 → `"online":false`.

</details>

## 2026-07-30 12:11 — ✅ BE 32 tests + MQTT→WS 실연동(위치·RFID) E2E 통과 (Claude)

- **명령**: `backend/gradlew.bat test`, 이후 `bootRun`(MQTT_ENABLED=true) + `mosquitto_pub` 실발행 + Node WS 리스너
- **환경**: Windows 11, Microsoft OpenJDK 21.0.12, MySQL(AWS RDS), Mosquitto 로컬 브로커, Node v24
- **브랜치**: `develop` (f5584e2 기준 작업 트리, 커밋 전)
- **결과**: 15 suites, 32 tests, 0 failures, 0 errors (신규 11개: CartPositionTelemetryServiceTest 2,
  MqttRfidMessageHandlerTest 4, SlotRfidEventServiceTest 4, CartEventPublisherTest 1)
- **검증 범위**:
  - MQTT `carts/1/telemetry/position` 수신 → DB 갱신 + WS `CART_POSITION_UPDATE` 발행 (yaw는 EM 미송신으로 임시 0)
  - MQTT `choll/cart/rfid` DETECTED → uid `0437F306`(초록 눈 코끼리) book_copies 매칭 → 슬롯 1 OCCUPIED + WS `SLOT_UPDATED`
  - REMOVED → 슬롯 1 EMPTY 복구 + WS `SLOT_UPDATED` (테스트 후 시드 상태 원복 확인)
  - REST `GET /api/carts/1`, `GET /api/carts/1/slots/1` 로 DB 반영 교차 확인

<details>
<summary>Gradle 테스트 출력 + 스위트별 집계</summary>

```text
> Task :compileJava
> Task :processResources
> Task :classes
> Task :compileTestJava
> Task :processTestResources NO-SOURCE
> Task :testClasses
> Task :test

BUILD SUCCESSFUL in 36s
4 actionable tasks: 4 executed

com.ssafy.backend.BackendApplicationTests: tests=1 failures=0 errors=0 skipped=0
com.ssafy.backend.bookimport.BookCsvImportServiceTests: tests=1 failures=0 errors=0 skipped=0
com.ssafy.backend.booklocation.BookLocationServiceTests: tests=4 failures=0 errors=0 skipped=0
com.ssafy.backend.cart.CartServiceTests: tests=1 failures=0 errors=0 skipped=0
com.ssafy.backend.mqtt.position.CartPositionTelemetryServiceTest: tests=2 failures=0 errors=0 skipped=0
com.ssafy.backend.mqtt.position.MqttPositionMessageHandlerTest: tests=3 failures=0 errors=0 skipped=0
com.ssafy.backend.mqtt.position.PolygonZoneMatcherTest: tests=2 failures=0 errors=0 skipped=0
com.ssafy.backend.mqtt.position.RecentPositionBufferTest: tests=2 failures=0 errors=0 skipped=0
com.ssafy.backend.mqtt.position.StableZoneTrackerTest: tests=3 failures=0 errors=0 skipped=0
com.ssafy.backend.mqtt.rfid.MqttRfidMessageHandlerTest: tests=4 failures=0 errors=0 skipped=0
com.ssafy.backend.mqtt.rfid.SlotRfidEventServiceTest: tests=4 failures=0 errors=0 skipped=0
com.ssafy.backend.slot.SlotServiceTests: tests=2 failures=0 errors=0 skipped=0
com.ssafy.backend.task.TaskServiceTests: tests=1 failures=0 errors=0 skipped=0
com.ssafy.backend.websocket.CartEventPublisherTest: tests=1 failures=0 errors=0 skipped=0
com.ssafy.backend.websocket.PositionTestPublisherTest: tests=1 failures=0 errors=0 skipped=0
```

</details>

<details>
<summary>E2E: mosquitto_pub 발행 ↔ Node WS 리스너(/ws/carts/1) 수신 원본</summary>

발행 (mosquitto_pub -h localhost):

```text
-t "carts/1/telemetry/position" -m '{"x": 250.5, "y": 120.0, "timestamp": "2026-07-30T12:10:00.000+09:00"}'
-t "choll/cart/rfid" -m '{"slot_id": 1, "uid": "0437F306", "event": "DETECTED", "timestamp": "2026-07-30T12:10:01.000+09:00"}'
-t "choll/cart/rfid" -m '{"slot_id": 1, "uid": "0437F306", "event": "REMOVED", "timestamp": "2026-07-30T12:11:00.000+09:00"}'
```

WS 수신:

```text
[2026-07-30T03:08:09.152Z] OPEN
[2026-07-30T03:08:21.403Z] MSG {"type":"CART_POSITION_UPDATE","payload":{"mapId":2,"x":250.5,"y":120.0,"yaw":0,"valid":true}}
[2026-07-30T03:08:22.435Z] MSG {"type":"SLOT_UPDATED","payload":{"id":1,"slotNumber":1,"status":"OCCUPIED","isTarget":false,"book":{"id":143180,"bookId":112105,"title":"초록 눈 코끼리","author":"강정연 글;백대승 그림","callNumber":"아 813.8-강74ㅊ","rfidTagId":"0437F306","bookshelfId":9,"bookshelfNumber":"800","shelfZoneId":7,"zoneName":"오른쪽 중앙 존"},"lastDetectedAt":"2026-07-30T12:10:01"}}
[2026-07-30T03:09:04.499Z] MSG {"type":"SLOT_UPDATED","payload":{"id":1,"slotNumber":1,"status":"EMPTY","isTarget":false,"book":null,"lastDetectedAt":"2026-07-30T12:11:00"}}
```

REST 교차 확인: `GET /api/carts/1` → position 250.5/120.0, `GET /api/carts/1/slots/1` → OCCUPIED 후 EMPTY 복구.

</details>

## 2026-07-28 17:43 — ✅ BE 20 tests·Z1~Z7 시드 재실행 통과 (Codex)

- **명령**: `backend/gradlew.bat test`, `source backend/src/main/resources/db/test-room-bookshelves.sql`
- **환경**: Windows 11, Microsoft OpenJDK 21.0.11, MySQL 8.4
- **브랜치**: `backend/feature/rfid_zone_data`
- **결과**: 10 suites, 20 tests, 0 failures, 0 errors
- **검증 범위**: Z1~Z7 중복 없는 재구성, 책장 10개 존 배치, 소장 도서
  67,289권 책장 연결, 테스트 RFID 5개 보존, 백엔드 전체 테스트

<details>
<summary>백엔드 Gradle 테스트 최종 출력</summary>

```text
> Task :compileJava UP-TO-DATE
> Task :processResources
> Task :classes
> Task :compileTestJava UP-TO-DATE
> Task :processTestResources NO-SOURCE
> Task :testClasses UP-TO-DATE
> Task :test

BUILD SUCCESSFUL in 40s
4 actionable tasks: 2 executed, 2 up-to-date
```

</details>

## 2026-07-27 17:07 — ✅ BE 20 tests·UTF-8 전체 재컴파일 통과 (Codex)

- **명령**: `backend/gradlew.bat test --rerun-tasks`
- **환경**: Windows 11, Microsoft OpenJDK 21.0.11
- **브랜치**: `backend/feature/socket_test`
- **결과**: 10 suites, 20 tests, 0 failures, 0 errors
- **검증 범위**: UTF-8 Java 전체 재컴파일, MQTT 활성 상태 애플리케이션 기동,
  메시지 파싱, 카트별 최근 위치 20개 제한, 다각형 구역 판정, 동일 구역 3회
  연속 감지
- **참고**: 구현 중 Paho 의존성 누락으로 컴파일 실패 후 명시적 의존성을
  추가했고, Spring Boot 4의 Jackson 3에 맞게 import를 수정한 뒤 재검증했다.
  샌드박스에서 Gradle 배포 파일 다운로드가 차단된 실행은 기존 캐시를 사용할 수
  있는 환경에서 다시 실행했다.

<details>
<summary>백엔드 Gradle 테스트 최종 출력</summary>

```text
> Task :compileJava UP-TO-DATE
> Task :processResources UP-TO-DATE
> Task :classes UP-TO-DATE
> Task :compileTestJava
> Task :processTestResources NO-SOURCE
> Task :testClasses
> Task :test

BUILD SUCCESSFUL in 29s
4 actionable tasks: 4 executed

```

</details>

## 2026-07-27 15:50 — ✅ BE 10 tests·FE 6 tests·lint·format·build 통과 (Codex)

- **명령**: `backend/gradlew.bat test`, `pnpm test`, `pnpm lint`, `pnpm format:check`, `pnpm build`
- **환경**: Windows 11, Microsoft OpenJDK 21.0.11, pnpm 11.9.0
- **커밋**: `9c70421` ([chore] OpenAPI 프론트 클라이언트 재생성)
- **맥락**: 노션 기준 API 계약, 백엔드 DTO·컨트롤러, springdoc YAML, orval 생성 클라이언트의 최종 정합성 검증.

<details>
<summary>백엔드 Gradle 테스트 전체 출력</summary>

```text
> Task :compileJava UP-TO-DATE
> Task :processResources UP-TO-DATE
> Task :classes UP-TO-DATE
> Task :compileTestJava
> Task :processTestResources NO-SOURCE
> Task :testClasses
OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
> Task :test

BUILD SUCCESSFUL in 13s
4 actionable tasks: 2 executed, 2 up-to-date
```

Gradle XML 결과: 6 suites, 10 tests, 0 failures.

</details>

<details>
<summary>프론트 Vitest 전체 출력</summary>

```text
$ vitest run

 RUN  v4.1.10 C:/ssafy2_1/S15P11C101/frontend

 Test Files  2 passed (2)
      Tests  6 passed (6)
   Start at  15:49:28
   Duration  2.68s (transform 642ms, setup 1.54s, import 724ms, tests 35ms, environment 2.02s)

```

</details>

<details>
<summary>프론트 lint·format·build 전체 출력</summary>

```text
$ eslint .

$ prettier --check .
Checking formatting...
All matched files use Prettier code style!

$ tsc -b && vite build
vite v8.1.5 building client environment for production...
transforming...✓ 3328 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                     0.82 kB │ gzip:   0.48 kB
dist/assets/logo-CS11PIW0.png   3,392.58 kB
dist/assets/index-wTSF6KgR.css     18.42 kB │ gzip:   4.35 kB
dist/assets/index-BM8F48Jx.js     422.86 kB │ gzip: 142.04 kB

✓ built in 1.29s

```

</details>

## 2026-07-27 15:49 — ❌ 프론트 format 검사 실패 후 수정 (Codex)

- **명령**: `pnpm format:check`
- **환경**: Windows 11, pnpm 11.9.0
- **커밋**: `d22ad30` ([chore] OpenAPI 프론트 클라이언트 재생성, 수정 전)
- **맥락**: Git에서 무시되는 `shared/lib`를 `shared/utils`로 옮긴 직후 import가 재정렬되지 않아 실패. Prettier 적용 후 재검사 통과.

<details>
<summary>실패 출력</summary>

```text
$ prettier --check .
Checking formatting...
[warn] src/features/cart-map/ui/ArrivalModal.tsx
[warn] src/features/slot-board/ui/SlotDetailModal.tsx
[warn] src/features/slot-board/ui/SlotTile.tsx
[warn] src/pages/search/SearchPage.tsx
[warn] Code style issues found in 4 files. Run Prettier with --write to fix.
```

</details>

## 2026-07-27 15:41 — ❌ OpenAPI 재생성 직후 프론트 build 실패 후 수정 (Codex)

- **명령**: `pnpm build`
- **환경**: Windows 11, pnpm 11.9.0
- **커밋**: 미커밋 상태
- **맥락**: 기존 mock·story가 제거된 follow API와 이전 `Book` 타입을 참조하고, 새 nullable/필수 필드를 반영하지 않아 실패. 생성 타입에 맞춰 수정 후 빌드 통과.

<details>
<summary>실패 출력</summary>

```text
$ tsc -b && vite build
src/features/slot-board/ui/SlotTile.stories.tsx: Type 'SlotBook' 필수 필드 누락
src/features/slot-board/ui/SlotTile.test.tsx: 'lastDetectedAt' 필수 필드 누락
src/pages/search/SearchPage.tsx: nullable 'rfidTagId' 처리 누락
src/shared/api/mocks/handlers.ts: 삭제된 follow 모듈과 Book 타입 참조
Command failed with exit code 2.
```

</details>

## 2026-07-27 15:29 — ❌ 백엔드 테스트 컴파일 실패 후 수정 (Codex)

- **명령**: `backend/gradlew.bat test`
- **환경**: Windows 11, Microsoft OpenJDK 21.0.11
- **커밋**: 미커밋 상태
- **맥락**: Cart DTO 테스트 수정 중 `CartConnectionStatus` import 누락. import 복구 후 전체 테스트 통과.

<details>
<summary>실패 출력</summary>

```text
> Task :compileTestJava FAILED
CartServiceTests.java:41: error: cannot find symbol
    when(cart.getConnectionStatus()).thenReturn(CartConnectionStatus.OFFLINE);
                                                ^
  symbol:   variable CartConnectionStatus
  location: class CartServiceTests
1 error

BUILD FAILED in 3s

```

</details>
