# CLAUDE.md — backend/ 

쫄래쫄래 프로젝트의 **백엔드 서버**입니다. FE(웹)와 카트(EM/AI) 사이의 허브 역할을 합니다.
프로젝트 전체 맥락은 [루트 CLAUDE.md](../CLAUDE.md), 협업 규칙은 [docs/GIT_CONVENTION.md](../docs/GIT_CONVENTION.md)를 먼저 읽으세요.

## 기능 명세

```
FE ←REST/WebSocket/WebRTC시그널링→ BE ←MQTT→ 카트(EM/AI)
```

1. **카트 관리**: 상태 조회/갱신, MQTT Heartbeat 기반 연결 상태 판정
2. **슬롯·RFID**: 슬롯 상태 갱신, RFID ID↔도서 매칭, 재인식 요청 중계
3. **지도·구역**: SLAM 지도 제공, FE 좌표↔SLAM 좌표 상호 변환, 카트 위치의 현재 구역 판정
4. **정리 작업**: 도서 인식 시 작업 생성, 책 제거 시 완료 처리, 진행률 계산,
   구역별 슬롯 LED 대상 결정(구현됨 — `cmd/lit/led` 발행)
5. **이동·추종**: FE 요청을 MQTT 명령으로 변환(requestId로 요청-결과 연결), 상태를 WS 이벤트로 FE에 전달
6. **WebRTC 시그널링**: FE↔카트 카메라 간 Offer/Answer/ICE 중계 (우선순위 2)

**1차 개발 흐름**: REST 조회 → 가짜 카트의 MQTT 수신 → DB 갱신 → WS 전달 → 이동 명령 변환 → 구역 판정·LED. 추종/WebRTC는 그 다음.

## 기술 스택

| 항목 | 값 |
|------|-----|
| 언어/프레임워크 | Java 21, Spring Boot 4.1.0 |
| 데이터 | Spring Data JPA, MySQL 8.4 (EC2 Docker 컨테이너 — RDS 아님) |
| 보안 | Spring Security + JWT (미구현 — 웹 노출 보호는 nginx 레벨 검토 중) |
| 빌드/테스트 | Gradle, JUnit 5 / Mockito |
| API 문서 | Swagger (springdoc-openapi) — FE가 orval로 클라이언트 생성하므로 스키마 정확성 중요 |
| 인프라 | AWS EC2 (your-server.example.com), Docker, Jenkins (main 머지 시 자동 배포 — 루트 Jenkinsfile) |

## API 명세

- **REST**: `/api/carts/{cartId}/...`, `/api/maps/{mapId}/...` (CART/SLOT/MAP/TASK/NAV/FOLLOW)
  — NAV-01/02 구현됨: `POST/DELETE /api/carts/{cartId}/navigation` (202/204, 오프라인·중복 시작은 400)
- **WebSocket**: `/ws/carts/{cartId}`, JSON, BE→FE 이벤트 13종 (WS-FE-01~13)
  — 실구현 6종: `CART_POSITION_UPDATE`(MQTT 위치 중계, yaw는 EM 미송신으로 임시 0), `SLOT_UPDATED`(RFID 중계),
  `CART_CONNECTION_UPDATED`(하트비트 기반 ONLINE/OFFLINE 전환 시), `NAVIGATION_STATUS_UPDATED`(ACCEPTED/CANCELLED —
  STARTED/ARRIVED/FAILED는 카트 상행 결과 토픽 확정 후), `TASK_PROGRESS_UPDATED`(RFID 이벤트마다),
  `TRACKS_UPDATED`(AI 추적 후보 중계 — FE 타겟 선택 UI용)
- **WebSocket 영상**: `/ws/carts/{cartId}/video` (FE 시청, 바이너리 JPEG 1메시지=1프레임)
  ← `/ws/carts/{cartId}/video/publish` (Jetson 발행, 10fps/품질70 기준 ~4Mbps)
- **MQTT 토픽 네이밍 규칙**: 카트·AI→BE **상행은 `status/*`**, BE→카트 **하행은 `cmd/*`**.
  새 토픽을 만들 때 방향과 프리픽스가 어긋나지 않게 할 것.
  **선행 슬래시를 붙이지 않는다** — `/status/…`는 빈 최상위 레벨을 만든다 (ROS 토픽과 혼동 주의).
- **MQTT** (카트→BE, 현재 확정분):
  - `status/position` — `{"x","y","timestamp"}` → 구역 판정 후 DB 갱신 + WS 중계.
    좌표 단위 계약(2026-07-31): **SLAM 미터** — `mqtt.position-unit=meters`면 BE가 지도 메타(resolution·origin)로
    이미지 픽셀 변환(세로축 뒤집기 포함). 기본값 pixels(무변환) — EM 발행 시작 시 meters로 전환 +
    `library_maps`(id=`mqtt.map-id`) 행에 실제 map.yaml 값 입력 필요
  - `status/slot` — `{"slot_id","uid","event":"DETECTED|REMOVED","timestamp"}` (2026-07-30 실물 기준 확정)
  - `status/cart` (하트비트, 5초 주기) — 수신 시 ONLINE, `cart.connection.offline-timeout-seconds`(기본 15초)
    무신호 시 워치독이 OFFLINE 전환. 페이로드는 timestamp 선택(없으면 수신 시각 기준)
  - `status/target` (AI→BE, 5~10Hz) — `{"image_width","image_height","tracks":[{"id","x","y","w","h"}]}`
    (x,y=bbox 좌상단 픽셀) → WS `TRACKS_UPDATED`로 원형 그대로 중계
  - ⚠️ 수신 토픽 4종 모두 cartId가 없어 `mqtt.cart-id`(기본 1)로 귀속 — 다중 카트 도입 시 재협의 필요
- **MQTT** (BE→카트 명령): `cmd/move/cart`
  - `{"requestId","command":"MOVE|CANCEL","zoneId","x","y"}` (구역 bbox 중심 좌표)
  - `{"command":"SELECT_TARGET","trackId"}` — `POST /api/carts/{id}/follow/target`에서 발행,
    Jetson fe_bridge_node가 `/select_target` ROS 토픽으로 변환
  ⚠️ EM 미확정 임시 계약 — 추종·RFID 재인식 포함 확정 시 EM·API 명세서와 동시 갱신할 것
- **MQTT** (BE→라즈베리파이 슬롯 LED): `cmd/lit/led` — `{"slot_id":[1,3,5]}`
  - **카트의 구역이 바뀌는 순간에만** 발행 (`SlotLedService`). 같은 구역에 머무는 동안은 발행하지 않는다.
  - `slot_id` = **그 시점에 켜져 있어야 할 슬롯 전체** = `isTarget`(슬롯의 책이 꽂힐 서가 구역 ==
    카트 현재 구역)인 슬롯 번호 (키 이름은 `status/slot` RFID 페이로드와 통일).
    라즈베리파이는 이 목록으로 점등 상태를 통째로 맞추면 된다.
  - **구역 이탈 시 빈 목록 `[]` 발행** — 책을 남기고 나가도 LED가 켜진 채 남지 않게. 구역 간 이동이면
    새 구역의 목록이 그대로 이전 상태를 대체한다.
  - 예외: 구역 밖에서 대상 없는 구역으로 들어갈 때는 켤 것도 끌 것도 없어 발행하지 않는다.
  - 슬롯에서 책이 빠졌을 때(RFID REMOVED)의 소등은 라즈베리파이가 자체 처리 — BE는 재발행하지 않는다.
  - DB 슬롯은 1~12번이지만 실물 RFID 리더는 5개만 설치(재정상). RFID가 없는 6~12번은 책이 인식되지
    않아 `isTarget`이 될 수 없으므로 `slot_id`에도 나오지 않는다.

## 참고 문서

- API 명세서: https://app.notion.com/p/API-3a3135971f3c804c8c56e68e492e3990
- 기능 명세서 > BE: https://app.notion.com/p/3a3135971f3c806ea787f252ce76e8d1
- ERD: https://www.erdcloud.com/d/vW3GTJQcayrfsLsDy (비공개 — 접근 권한 필요)

## 이 디렉토리에서 지켜야 할 것

- 커밋 메시지 `[type] subject`, 브랜치는 `develop`에서 `feature/*` 분기 → [GIT_CONVENTION.md](../docs/GIT_CONVENTION.md)
- `build/`, `.gradle/` 등 빌드 산출물 커밋 금지 (`.gitignore` 유지)
- **시크릿(DB 비밀번호, JWT 키, AWS 자격증명) 절대 커밋 금지** — 환경변수/외부 설정으로 분리
- MQTT 토픽·페이로드를 바꾸면 EM 파트와 API 명세서를 동시에 갱신 (단독 변경 금지)
