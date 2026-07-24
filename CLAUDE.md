# CLAUDE.md — 쫄래쫄래 (Person-Following Book Cart)

이 파일은 Claude Code / AI 에이전트가 이 저장소에서 작업할 때 **가장 먼저 읽는 컨텍스트**입니다.
사람용 소개는 [README.md](README.md), 상세 명세는 [docs/](docs/)를 참조하세요.

## 프로젝트 한 줄 요약

사서를 따라다니며 구역별 도서 정리를 돕는 **ROS2 기반 자율주행 북카트**.
Face Recognition이 아닌 **Person Re-Identification(Re-ID)** 으로 동일 인물을 추적하며,
**Jetson Orin Nano 8GB** 위에서 실시간(10 FPS+) 구동을 목표로 합니다.

## 저장소 지도 (어디에 무엇이 있는가)

| 경로 | 내용 | 진입점 CLAUDE.md |
|------|------|------------------|
| [docs/](docs/) | 프로젝트 헌장·아키텍처·AI 명세·개발 가이드 | [docs/CLAUDE.md](docs/CLAUDE.md) |
| [ai/src/person_follow_robot/](ai/src/person_follow_robot/) | ROS2 패키지 (빌드/실행 단위) | [패키지 CLAUDE.md](ai/src/person_follow_robot/CLAUDE.md) |
| `ai/.../person_follow_robot/` | ROS2 노드 소스 (7개 노드) | [노드 CLAUDE.md](ai/src/person_follow_robot/person_follow_robot/CLAUDE.md) |
| [tests/](tests/) | 프레임워크 독립 로직 단위 테스트 | [tests/CLAUDE.md](tests/CLAUDE.md) |
| [frontend/](frontend/) | FE: 사서용 카트 관리 웹 (React 18+TS+Vite) | [frontend/CLAUDE.md](frontend/CLAUDE.md) |
| [backend/](backend/) | BE: 허브 서버 (Java 21+Spring Boot, MySQL, MQTT) | [backend/CLAUDE.md](backend/CLAUDE.md) |
| [embedded/](embedded/) | EM: 카트 제어 (STM32·ROS2·SLAM·RFID·MQTT) | [embedded/CLAUDE.md](embedded/CLAUDE.md) |
| `ai/.../test/` | ament lint + colcon 테스트 | (패키지 CLAUDE.md 참조) |
| [scripts/](scripts/) | 유지보수 스크립트 (가비지 컬렉션 등) | — |

## 파이프라인 (데이터 흐름)

```
RGB Camera → YOLOv10s(TensorRT) → ByteTrack → [사서 선택 2초] → OSNet Re-ID
    → Memory Bank → (추적 성공 | 추적 실패→Re-ID 재탐색) → Target Track ID
    → 화면 중심 오차 + LiDAR 거리 → PID → /cmd_vel → Motor
```

노드 단위 매핑: `camera_node → detector_node → tracker_node → reid_node → control_node → motor_node` (+ `debug_visualization_node`).
자세한 토픽 계약은 [SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md)와 노드 CLAUDE.md를 참조.

## 절대 규칙 (docs/DEVELOPMENT_GUIDE.md의 코딩 규칙 요약)

- **AI 스택 고정**: YOLOv10s TensorRT · ByteTrack · OSNet · Online Memory Bank. **Fine-tuning 금지, 추가 데이터셋 수집 금지, TensorRT 추론만.**
- **범위 밖(Out of Scope)**: Face Recognition, Voice Recognition, Pose Estimation, Crowd Analysis. 이 방향의 코드를 새로 만들지 말 것.
- **코드 스타일**: PEP8 준수, **Type Hint · Docstring 필수**. 전역 변수 금지. 예외 처리와 로깅 필수.
- **아키텍처**: 하나의 ROS2 노드 = 단일 책임(SRP). 토픽 기반 느슨한 결합. 노드 간 직접 호출 금지.
- **성능 예산**: 10 FPS+ (LiDAR ~10 Hz 기준), 지연 < 100 ms, GPU 메모리 < 6 GB.

## 자주 쓰는 명령

빌드·실행·테스트의 정본은 [패키지 CLAUDE.md](ai/src/person_follow_robot/CLAUDE.md)에 있습니다. 요약:

```bash
# 빌드 (colcon 워크스페이스 루트 = 저장소/ai 에서. 코드 변경 시마다 여기서 재빌드)
# Jetson 실기: cd ~/Choll/ai
cd ai && colcon build --symlink-install && source install/setup.bash

# 실행 (SSH 접속 + 터미널 3개. 상세 단계는 README Quick Start 참조)
# 반드시 저장소 루트에서 실행 (모델을 models/*.engine 상대경로로 찾음)
ros2 launch person_follow_robot follow_robot_launch.py

# 프레임워크 독립 로직 테스트 (ROS 설치 불필요)
pytest tests/

# 린트/포맷 (pyproject.toml 설정)
ruff check . && ruff format --check .

# 가비지 컬렉션 (빌드 산출물 정리)
bash scripts/gc.sh          # 또는 Windows: pwsh scripts/gc.ps1
```

## 작업 원칙 (에이전트용)

1. **코드를 바꾸기 전에 해당 디렉토리의 CLAUDE.md와 관련 docs를 읽는다.**
2. 노드를 수정하면 **토픽 계약**(이름·타입)이 파이프라인의 이웃 노드와 일치하는지 확인한다. (알려진 불일치는 노드 CLAUDE.md의 "Known Gaps" 참조.)
3. 새 파라미터는 `declare_parameter`로 선언하고 launch 파일과 문서에 반영한다.
4. 임시 산출물(빌드, 결과 영상, 캐시)은 커밋하지 않는다. → [docs/MAINTENANCE.md](docs/MAINTENANCE.md)의 가비지 컬렉션 정책.
5. 변경 후 `ruff check`와 `pytest tests/`를 돌리고, **결과(통과/실패 모두)를 [tests/TEST_LOG.md](tests/TEST_LOG.md)에 기록한다.**
   "테스트 통과"라는 주장은 이 로그의 원본 출력으로 사람이 검증할 수 있어야 한다. 형식은 TEST_LOG.md 상단 규칙 참조.
6. **커밋 메시지는 `[type] subject` 형식** (`feat`/`fix`/`refactor`/`style`/`docs`/`test`/`chore`, 50자 이하·명사형·마침표 없이).
   브랜치 전략·MR/이슈 템플릿 포함 전체 규칙: [docs/GIT_CONVENTION.md](docs/GIT_CONVENTION.md)
