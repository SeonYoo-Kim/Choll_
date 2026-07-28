# CLAUDE.md — ai/test/

AI 파트의 **프레임워크 독립(framework-independent) 로직 단위 테스트**의 집입니다.
ROS·TensorRT·GPU 설치 없이 순수 파이썬으로 실행됩니다.

```bash
pip install pytest        # 최초 1회
pytest ai/test/ -v        # 저장소 루트에서 실행
```

> **Windows 개발 PC 주의**: 이 팀의 Windows 개발 머신은 python이 PATH에 없고 miniforge에만 있다.
> `python`이 안 잡히면 전체 경로로 실행: `~/miniforge3/python.exe -m pytest ai/test/ -v`

> 파트 공통 테스트 규칙(파트별 위치·인터페이스 계약)은 [루트 tests/CLAUDE.md](../../tests/CLAUDE.md) 참조.

## 테스트 로그 (필수)

테스트를 실행했으면 — 에이전트든 사람이든, 통과든 실패든 — 결과를 [TEST_LOG.md](TEST_LOG.md)에 기록한다.
날짜·실행자·환경·명령·커밋과 함께 **원본 출력을 `<details>` 블록으로** 남겨, "통과했다"는 말을
사람이 눈으로 검증할 수 있게 한다. 형식은 TEST_LOG.md 상단 규칙 참조.

## 2단계 테스트 전략 (AI 파트)

| 위치 | 무엇을 테스트 | 실행 방법 | ROS 필요? |
|------|---------------|-----------|-----------|
| `ai/test/` (여기) | 순수 알고리즘 (PID, 좌표 변환, LiDAR 조회 등) | `pytest ai/test/` | ❌ |
| `ai/src/person_follow_robot/test/` | ament lint(PEP8/docstring), 통합 | `colcon test` | ✅ |

`ai/src/person_follow_robot/test/`는 colcon이 실행하는 패키지 테스트로, 현재 ament lint 위주 — **현상유지**.
순수 로직 테스트는 전부 여기(`ai/test/`)에 둔다.

## 어떻게 ROS 없이 노드 코드를 테스트하나

`conftest.py`가 `rclpy`와 ROS 메시지 패키지의 **최소 스텁**을 `sys.modules`에 주입한 뒤
노드 파일 디렉토리(`../src/person_follow_robot/person_follow_robot`)를 `sys.path`에 추가합니다.
덕분에 `import control_node` 후 `PID` 같은 순수 클래스를 꺼내 검증할 수 있습니다.
노드가 새 rclpy 하위 모듈·메시지 타입을 import하면 conftest 스텁에도 추가해야 합니다.

## 새 테스트 추가 규칙

- **ROS 런타임에 의존하지 않는 순수 로직만** 여기에 둔다. 노드의 콜백/스핀/토픽 동작은 `colcon test`(패키지 `test/`)로.
- 새 순수 함수/클래스(예: 필터, 좌표 변환, 유사도 계산)를 만들면 여기에 대응 테스트를 추가한다.
- 무거운 의존성(torch/cv2/ultralytics)을 import하는 코드는 이 계층에서 테스트하지 않는다 — 스텁이 비대해지고 깨지기 쉽다.
- 테스트 파일은 `test_*.py`, 함수는 `test_*` (pyproject.toml의 pytest 설정).
- 이 디렉토리는 colcon 패키지가 아니므로(`package.xml` 없음) `colcon build`에는 영향을 주지 않는다.
