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
4. **정리 작업**: 도서 인식 시 작업 생성, 책 제거 시 완료 처리, 진행률 계산, 구역별 슬롯 LED 대상 결정
5. **이동·추종**: FE 요청을 MQTT 명령으로 변환(requestId로 요청-결과 연결), 상태를 WS 이벤트로 FE에 전달
6. **WebRTC 시그널링**: FE↔카트 카메라 간 Offer/Answer/ICE 중계 (우선순위 2)

**1차 개발 흐름**: REST 조회 → 가짜 카트의 MQTT 수신 → DB 갱신 → WS 전달 → 이동 명령 변환 → 구역 판정·LED. 추종/WebRTC는 그 다음.

## 기술 스택

| 항목 | 값 |
|------|-----|
| 언어/프레임워크 | Java 21, Spring Boot 4.1.0 |
| 데이터 | Spring Data JPA, MySQL 8.4 (AWS RDS) |
| 보안 | Spring Security + JWT |
| 빌드/테스트 | Gradle, JUnit 5 / Mockito |
| API 문서 | Swagger (springdoc-openapi) — FE가 orval로 클라이언트 생성하므로 스키마 정확성 중요 |
| 인프라 | AWS EC2, Docker, GitHub Actions |

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
- **MQTT** (카트→BE, 현재 확정분):
  - `carts/{cartId}/telemetry/position` — `{"x","y","timestamp"}` → 구역 판정 후 DB 갱신 + WS 중계
  - `choll/cart/rfid` — `{"slot_id","uid","event":"DETECTED|REMOVED","timestamp"}` (2026-07-30 실물 기준 확정)
  - `carts/status` (하트비트, 5초 주기) — 수신 시 ONLINE, `cart.connection.offline-timeout-seconds`(기본 15초)
    무신호 시 워치독이 OFFLINE 전환. 페이로드는 timestamp 선택(없으면 수신 시각 기준)
  - `choll/cart/tracks` (AI→BE, 5~10Hz) — `{"image_width","image_height","tracks":[{"id","x","y","w","h"}]}`
    (x,y=bbox 좌상단 픽셀) → WS `TRACKS_UPDATED`로 원형 그대로 중계
  - ⚠️ 하트비트·RFID·tracks 토픽에 cartId가 없어 `mqtt.cart-id`(기본 1)로 귀속 — 다중 카트 도입 시 재협의 필요
- **MQTT** (BE→카트 명령): `choll/cart/cmd`
  - `{"requestId","command":"MOVE|CANCEL","zoneId","x","y"}` (구역 bbox 중심 좌표)
  - `{"command":"SELECT_TARGET","trackId"}` — `POST /api/carts/{id}/follow/target`에서 발행,
    Jetson fe_bridge_node가 `/select_target` ROS 토픽으로 변환
  ⚠️ EM 미확정 임시 계약 — 추종·LED·RFID 재인식 포함 확정 시 EM·API 명세서와 동시 갱신할 것

## 참고 문서

- API 명세서: https://app.notion.com/p/API-3a3135971f3c804c8c56e68e492e3990
- 기능 명세서 > BE: https://app.notion.com/p/3a3135971f3c806ea787f252ce76e8d1
- ERD: https://www.erdcloud.com/d/vW3GTJQcayrfsLsDy (비공개 — 접근 권한 필요)

## 이 디렉토리에서 지켜야 할 것

- 커밋 메시지 `[type] subject`, 브랜치는 `develop`에서 `feature/*` 분기 → [GIT_CONVENTION.md](../docs/GIT_CONVENTION.md)
- `build/`, `.gradle/` 등 빌드 산출물 커밋 금지 (`.gitignore` 유지)
- **시크릿(DB 비밀번호, JWT 키, AWS 자격증명) 절대 커밋 금지** — 환경변수/외부 설정으로 분리
- MQTT 토픽·페이로드를 바꾸면 EM 파트와 API 명세서를 동시에 갱신 (단독 변경 금지)
