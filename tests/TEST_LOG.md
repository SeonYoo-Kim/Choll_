# Test Log

테스트 실행 기록입니다. **에이전트(Claude)든 사람이든, 테스트를 돌렸으면 결과를 여기에 남깁니다.**
목적: "테스트 통과했다"는 말을 사람이 눈으로 검증할 수 있게 하는 것.

## 기록 규칙

- **최신 항목이 맨 위** (이 문단 바로 아래에 추가).
- 항목 형식: `## 날짜 시각 — 결과 요약 (실행자)` + 환경·명령·커밋 + 접힌 전체 출력(`<details>`).
- **실패도 기록한다.** 실패 → 수정 → 재실행이면 두 번 다 남겨서 이력이 보이게 한다.
- 원본 출력은 `<details>` 블록에 그대로 붙인다 (요약만 믿지 말고 검증 가능하게).

---

## 2026-07-28 08:53 — ✅ 26 passed, ruff 변경 파일 0건 (Claude)

- **명령**: `pytest tests/` + `ruff check debug_visualization_node.py`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: `53d8f01` 기준 작업 트리 (라벨 화면 안 clamp, 커밋 전)
- **맥락**: 바운딩박스가 프레임 밖으로 나가면 거리/ID 라벨이 화면 밖에 그려져
  보이지 않는 문제 수정. `_draw_label`(모든 라벨 공통 진입점)에서 배경 사각형이
  프레임 안에 완전히 들어오도록 x·y를 clamp. cv2 의존 그리기 로직이라 순수 테스트
  없음 → 기존 26개 회귀만 확인, 표시 확인은 Jetson 실기.

<details>
<summary>pytest 출력 (마지막 줄)</summary>

```
============================= 26 passed in 0.03s ==============================
```

</details>

## 2026-07-28 08:42 — ✅ 26 passed, ruff 변경 파일 0건 (Claude)

- **명령**: `pytest tests/` + `ruff check control_node.py conftest.py`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: `53d8f01` 기준 작업 트리 (/scan QoS 수정, 커밋 전)
- **맥락**: Jetson 실기에서 영상에 `NO LIDAR`가 찍힌 문제 수정 검증.
  원인: ydlidar 드라이버는 BEST_EFFORT(sensor QoS)로 발행하는데 control_node가
  기본 RELIABLE로 구독 → QoS 비호환으로 /scan 미수신.
  - control_node: /scan 구독을 `qos_profile_sensor_data`(BEST_EFFORT)로 변경.
  - 거리 획득 실패 경고에 원인 구분 추가 (/scan 미수신 vs 유효 range 없음).
  - conftest.py에 `rclpy.qos` 스텁 추가 (미추가 시 import 실패).
  - 순수 로직 변경 없음 → 기존 26개 회귀 확인. QoS 매칭 자체는 Jetson 실기 검증 필요.

<details>
<summary>pytest 출력 (마지막 줄)</summary>

```
============================= 26 passed in 0.06s ==============================
```

</details>

## 2026-07-27 17:30 — ✅ 26 passed, ruff 변경 파일 0건 (Claude)

- **명령**: `pytest tests/ -v` + `ruff check control_node.py debug_visualization_node.py`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: `36cc4dd` 기준 작업 트리 (거리 표시 NaN 폴백 추가, 커밋 전)
- **맥락**: 실기에서 result.mp4에 거리 라벨이 안 찍힌 문제의 후속 수정 검증.
  원인 추정: LiDAR 거리 측정 실패 시 `/target_distance`를 아예 발행하지 않아
  디버그 노드가 표시할 데이터가 없었음.
  - control_node: 타겟이 보이는데 측정 실패면 NaN 발행 (미검출 시엔 여전히 미발행).
  - debug_visualization_node: NaN → 박스 우상단 `NO LIDAR`, 수신 없음 → 배너 `DIST: --`,
    정상 → `X.XXm`. 상단 배너에 `DIST:` 항목 상시 추가.
  - 순수 로직 변경 없음 → 기존 26개로 회귀 확인. 실기 검증은 Jetson에서 필요.

<details>
<summary>pytest 출력 (마지막 8줄)</summary>

```
tests/test_motor_logic.py::TestValidation::test_negative_max_rpm_raises PASSED [ 80%]
tests/test_pid.py::test_proportional_term_only PASSED                    [ 84%]
tests/test_pid.py::test_output_is_clamped_to_limit PASSED                [ 88%]
tests/test_pid.py::test_integral_accumulates_over_time PASSED            [ 92%]
tests/test_pid.py::test_derivative_responds_to_error_change PASSED       [ 96%]
tests/test_pid.py::test_zero_dt_disables_derivative PASSED               [100%]

============================= 26 passed in 0.05s ==============================
```

</details>

## 2026-07-27 17:11 — ✅ 26 passed, ruff 변경 파일 0건 (Claude)

- **명령**: `pytest tests/ -v` + `ruff check <변경 파일들>`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **커밋**: `36cc4dd` 기준 작업 트리 (디버그 영상 거리 표시 기능, 커밋 전)
- **맥락**: 디버그 영상의 타겟 바운딩박스 우상단에 LiDAR 측정 거리(m) 표시 기능 검증.
  - control_node: 측정 거리를 `/target_distance`(std_msgs/Float32)로 발행.
  - debug_visualization_node: 구독 후 타겟 박스 우상단에 `X.XXm` 라벨
    (staleness 타임아웃 `distance_display_timeout_sec`=1s 초과 시 숨김).
  - conftest.py 스텁에 `Float32` 추가 — 추가 전에는 control_node import 실패로
    테스트 수집 자체가 깨졌음 (해당 실행도 아래 이력 참조).
  - 새 순수 로직 없음(발행/구독+cv2 그리기) → 신규 pytest 케이스 없이 기존 26개로 회귀 확인.
- **ruff**: 변경 파일(control_node·debug_visualization_node·launch·conftest) `All checks passed!`
  (debug_visualization_node의 기존 lint 이슈 — frame 타입 힌트, import 정렬, docstring —
  이번 기회에 함께 정리. `ruff format --check`의 저장소 기존 포맷 드리프트는 미변경.)

<details>
<summary>1차 실행 — ❌ 수집 에러 (conftest 스텁에 Float32 부재)</summary>

```
ERROR collecting tests/test_control_logic.py
ai\src\person_follow_robot\person_follow_robot\control_node.py:29: in <module>
    from std_msgs.msg import Float32
E   ImportError: cannot import name 'Float32' from 'std_msgs.msg' (unknown location)
ERROR collecting tests/test_pid.py
    (동일 원인)
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!
============================== 2 errors in 0.17s ==============================
```

</details>

<details>
<summary>2차 실행 — pytest 전체 출력</summary>

```
============================= test session starts =============================
platform win32 -- Python 3.12.12, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\SSAFY\miniforge3\python.exe
cachedir: .pytest_cache
rootdir: C:\SSAFY\workspace\Choll
configfile: pyproject.toml
plugins: anyio-4.14.1
collecting ... collected 26 items

tests/test_control_logic.py::TestNormalizeCenterX::test_image_center_maps_to_zero PASSED [  3%]
tests/test_control_logic.py::TestNormalizeCenterX::test_left_edge_maps_to_minus_one PASSED [  7%]
tests/test_control_logic.py::TestNormalizeCenterX::test_right_edge_maps_to_plus_one PASSED [ 11%]
tests/test_control_logic.py::TestNormalizeCenterX::test_quarter_position PASSED [ 15%]
tests/test_control_logic.py::TestNormalizeCenterX::test_out_of_frame_is_clamped PASSED [ 19%]
tests/test_control_logic.py::TestNormalizeCenterX::test_non_positive_width_raises PASSED [ 23%]
tests/test_control_logic.py::TestCameraBearingToLidarAngle::test_center_maps_to_zero PASSED [ 26%]
tests/test_control_logic.py::TestCameraBearingToLidarAngle::test_right_edge_is_negative_half_fov PASSED [ 30%]
tests/test_control_logic.py::TestCameraBearingToLidarAngle::test_left_edge_is_positive_half_fov PASSED [ 34%]
tests/test_control_logic.py::TestCameraBearingToLidarAngle::test_mount_offset_shifts_lookup_angle PASSED [ 38%]
tests/test_control_logic.py::TestPidReset::test_reset_clears_integral_and_derivative_state PASSED [ 42%]
tests/test_motor_logic.py::TestStraightLine::test_forward_gives_equal_positive_rpms PASSED [ 46%]
tests/test_motor_logic.py::TestStraightLine::test_backward_gives_equal_negative_rpms PASSED [ 50%]
tests/test_motor_logic.py::TestRotation::test_left_turn_makes_right_wheel_faster PASSED [ 53%]
tests/test_motor_logic.py::TestRotation::test_spin_in_place_wheels_are_opposite PASSED [ 57%]
tests/test_motor_logic.py::TestClamping::test_peak_clamped_to_max_rpm PASSED [ 61%]
tests/test_motor_logic.py::TestClamping::test_clamp_preserves_left_right_ratio PASSED [ 65%]
tests/test_motor_logic.py::TestClamping::test_zero_command_is_zero PASSED [ 69%]
tests/test_motor_logic.py::TestValidation::test_non_positive_radius_raises PASSED [ 73%]
tests/test_motor_logic.py::TestValidation::test_non_positive_separation_raises PASSED [ 76%]
tests/test_motor_logic.py::TestValidation::test_negative_max_rpm_raises PASSED [ 80%]
tests/test_pid.py::test_proportional_term_only PASSED                    [ 84%]
tests/test_pid.py::test_output_is_clamped_to_limit PASSED                [ 88%]
tests/test_pid.py::test_integral_accumulates_over_time PASSED            [ 92%]
tests/test_pid.py::test_derivative_responds_to_error_change PASSED       [ 96%]
tests/test_pid.py::test_zero_dt_disables_derivative PASSED               [100%]

============================= 26 passed in 0.03s ==============================
```

</details>

## 2026-07-24 16:43 — ✅ 26 passed, ruff 변경 파일 0건 (Claude)

- **명령**: `pytest tests/ -v` + `ruff check <변경 파일들>`
- **환경**: Windows 11 개발 PC, Python 3.12.12 (miniforge base), pytest 9.1.1, ruff 0.16.0
- **맥락**: motor_node 차동구동 역기구학 구현(+14 테스트) 및 control_node LiDAR 조회
  각도 부호 버그 수정(+카메라 방위각→LiDAR 각도 변환 함수 분리) 검증.
  - `test_motor_logic.py` 신규 11개: 직진/후진 RPM, 좌회전 시 오른쪽 바퀴 가속(REP 103),
    제자리 회전 부호, max_rpm 클램핑(좌우 비율 보존), 입력 검증.
  - `test_control_logic.py`에 `camera_bearing_to_lidar_angle` 4개 추가: 중앙=0,
    화면 오른쪽=음의 방위각, 장착 오프셋 반영.
- **ruff**: 변경 파일(motor_node·control_node·launch·tests/) 기준 `All checks passed!`
  (저장소 전체에는 다른 노드의 기존 이슈 잔존)

<details>
<summary>pytest 전체 출력</summary>

```
============================= test session starts =============================
platform win32 -- Python 3.12.12, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\SSAFY\miniforge3\python.exe
cachedir: .pytest_cache
rootdir: C:\SSAFY\workspace\Choll
configfile: pyproject.toml
plugins: anyio-4.14.1
collecting ... collected 26 items

tests/test_control_logic.py::TestNormalizeCenterX::test_image_center_maps_to_zero PASSED [  3%]
tests/test_control_logic.py::TestNormalizeCenterX::test_left_edge_maps_to_minus_one PASSED [  7%]
tests/test_control_logic.py::TestNormalizeCenterX::test_right_edge_maps_to_plus_one PASSED [ 11%]
tests/test_control_logic.py::TestNormalizeCenterX::test_quarter_position PASSED [ 15%]
tests/test_control_logic.py::TestNormalizeCenterX::test_out_of_frame_is_clamped PASSED [ 19%]
tests/test_control_logic.py::TestNormalizeCenterX::test_non_positive_width_raises PASSED [ 23%]
tests/test_control_logic.py::TestCameraBearingToLidarAngle::test_center_maps_to_zero PASSED [ 26%]
tests/test_control_logic.py::TestCameraBearingToLidarAngle::test_right_edge_is_negative_half_fov PASSED [ 30%]
tests/test_control_logic.py::TestCameraBearingToLidarAngle::test_left_edge_is_positive_half_fov PASSED [ 34%]
tests/test_control_logic.py::TestCameraBearingToLidarAngle::test_mount_offset_shifts_lookup_angle PASSED [ 38%]
tests/test_control_logic.py::TestPidReset::test_reset_clears_integral_and_derivative_state PASSED [ 42%]
tests/test_motor_logic.py::TestStraightLine::test_forward_gives_equal_positive_rpms PASSED [ 46%]
tests/test_motor_logic.py::TestStraightLine::test_backward_gives_equal_negative_rpms PASSED [ 50%]
tests/test_motor_logic.py::TestRotation::test_left_turn_makes_right_wheel_faster PASSED [ 53%]
tests/test_motor_logic.py::TestRotation::test_spin_in_place_wheels_are_opposite PASSED [ 57%]
tests/test_motor_logic.py::TestClamping::test_peak_clamped_to_max_rpm PASSED [ 61%]
tests/test_motor_logic.py::TestClamping::test_clamp_preserves_left_right_ratio PASSED [ 65%]
tests/test_motor_logic.py::TestClamping::test_zero_command_is_zero PASSED [ 69%]
tests/test_motor_logic.py::TestValidation::test_non_positive_radius_raises PASSED [ 73%]
tests/test_motor_logic.py::TestValidation::test_non_positive_separation_raises PASSED [ 76%]
tests/test_motor_logic.py::TestValidation::test_negative_max_rpm_raises PASSED [ 80%]
tests/test_pid.py::test_proportional_term_only PASSED                    [ 84%]
tests/test_pid.py::test_output_is_clamped_to_limit PASSED                [ 88%]
tests/test_pid.py::test_integral_accumulates_over_time PASSED            [ 92%]
tests/test_pid.py::test_derivative_responds_to_error_change PASSED       [ 96%]
tests/test_pid.py::test_zero_dt_disables_derivative PASSED               [100%]

============================= 26 passed in 0.06s ==============================
```

</details>

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
