# CLAUDE.md — tests/ (파트 공통)

파트 공통 테스트 규칙과 공용 테스트 로그([TEST_LOG.md](TEST_LOG.md))의 집입니다.
**각 파트의 테스트 코드는 각 파트 디렉토리 안에 둡니다** — 이 디렉토리에 테스트 코드를 추가하지 마세요.

> AI 파트의 단위 테스트와 로그는 [ai/test/](../ai/test/CLAUDE.md)로 이동했습니다 (2026-07-28).

## 파트별 테스트 규칙

| 파트 | 테스트 위치 | 도구·실행 | 규칙 |
|------|-------------|-----------|------|
| AI | `ai/test/` + `ai/src/person_follow_robot/test/` | `pytest ai/test/`, `colcon test` | 2단계 전략은 [ai/test/CLAUDE.md](../ai/test/CLAUDE.md) 참조. 실기(추론·센서·주행) 검증은 Jetson에서만 가능 |
| FE | `frontend/` 내부 | Playwright(E2E), Storybook, MSW+orval 모킹 | BE 없이도 돌게 API는 MSW로 모킹. E2E는 핵심 유저 플로우(슬롯 보드·지도·추종 제어) 우선 |
| BE | `backend/src/test/` | JUnit 5 / Mockito, `./gradlew test` | 외부 의존(MySQL·MQTT Broker)은 모킹 또는 Testcontainers로 격리. MQTT↔WS 이벤트 변환 로직은 단위 테스트 필수 |
| EM | `embedded/` 내부 | 실기(HIL) 중심 | 하드웨어 없이 검증 가능한 로직(프로토콜 파싱, Differential Drive 계산 등)은 분리해서 단위 테스트. 센서·모터·MQTT 통신은 실기에서 체크리스트로 |

공통: 파트 간 **인터페이스 계약**(REST/WS/MQTT/토픽)을 바꾸는 변경은 해당 계약을 검증하는
테스트(스키마·페이로드 형식)를 함께 갱신하고, 정본 문서(API 명세서·JETSON_TO_STM.md)와 어긋나지 않는지 확인한다.

## 테스트 로그

테스트를 실행했으면 — 에이전트든 사람이든, 통과든 실패든 — 결과를 로그에 남긴다.
날짜·실행자·환경·명령·커밋과 함께 **원본 출력을 `<details>` 블록으로** 기록 (형식은 각 로그 상단 규칙 참조).

- AI: [ai/test/TEST_LOG.md](../ai/test/TEST_LOG.md)
- FE/BE/EM 및 여러 파트에 걸친 검증: [tests/TEST_LOG.md](TEST_LOG.md) (여기)
