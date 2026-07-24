# Test Log

테스트 실행 기록입니다. **에이전트(Claude)든 사람이든, 테스트를 돌렸으면 결과를 여기에 남깁니다.**
목적: "테스트 통과했다"는 말을 사람이 눈으로 검증할 수 있게 하는 것.

## 기록 규칙

- **최신 항목이 맨 위** (이 문단 바로 아래에 추가).
- 항목 형식: `## 날짜 시각 — 결과 요약 (실행자)` + 환경·명령·커밋 + 접힌 전체 출력(`<details>`).
- **실패도 기록한다.** 실패 → 수정 → 재실행이면 두 번 다 남겨서 이력이 보이게 한다.
- 원본 출력은 `<details>` 블록에 그대로 붙인다 (요약만 믿지 말고 검증 가능하게).

---

## 2026-07-24 14:37 — ✅ 12 passed (Claude)

- **명령**: `pytest tests/ -v`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1
- **커밋**: `ee8bab4` ([chore] ros2_ws→ai 잔여 경로 정리 및 구버전 루트 문서 삭제)
- **맥락**: `ros2_ws` → `ai` 디렉토리 이름 변경 후 conftest.py의 노드 import 경로 수정 검증.
  수정 전에는 conftest.py가 존재하지 않는 `ros2_ws/...` 경로를 참조해 테스트 수집이 불가능한 상태였음.
- **함께 실행**: `ruff check .` → 66건 (전부 노드 소스의 기존 이슈 — E501·docstring 등. 이번 변경 파일과 무관)

<details>
<summary>pytest 전체 출력</summary>

```
============================= test session starts =============================
platform win32 -- Python 3.12.12, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\SSAFY\miniforge3\python.exe
cachedir: .pytest_cache
rootdir: C:\SSAFY\workspace\Choll
configfile: pyproject.toml
plugins: anyio-4.14.1
collecting ... collected 12 items

tests/test_control_logic.py::TestNormalizeCenterX::test_image_center_maps_to_zero PASSED [  8%]
tests/test_control_logic.py::TestNormalizeCenterX::test_left_edge_maps_to_minus_one PASSED [ 16%]
tests/test_control_logic.py::TestNormalizeCenterX::test_right_edge_maps_to_plus_one PASSED [ 25%]
tests/test_control_logic.py::TestNormalizeCenterX::test_quarter_position PASSED [ 33%]
tests/test_control_logic.py::TestNormalizeCenterX::test_out_of_frame_is_clamped PASSED [ 41%]
tests/test_control_logic.py::TestNormalizeCenterX::test_non_positive_width_raises PASSED [ 50%]
tests/test_control_logic.py::TestPidReset::test_reset_clears_integral_and_derivative_state PASSED [ 58%]
tests/test_pid.py::test_proportional_term_only PASSED                    [ 66%]
tests/test_pid.py::test_output_is_clamped_to_limit PASSED                [ 75%]
tests/test_pid.py::test_integral_accumulates_over_time PASSED            [ 83%]
tests/test_pid.py::test_derivative_responds_to_error_change PASSED       [ 91%]
tests/test_pid.py::test_zero_dt_disables_derivative PASSED               [100%]

============================= 12 passed in 0.05s ==============================
```

</details>
