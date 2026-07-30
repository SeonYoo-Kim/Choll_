# CLAUDE.md — embedded/

쫄래쫄래 프로젝트의 **임베디드** 작업 공간입니다.
프로젝트 전체 맥락은 [루트 CLAUDE.md](../CLAUDE.md), Jetson↔STM32 인터페이스 정본은 [docs/JETSON_TO_STM.md](../docs/JETSON_TO_STM.md)입니다.

## 기술 스택 

STM32(MCU) · ROS 2 · DC 모터 · SLAM · LiDAR · CAN · Ubuntu 22.04.5 LTS

## 기능 명세

| 영역 | 내용 |
|------|------|
| 카트 상태 | 상태 송신(MQTT), 정지 명령 처리(모터 PWM 차단) |
| RFID·슬롯 | 슬롯 RFID 태그 읽기, 책 삽입/제거 감지 → MQTT Publish |
| 위치·Navigation | SLAM 위치 추정(ROS2 Localization), 위치 MQTT 송신, Nav2 Goal 기반 목적지 이동/취소 |
| 카메라 | 카메라 영상을 Jetson Orin에 전달 (AI 파이프라인 입력) |
| 모터 | `/cmd_vel` 수신 → Differential Drive 계산 → PWM 출력, 엔코더 읽기, 긴급 정지 |
| LED | 슬롯 LED 점등(BE의 MQTT 명령), 카트 상태 LED |
| MQTT | Broker 연결/재연결, BE 명령 수신·상태 송신 |

## 인터페이스 계약

**Jetson → STM32** ([JETSON_TO_STM.md](../docs/JETSON_TO_STM.md)):
- UART Serial 115200 bps, micro-ROS (ROS 2 Humble)
- 구독: `/wheel_speed_cmd` (`std_msgs/msg/Int32MultiArray`) — `data[0]` 좌측 RPM, `data[1]` 우측 RPM, 10~12 Hz

**카트 → Backend (MQTT, 현재 확정분)**:
- `carts/{cartId}/telemetry/position` (SLAM 위치), `carts/{cartId}/status` (동작 상태·하트비트),
  `choll/cart/rfid` (슬롯·RFID — 2026-07-30 실물 기준 확정, 페이로드 `{"slot_id","uid","event":"DETECTED|REMOVED","timestamp"}`.
  ⚠️ cartId 미포함: BE가 `mqtt.rfid-cart-id`로 귀속하므로 다중 카트 도입 시 BE와 재협의)
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

## 이 디렉토리에서 지켜야 할 것

- 커밋 메시지 `[type] subject`, 브랜치는 `develop`에서 `feature/*` 분기 → [GIT_CONVENTION.md](../docs/GIT_CONVENTION.md)
- 빌드 산출물(`Debug/`, `Release/`, `.o`, `.elf` 등) 커밋 금지, CubeMX `.ioc`는 커밋 (재생성 정본)
