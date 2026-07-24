# CLAUDE.md — tests/

**프레임워크 독립(framework-independent) 로직 단위 테스트**의 집입니다.
ROS·TensorRT·GPU 설치 없이 순수 파이썬으로 실행됩니다.

```bash
pip install pytest        # 최초 1회
pytest tests/ -v
```

> 이 디렉토리는 **AI 파트(ros2_ws) 전용**입니다. FE/BE/EM 테스트는 각 파트 디렉토리
> 안에 두고 각자의 러너로 실행합니다 — 아래 "파트별 테스트 규칙" 참조.

## 파트별 테스트 규칙

| 파트 | 테스트 위치 | 도구·실행 | 규칙 |
|------|-------------|-----------|------|
| AI | `tests/` + `ros2_ws/.../test/` | `pytest tests/`, `colcon test` | 아래 2단계 전략 참조. 실기(추론·센서·주행) 검증은 Jetson에서만 가능 |
| FE | `frontend/` 내부 | Playwright(E2E), Storybook, MSW+orval 모킹 | BE 없이도 돌게 API는 MSW로 모킹. E2E는 핵심 유저 플로우(슬롯 보드·지도·추종 제어) 우선 |
| BE | `backend/src/test/` | JUnit 5 / Mockito, `./gradlew test` | 외부 의존(MySQL·MQTT Broker)은 모킹 또는 Testcontainers로 격리. MQTT↔WS 이벤트 변환 로직은 단위 테스트 필수 |
| EM | `embedded/` 내부 | 실기(HIL) 중심 | 하드웨어 없이 검증 가능한 로직(프로토콜 파싱, Differential Drive 계산 등)은 분리해서 단위 테스트. 센서·모터·MQTT 통신은 실기에서 체크리스트로 |

공통: 파트 간 **인터페이스 계약**(REST/WS/MQTT/토픽)을 바꾸는 변경은 해당 계약을 검증하는
테스트(스키마·페이로드 형식)를 함께 갱신하고, 정본 문서(API 명세서·JETSON_TO_STM.md)와 어긋나지 않는지 확인한다.

## 2단계 테스트 전략 (AI 파트)

| 위치 | 무엇을 테스트 | 실행 방법 | ROS 필요? |
|------|---------------|-----------|-----------|
| `tests/` (여기) | 순수 알고리즘 (PID, 코사인 유사도 등) | `pytest tests/` | ❌ |
| `ros2_ws/src/person_follow_robot/test/` | ament lint(PEP8/docstring), 통합 | `colcon test` | ✅ |

## 어떻게 ROS 없이 노드 코드를 테스트하나

`conftest.py`가 `rclpy`와 ROS 메시지 패키지의 **최소 스텁**을 `sys.modules`에 주입한 뒤
노드 파일 디렉토리를 `sys.path`에 추가합니다. 덕분에 `import control_node` 후
`PID` 같은 순수 클래스를 꺼내 검증할 수 있습니다.

## 새 테스트 추가 규칙

- **ROS 런타임에 의존하지 않는 순수 로직만** 여기에 둔다. 노드의 콜백/스핀/토픽 동작은 `colcon test`(패키지 `test/`)로.
- 새 순수 클래스(예: 필터, 좌표 변환, 유사도 계산)를 만들면 여기에 대응 테스트를 추가한다.
- 무거운 의존성(torch/cv2/ultralytics)을 import하는 코드는 이 계층에서 테스트하지 않는다 — 스텁이 비대해지고 깨지기 쉽다.
- 테스트 파일은 `test_*.py`, 함수는 `test_*` (pyproject.toml의 pytest 설정).
