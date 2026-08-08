# CLAUDE.md — embedded/
이 문서는 **임베디드 파트의 공통 규칙**을 설명합니다.
모듈별 구현 및 상세 내용은 각 하위 디렉토리의 `CLAUDE.md`를 우선합니다.
프로젝트 전체 개요는 [루트 CLAUDE.md](../CLAUDE.md)를 참고하세요.
Jetson ↔ STM32 인터페이스는 [docs/JETSON_TO_STM.md](../docs/JETSON_TO_STM.md)를 참고하세요.


## 역할
임베디드 파트는 카트의 하드웨어 제어를 담당합니다.
주요 구성은 다음과 같습니다.
- STM32 기반 모터 제어
- RFID 기반 도서 인식
- LED 제어
- Jetson과의 데이터 송수신
- 하드웨어 입출력(GPIO, PWM, UART 등)


## 디렉토리
| 경로 | 내용 |
|------|------|
| `motor/` | STM32 기반 모터 제어 |
| `rfid/` | RFID 인식 |
| `led/` | LED 제어 |
| `Lidar/` | SLAM/NAV colcon 워크스페이스 (X4Pro + slam_toolbox + Nav2, `/robot_pose`·`/target_position` 계약 구현) |

## 인터페이스 계약

**Jetson → STM32** ([JETSON_TO_STM.md](../docs/JETSON_TO_STM.md)):
- UART Serial 115200 bps, micro-ROS (ROS 2 Humble)
- 구독: `/wheel_speed_cmd` (`std_msgs/msg/Int32MultiArray`) — `data[0]` 좌측 RPM, `data[1]` 우측 RPM, 10~12 Hz

**카트 → Backend (MQTT)** — 2026-08-09 BE 소스 + 브로커 `#` 구독 실측으로 확정:

| 용도 | 토픽 | 페이로드 | 발행 주체 |
|---|---|---|---|
| SLAM 위치 | `status/position` | `{"x","y","yaw","timestamp"}` (미터·라디안·ISO8601 UTC) | `choll_mqtt_bridge`, 2Hz |
| 하트비트 | `status/cart` | `{"status"}` | (미구현 — 리테인 잔재만 관측) |
| 슬롯·RFID | `status/slot` | `{"slot_id","uid","event":"DETECTED\|REMOVED","timestamp"}` | RPi `embedded/rfid/main.py` |
| 추적 대상 | `status/target` | `{"image_width","image_height","tracks"}` | AI `fe_bridge_node` |

**Backend → 카트**: `cmd/move/cart` (`{"requestId","command":"MOVE\|CANCEL","zoneId","target":{x,y},"pixel":{x,y}}`),
`cmd/lit/led` (`{"slot_id":[...]}`).

> 🔴 2026-08-09 정정: 이전에 적혀 있던 `carts/{cartId}/telemetry/position` · `carts/status` ·
> `choll/cart/rfid` 는 **BE 코드에 존재하지 않는다**(`grep choll/` 0건). 위 표가 정본이다.

⚠️ 위치·RFID·하트비트 토픽에 cartId 미포함: BE가 `mqtt.cart-id`로 귀속하므로 다중 카트 도입 시 재협의.

🔴 **BE 측 전제 2개** (EM이 못 고침, 안 되어 있으면 위치가 도달해도 기능이 죽는다):
- `MQTT_POSITION_UNIT=meters` — 기본값 `pixels`. EM은 SLAM 미터를 보내므로 `pixels`면
  BE가 `x=1.235`를 픽셀 1.235로 읽어 구역 판정이 전부 실패한다(→ LED가 안 켜진다).
  같은 설정이 `NavigationService`의 MOVE `target`도 `null`로 만들어 EM이 명령을 거부한다.
- `library_maps` id=`MQTT_MAP_ID`(기본 2)에 사용 지도의 `resolution`/`origin_x`/`origin_y`/
  `width`/`height` 등록. 행이 없으면 meters 모드에서 매 메시지마다 예외가 난다 —
  **지도 등록을 meters 전환보다 먼저.**
- BE는 `yaw`를 파싱하지 않는다(`PositionPayload(x, y, timestamp)`). FE에는 항상 0이 나간다.

> ⚠️ 위 계약(토픽명·타입·매핑)을 바꾸려면 AI 파트(`motor_node`)·BE 파트와 동시에 바꿔야 합니다.
> 단독 변경 금지 — 이슈로 논의 후 정본 문서(JETSON_TO_STM.md / API 명세서)를 먼저 갱신하세요.

## 확정 필요

- [ ] STM32 보드 모델, CubeIDE/CubeMX 버전
- [ ] 커밋 범위: CubeMX 생성 프로젝트 전체 커밋 여부 (Drivers/, Middlewares/ 포함?)
- [ ] SLAM·Nav2 실행 위치: Jetson Orin? 별도 컴퓨트? (`ai/` 워크스페이스와의 코드 경계)
- [ ] CAN 버스 용도 (모터 드라이버? 센서?)

## 참고 문서
- 기능 명세서 > Embedded: https://app.notion.com/p/3a6135971f3c80c0a360d88ddfcf4e67
- 임베디드 워크플로우 (Excalidraw): https://excalidraw.com/#room=REDACTED 
