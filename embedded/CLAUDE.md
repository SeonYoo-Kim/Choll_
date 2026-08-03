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

**카트 → Backend (MQTT, 현재 확정분)**:
- `carts/{cartId}/telemetry/position` (SLAM 위치), `carts/status` (하트비트 — 5초 주기 발행 약속, 2026-07-30 확정),
  `choll/cart/rfid` (슬롯·RFID — 2026-07-30 실물 기준 확정, 페이로드 `{"slot_id","uid","event":"DETECTED|REMOVED","timestamp"}`.
  ⚠️ 하트비트·RFID 토픽에 cartId 미포함: BE가 `mqtt.cart-id`로 귀속하므로 다중 카트 도입 시 BE와 재협의)
- BE→EM 명령 토픽(이동·추종·LED·RFID 재인식)은 명세 작성 중

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
