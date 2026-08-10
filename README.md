# 쫄래쫄래 (Choll)

> **사서를 따라다니며 구역별 도서 정리를 돕는 자율주행 북카트**
> SSAFY 15기 공통 프로젝트 · S15P11C101 · 2026.07.16 ~ 2026.08.11

사서가 북카트에 책을 실으면 카트가 **RFID로 어떤 책인지 인식**하고, 얼굴 인식이 아닌
**Person Re-Identification(Re-ID)** 으로 사서를 졸졸 따라다니며, 웹 화면에서
**정리 진행률과 카트 위치를 실시간으로** 보여줍니다.

배포 주소: http://your-server.example.com

---

## 목차

1. [주요 기능](#주요-기능)
2. [시스템 아키텍처](#시스템-아키텍처)
3. [AI 파이프라인](#ai-파이프라인)
4. [기술 스택](#기술-스택)
5. [저장소 구조](#저장소-구조)
6. [실행 방법](#실행-방법)
7. [문서](#문서)
8. [팀원](#팀원)
9. [기여 규칙](#기여-규칙)

---

## 주요 기능

### 🚶 사람 추종 (AI)

- **타겟 등록**: 카트에 가장 가까운 사람(최대 bbox)을 자동 선택해 2초간 등록 — 또는 웹 화면의 카메라 영상에서 사서를 직접 클릭해 선택
- **동일 인물 추적**: YOLOv10s(TensorRT) 탐지 → ByteTrack 추적 → OSNet Re-ID 특징(512-D)을 Memory Bank에 저장
- **가림 복구**: 사람에 가려지거나 잠시 시야에서 사라져도 Re-ID 매칭으로 같은 사서를 다시 찾아 추적 재개
- **좌표 발행**: 카메라 방위각 + LiDAR 거리 + 카트 포즈(SLAM)를 융합해 사서의 지도 좌표(`/target_position`)를 발행 → SLAM 내비게이션이 경로 계획
- Jetson Orin Nano 8GB에서 **실시간(10 FPS+) 구동**

### 📚 도서 인식·정리 작업 (EM + BE)

- 슬롯에 책을 올리면 **RFID 태깅**으로 어떤 책인지 자동 인식
- 카트가 서가 구역에 진입하면 **그 구역에 꽂을 책이 있는 슬롯의 LED 점등**
- 도서 인식 시 정리 작업 자동 생성, 책 제거 시 완료 처리 → 진행률 계산

### 🗺️ 실시간 모니터링·제어 (FE + BE)

- **슬롯 상태 보드**: 슬롯별 비어 있음/책 있음/인식 실패, 책 정보(제목·구역)
- **지도**: 평면도 위 카트 실시간 위치·구역 판정, 지도 클릭으로 목적지 지정(자유 좌표 이동)
- **카트 제어**: 호출·이동 취소·추종 시작/일시정지/종료, 카트 연결 상태(하트비트) 표시
- **실시간 영상**: 카트 카메라 영상 스트리밍(WebSocket 바이너리 JPEG) + AI 탐지 박스 오버레이

## 시스템 아키텍처

```
[사서용 웹 (FE)] ←─ REST / WebSocket ─→ [허브 서버 (BE)] ←─ MQTT ─→ [북카트]
                                             │                        ├── AI (Jetson): 사람 인식·추종, 사서 좌표 발행
                                          MySQL                       └── EM (STM32·RPi): SLAM·모터 구동·RFID·LED
```

- **FE ↔ BE**: REST(`/api/carts/{cartId}/...`) + WebSocket 이벤트(`/ws/carts/{cartId}`) + 영상(`/ws/carts/{cartId}/video`)
- **BE ↔ 카트**: MQTT — 상행 `status/*`(위치·슬롯·하트비트·추적 후보·내비 결과), 하행 `cmd/*`(이동·추종·LED)
- **카트 내부**: Jetson(AI, ROS2) ↔ USB Serial(micro-ROS) ↔ STM32(모터), Raspberry Pi(RFID·LED)

상세 토픽 계약은 [docs/SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md) 참조.

## AI 파이프라인

```
RGB Camera → YOLOv10s(TensorRT) → ByteTrack → [최근접 자동 선택 → 2초 등록] → OSNet Re-ID
    → Memory Bank → (추적 성공 | 추적 실패 → Re-ID 재탐색) → Target Track ID
    → 방위각(카메라) + 거리(LiDAR) + 카트 포즈(SLAM) → 타겟 지도 좌표 /target_position
    → SLAM 내비게이션 경로 계획 (EM) → STM32 모터 구동
```

- **스택 고정**: YOLOv10s TensorRT · ByteTrack · OSNet · Online Memory Bank — Fine-tuning 없이, 추가 데이터셋 수집 없이, TensorRT 추론만으로 동작
- **성능 예산**: 10 FPS+ (LiDAR ~10 Hz 기준), 지연 < 100 ms, GPU 메모리 < 6 GB
- 모델 선택 이유와 파라미터: [docs/AI_SPECIFICATIONS.md](docs/AI_SPECIFICATIONS.md)

## 기술 스택

| 파트 | 디렉토리 | 스택 | 시작 문서 |
|------|----------|------|-----------|
| AI (추종·인식) | [ai/](ai/) | ROS2 Humble · Python 3.10 · YOLOv10s TensorRT · ByteTrack · OSNet | [ai/README.md](ai/README.md) |
| BE (허브 서버) | [backend/](backend/) | Java 21 · Spring Boot 4.1.0 · Spring Data JPA · MySQL 8.4 · MQTT(Mosquitto) · Swagger | [backend/CLAUDE.md](backend/CLAUDE.md) |
| FE (사서용 웹) | [frontend/](frontend/) | React 18 · TypeScript · Vite · TanStack Query · Zustand · Ant Design · MSW/orval · Playwright | [frontend/CLAUDE.md](frontend/CLAUDE.md) |
| EM (카트 제어) | [embedded/](embedded/) | STM32 NUCLEO-F446RE(C·HAL) · Raspberry Pi(Python) · micro-ROS · SLAM/Nav2 · RFID | [embedded/CLAUDE.md](embedded/CLAUDE.md) |
| Infra (배포) | [infra/](infra/) | AWS EC2 · Docker · nginx · Jenkins (main 브랜치 웹훅 자동 배포) | [Jenkinsfile](Jenkinsfile) |

## 저장소 구조

    Choll/
    ├── README.md            # (이 문서) 프로젝트 전체 소개
    ├── CLAUDE.md            # AI 에이전트/기여자 진입점 — 저장소 지도, 규칙
    ├── ai/                  # AI 파트 (ROS2 워크스페이스 + 단위 테스트)
    ├── backend/             # BE 파트 (Spring Boot)
    ├── frontend/            # FE 파트 (React)
    ├── embedded/            # EM 파트 (STM32·RPi)
    ├── infra/               # 배포 compose
    ├── exec/                # 포팅 매뉴얼 (빌드·배포·실행 절차)
    ├── docs/                # 프로젝트 공통 문서 (단일 진실 공급원)
    ├── tests/               # 파트 공통 테스트 규칙·공용 테스트 로그
    └── scripts/             # 유지보수·시연 보조 스크립트

## 실행 방법

전체 빌드·배포·실행 절차의 정본은 **[exec/포팅매뉴얼.md](exec/포팅매뉴얼.md)** 입니다. 요약:

```bash
# Frontend (frontend/)
pnpm install && pnpm dev        # BE 없이 화면만: .env.development.local에 VITE_ENABLE_MSW=true

# Backend (backend/) — MySQL 8.4 + Mosquitto 필요
./gradlew bootRun

# AI (Jetson, 저장소 루트에서 — 모델을 models/*.engine 상대경로로 찾음)
cd ai && colcon build --symlink-install && source install/setup.bash && cd ..
ros2 launch person_follow_robot follow_robot_launch.py
```

시연 절차는 [docs/DEMO_RUNBOOK.md](docs/DEMO_RUNBOOK.md) 참조.

## 문서

| 문서 | 내용 |
|------|------|
| [docs/PROJECT_CHARTER.md](docs/PROJECT_CHARTER.md) | 프로젝트 목표, 범위, 제약, 성공 기준 |
| [docs/SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md) | 파이프라인 · ROS2 토픽 · 데이터 흐름 |
| [docs/AI_SPECIFICATIONS.md](docs/AI_SPECIFICATIONS.md) | AI 모델 명세와 선택 이유 |
| [docs/JETSON_TO_STM.md](docs/JETSON_TO_STM.md) | Jetson ↔ STM32 인터페이스 계약 |
| [docs/DEMO_RUNBOOK.md](docs/DEMO_RUNBOOK.md) | 시연 절차 (데모 런북) |
| [docs/GIT_CONVENTION.md](docs/GIT_CONVENTION.md) | 브랜치 전략 · 커밋 메시지 · MR 템플릿 |
| [docs/MAINTENANCE.md](docs/MAINTENANCE.md) | 저장소 정리 정책 |
| [exec/포팅매뉴얼.md](exec/포팅매뉴얼.md) | 빌드 · 배포 · 실행 · 외부 서비스 · DB 덤프 |

## 팀원

| 이름 | 파트 |
|------|------|
| FE 담당 | FE |
| 김선유 | BE · AI |
| LED·RFID 담당 | 임베디드 |
| SLAM 담당 | 임베디드 |
| 모터제어 담당 | 임베디드 |

## 기여 규칙

`develop`에서 `파트/타입/이름` 브랜치 분기 → 커밋 메시지 `[type] subject` → MR은 develop 대상,
**머지는 사람이** 합니다. 상세: [docs/GIT_CONVENTION.md](docs/GIT_CONVENTION.md)
