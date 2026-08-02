# 쫄래쫄래 (Choll)

**사서를 따라다니며 구역별 도서 정리를 돕는 자율주행 북카트** — SSAFY S15P11C101

사서가 북카트에 책을 실으면 카트가 RFID로 어떤 책인지 알아채고, 사서를 졸졸 따라다니다가
(얼굴 인식이 아닌 **Person Re-ID**로 동일 인물 추적), 웹 화면에서 정리 진행률과 카트 위치를
실시간으로 보여줍니다.

## 시스템 전경

```
[사서용 웹 (FE)] ←─ REST / WebSocket ─→ [허브 서버 (BE)] ←─ MQTT ─→ [북카트]
                                             │                        ├── AI (Jetson): 사람 인식·추종, 사서 좌표 발행
                                          MySQL                       └── EM (STM32·RPi): SLAM·모터 구동·RFID
```

- **추종**: 카메라(YOLOv10s+ByteTrack+OSNet Re-ID) + LiDAR로 사서의 지도 좌표를 계산 → SLAM 내비게이션이 경로 계획 → 모터 구동
- **타겟 선택**: 카트에 가장 가까운 사람 자동 선택, 또는 웹 화면의 영상에서 직접 클릭
- **도서 인식**: 슬롯 RFID 태깅 → 실시간 슬롯 현황·정리 작업 진행률
- **모니터링**: SLAM 지도 위 카트 실시간 위치, 구역 판정, 목적지 이동 명령

## 파트 구성

| 파트 | 디렉토리 | 스택 | 시작 문서 |
|------|----------|------|-----------|
| AI (추종·인식) | [ai/](ai/) | ROS2 Humble · YOLOv10s TensorRT · ByteTrack · OSNet | [ai/README.md](ai/README.md) (실행 가이드) |
| BE (허브 서버) | [backend/](backend/) | Java 21 · Spring Boot · MySQL · MQTT | [backend/CLAUDE.md](backend/CLAUDE.md) |
| FE (사서용 웹) | [frontend/](frontend/) | React 18 · TypeScript · Vite | [frontend/CLAUDE.md](frontend/CLAUDE.md) |
| EM (카트 제어) | [embedded/](embedded/) | STM32 · Raspberry Pi · SLAM · RFID | [embedded/CLAUDE.md](embedded/CLAUDE.md) |
| Infra (배포) | [infra/](infra/) | Docker · Jenkins (main 브랜치 웹훅) | [Jenkinsfile](Jenkinsfile) |

배포 주소: http://your-server.example.com

## 저장소 구조 (최상위)

    Choll/
    ├── README.md            # (이 문서) 프로젝트 전체 소개
    ├── CLAUDE.md            # AI 에이전트/기여자 진입점 — 저장소 지도, 규칙
    ├── ai/                  # AI 파트 (ROS2 워크스페이스 + 단위 테스트)
    ├── backend/             # BE 파트 (Spring Boot)
    ├── frontend/            # FE 파트 (React)
    ├── embedded/            # EM 파트 (STM32·RPi)
    ├── infra/               # 배포 compose
    ├── docs/                # 프로젝트 공통 문서 (단일 진실 공급원)
    ├── tests/               # 파트 공통 테스트 규칙·공용 테스트 로그
    └── scripts/             # 유지보수 스크립트 (가비지 컬렉션, Jetson 운영)

## 공통 문서

| 문서 | 내용 |
|------|------|
| [docs/PROJECT_CHARTER.md](docs/PROJECT_CHARTER.md) | 프로젝트 목표, 범위, 제약 |
| [docs/SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md) | 파이프라인 · ROS2 토픽 · 데이터 흐름 |
| [docs/AI_SPECIFICATIONS.md](docs/AI_SPECIFICATIONS.md) | AI 모델 명세와 선택 이유 |
| [docs/JETSON_TO_STM.md](docs/JETSON_TO_STM.md) | Jetson ↔ STM32 인터페이스 계약 |
| [docs/GIT_CONVENTION.md](docs/GIT_CONVENTION.md) | 브랜치 전략 · 커밋 메시지 · MR 템플릿 |
| [docs/MAINTENANCE.md](docs/MAINTENANCE.md) | 저장소 정리 정책 |

## 기여 규칙 (요약)

`develop`에서 `파트/타입/이름` 브랜치 분기 → 커밋 메시지 `[type] subject` → MR은 develop 대상,
**머지는 사람이** 합니다. 상세: [docs/GIT_CONVENTION.md](docs/GIT_CONVENTION.md)
