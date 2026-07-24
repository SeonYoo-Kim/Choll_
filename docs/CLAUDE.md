# CLAUDE.md — docs/

프로젝트의 **단일 진실 공급원(source of truth)** 문서 모음입니다.
코드가 문서와 어긋나면 문서를 갱신하거나(설계 변경 시) 코드를 고칩니다(구현 오류 시). 어느 쪽인지 애매하면 사용자에게 확인하세요.

## 문서 색인

| 문서 | 무엇을 볼 때 | 성격 |
|------|--------------|------|
| [PROJECT_CHARTER.md](PROJECT_CHARTER.md) | 목표·범위·제약·성공 기준 | 불변에 가까움 (WHY) |
| [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) | 파이프라인·ROS2 토픽·노드 그래프 | 구조 (WHAT) |
| [AI_SPECIFICATIONS.md](AI_SPECIFICATIONS.md) | 모델·트래커·Re-ID·PID 파라미터와 선택 이유 | 명세 (WHAT/WHY) |
| [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) | 코딩 규칙·아키텍처 원칙·단계별 TODO | 규칙 (HOW) |
| [JETSON_TO_STM.md](JETSON_TO_STM.md) | Jetson↔STM32 UART / micro-ROS 인터페이스 규격 | 인터페이스 계약 |
| [MAINTENANCE.md](MAINTENANCE.md) | 가비지 컬렉션·정리 정책·저장소 위생 | 운영 (HOW) |
| [GIT_CONVENTION.md](GIT_CONVENTION.md) | 브랜치 전략·커밋 메시지·MR/이슈 템플릿 | 협업 규칙 (HOW) |

## 편집 규칙

- **PROJECT_CHARTER.md는 함부로 넓히지 않는다.** 범위(Out of Scope)를 늘리는 변경은 사용자 승인이 필요.
- 성능 목표(10 FPS, <100 ms, <6 GB)나 AI 스택(YOLOv10s/ByteTrack/OSNet)을 바꾸려면 CHARTER·SPEC·DEVELOPMENT_GUIDE를 함께 갱신한다.
- 토픽 이름/타입을 바꾸면 SYSTEM_ARCHITECTURE.md와 노드 CLAUDE.md를 동시에 갱신한다.
- 단계별 진행 상태는 DEVELOPMENT_GUIDE.md의 TODO와 README의 Current Progress 두 곳에 있다 — 한쪽만 고치지 말 것.
