# CLAUDE.md — tests/

**프레임워크 독립(framework-independent) 로직 단위 테스트**의 집입니다.
ROS·TensorRT·GPU 설치 없이 순수 파이썬으로 실행됩니다.

```bash
pip install pytest        # 최초 1회
pytest tests/ -v
```

## 2단계 테스트 전략

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
