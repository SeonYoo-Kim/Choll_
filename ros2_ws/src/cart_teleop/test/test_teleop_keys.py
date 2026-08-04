"""teleop_keys 순수 로직 단위 테스트 — ROS·터미널·하드웨어 없이 돌아간다.

시각을 인자로 넣으므로 command lease 경계를 결정적으로 만들 수 있다.

실행::

    cd ros2_ws
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 -m pytest src/cart_teleop/test/test_teleop_keys.py -v
"""

import ast
from pathlib import Path

import pytest

from cart_teleop.teleop_keys import (
    DEFAULT_INPUT_TIMEOUT_SEC,
    DEFAULT_MAX_ANGULAR_RPS,
    DEFAULT_MAX_LINEAR_MPS,
    KEY_BACKWARD,
    KEY_ESCAPE,
    KEY_FORWARD,
    KEY_QUIT,
    KEY_SPEED_DOWN,
    KEY_SPEED_UP,
    KEY_SPEED_UP_ALIAS,
    KEY_STOP,
    KEY_TURN_LEFT,
    KEY_TURN_RIGHT,
    TeleopState,
    TeleopStatus,
)

T0 = 1000.0


def _state(**kwargs: float) -> TeleopState:
    """기본 파라미터로 상태를 만든다 (개별 인자만 덮어쓴다)."""
    return TeleopState(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 기본값
# ---------------------------------------------------------------------------


def test_defaults_match_the_verified_slow_profile_range() -> None:
    """기본 상한은 2026-08-04 실기에서 확인한 범위와 같다."""
    assert DEFAULT_MAX_LINEAR_MPS == pytest.approx(0.13)
    assert DEFAULT_MAX_ANGULAR_RPS == pytest.approx(0.60)
    assert DEFAULT_INPUT_TIMEOUT_SEC == pytest.approx(1.0)


def test_starts_stopped_at_max_speed_step() -> None:
    """시작 상태는 STOPPED 이고 속도 단계는 최대(=기본 속도)다."""
    state = _state()

    command = state.evaluate(T0)

    assert command.status is TeleopStatus.STOPPED
    assert command.is_zero
    assert command.speed_step == command.speed_step_count
    assert command.last_key_label == ""
    assert command.lease_remaining_sec is None


# ---------------------------------------------------------------------------
# W/S/A/D 값과 REP 103 부호
# ---------------------------------------------------------------------------


def test_forward_is_positive_linear_only() -> None:
    """W: linear.x 양수, angular.z 는 0 (선속도·각속도를 섞지 않는다)."""
    state = _state()
    state.handle_key(KEY_FORWARD, T0)

    command = state.evaluate(T0)

    assert command.status is TeleopStatus.ARMED
    assert command.linear_x == pytest.approx(DEFAULT_MAX_LINEAR_MPS)
    assert command.linear_x > 0.0
    assert command.angular_z == 0.0


def test_backward_is_negative_linear_only() -> None:
    """S: linear.x 음수, angular.z 는 0."""
    state = _state()
    state.handle_key(KEY_BACKWARD, T0)

    command = state.evaluate(T0)

    assert command.linear_x == pytest.approx(-DEFAULT_MAX_LINEAR_MPS)
    assert command.linear_x < 0.0
    assert command.angular_z == 0.0


def test_turn_left_is_positive_angular_only_rep103() -> None:
    """A: REP 103 기준 반시계(좌회전)는 angular.z **양수**. linear.x 는 0."""
    state = _state()
    state.handle_key(KEY_TURN_LEFT, T0)

    command = state.evaluate(T0)

    assert command.angular_z == pytest.approx(DEFAULT_MAX_ANGULAR_RPS)
    assert command.angular_z > 0.0
    assert command.linear_x == 0.0


def test_turn_right_is_negative_angular_only_rep103() -> None:
    """D: 시계(우회전)는 angular.z **음수**. linear.x 는 0."""
    state = _state()
    state.handle_key(KEY_TURN_RIGHT, T0)

    command = state.evaluate(T0)

    assert command.angular_z == pytest.approx(-DEFAULT_MAX_ANGULAR_RPS)
    assert command.angular_z < 0.0
    assert command.linear_x == 0.0


@pytest.mark.parametrize("key", [KEY_FORWARD, KEY_BACKWARD, KEY_TURN_LEFT, KEY_TURN_RIGHT])
def test_motion_never_mixes_linear_and_angular(key: str) -> None:
    """어떤 주행 키에서도 선속도와 각속도가 동시에 0 이 아닌 경우는 없다."""
    state = _state()
    state.handle_key(key, T0)

    command = state.evaluate(T0)

    assert (command.linear_x == 0.0) or (command.angular_z == 0.0)


def test_motion_keys_are_case_insensitive() -> None:
    """대문자 W 도 전진으로 처리한다."""
    state = _state()
    state.handle_key("W", T0)

    assert state.evaluate(T0).status is TeleopStatus.ARMED


def test_later_motion_key_replaces_the_previous_one() -> None:
    """나중에 누른 주행 키가 이전 것을 대체한다."""
    state = _state()
    state.handle_key(KEY_FORWARD, T0)
    state.handle_key(KEY_TURN_RIGHT, T0 + 0.1)

    command = state.evaluate(T0 + 0.1)

    assert command.linear_x == 0.0
    assert command.angular_z < 0.0


# ---------------------------------------------------------------------------
# Space 즉시 정지
# ---------------------------------------------------------------------------


def test_space_stops_immediately() -> None:
    """Space 는 즉시 zero 로 만든다 (lease 가 남아 있어도)."""
    state = _state()
    state.handle_key(KEY_FORWARD, T0)
    assert state.evaluate(T0).status is TeleopStatus.ARMED

    state.handle_key(KEY_STOP, T0 + 0.1)
    command = state.evaluate(T0 + 0.1)

    assert command.status is TeleopStatus.STOPPED
    assert command.is_zero


def test_space_requires_new_key_to_move_again() -> None:
    """Space 이후에는 시간이 흘러도 스스로 다시 움직이지 않는다."""
    state = _state()
    state.handle_key(KEY_FORWARD, T0)
    state.handle_key(KEY_STOP, T0 + 0.1)

    assert state.evaluate(T0 + 0.2).is_zero
    assert state.evaluate(T0 + 0.5).is_zero

    state.handle_key(KEY_FORWARD, T0 + 0.6)
    assert state.evaluate(T0 + 0.6).status is TeleopStatus.ARMED


# ---------------------------------------------------------------------------
# command lease 경계값
# ---------------------------------------------------------------------------


def test_lease_is_active_just_before_timeout() -> None:
    """경과 < timeout 이면 ARMED 를 유지한다."""
    state = _state(input_timeout_sec=1.0)
    state.handle_key(KEY_FORWARD, T0)

    command = state.evaluate(T0 + 0.999)

    assert command.status is TeleopStatus.ARMED
    assert command.lease_remaining_sec == pytest.approx(0.001)


def test_lease_expires_exactly_at_timeout_boundary() -> None:
    """★ 경과 == timeout 이면 TIMEOUT 이다 — 애매한 순간에는 정지를 택한다."""
    state = _state(input_timeout_sec=1.0)
    state.handle_key(KEY_FORWARD, T0)

    command = state.evaluate(T0 + 1.0)

    assert command.status is TeleopStatus.TIMEOUT
    assert command.is_zero
    assert command.lease_remaining_sec is None


def test_lease_expired_stays_zero_without_new_key() -> None:
    """timeout 이후에는 새 키 없이 다시 움직이지 않는다."""
    state = _state(input_timeout_sec=1.0)
    state.handle_key(KEY_FORWARD, T0)
    assert state.evaluate(T0 + 1.0).status is TeleopStatus.TIMEOUT

    assert state.evaluate(T0 + 1.1).is_zero
    assert state.evaluate(T0 + 5.0).is_zero


def test_repeated_key_refreshes_the_lease() -> None:
    """OS 자동반복처럼 같은 키가 반복되면 lease 가 갱신된다."""
    state = _state(input_timeout_sec=1.0)
    state.handle_key(KEY_FORWARD, T0)
    state.handle_key(KEY_FORWARD, T0 + 0.9)

    # 첫 입력만 있었다면 T0+1.0 에서 만료됐을 시점.
    command = state.evaluate(T0 + 1.5)

    assert command.status is TeleopStatus.ARMED
    assert command.lease_remaining_sec == pytest.approx(0.4)


def test_speed_keys_do_not_refresh_the_lease() -> None:
    """속도 단계 키는 lease 를 갱신하지 않는다 — 주행 의도는 방향 키에만 있다."""
    state = _state(input_timeout_sec=1.0)
    state.handle_key(KEY_FORWARD, T0)
    state.handle_key(KEY_SPEED_DOWN, T0 + 0.9)

    assert state.evaluate(T0 + 1.0).status is TeleopStatus.TIMEOUT


# ---------------------------------------------------------------------------
# 알 수 없는 키 무시
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["x", "e", "1", "\t", "\n", "?", "Z", "["])
def test_unknown_keys_change_nothing(key: str) -> None:
    """알 수 없는 키는 상태·속도·마지막 키 라벨을 바꾸지 않는다."""
    state = _state()
    state.handle_key(KEY_FORWARD, T0)
    before = state.evaluate(T0)

    state.handle_key(key, T0 + 0.1)
    after = state.evaluate(T0 + 0.1)

    assert after.status is before.status
    assert after.linear_x == pytest.approx(before.linear_x)
    assert after.angular_z == pytest.approx(before.angular_z)
    assert after.speed_step == before.speed_step
    assert after.last_key_label == before.last_key_label


def test_unknown_key_does_not_arm_from_stopped() -> None:
    """정지 상태에서 알 수 없는 키를 눌러도 움직이지 않는다."""
    state = _state()
    state.handle_key("k", T0)

    assert state.evaluate(T0).status is TeleopStatus.STOPPED


# ---------------------------------------------------------------------------
# 속도 단계 clamp
# ---------------------------------------------------------------------------


def test_speed_step_starts_at_maximum() -> None:
    """기본 단계는 최대이며 그 값이 요구된 기본 속도다."""
    state = _state(speed_step_count=5)

    assert state.speed_step == 5
    assert state.speed_scale() == pytest.approx(1.0)


def test_speed_up_at_maximum_is_clamped() -> None:
    """최대에서 + 를 더 눌러도 최대를 넘지 않는다."""
    state = _state(speed_step_count=5)
    for _ in range(3):
        state.handle_key(KEY_SPEED_UP, T0)

    assert state.speed_step == 5


def test_speed_down_at_minimum_is_clamped() -> None:
    """최소(1)에서 - 를 더 눌러도 0 이나 음수가 되지 않는다."""
    state = _state(speed_step_count=5)
    for _ in range(10):
        state.handle_key(KEY_SPEED_DOWN, T0)

    assert state.speed_step == 1
    assert state.speed_scale() > 0.0


def test_speed_can_be_lowered_then_raised_back_to_maximum() -> None:
    """내렸다가 다시 올릴 수 있고, 최대값을 넘지 않는다."""
    state = _state(speed_step_count=5)
    state.handle_key(KEY_SPEED_DOWN, T0)
    state.handle_key(KEY_SPEED_DOWN, T0)
    assert state.speed_step == 3

    for _ in range(5):
        state.handle_key(KEY_SPEED_UP, T0)

    assert state.speed_step == 5
    state.handle_key(KEY_FORWARD, T0)
    assert state.evaluate(T0).linear_x == pytest.approx(DEFAULT_MAX_LINEAR_MPS)


def test_lowered_speed_scales_both_axes() -> None:
    """단계를 내리면 선속도·각속도가 같은 비율로 줄어든다."""
    state = _state(speed_step_count=5)
    state.handle_key(KEY_SPEED_DOWN, T0)  # 5 -> 4

    state.handle_key(KEY_FORWARD, T0)
    assert state.evaluate(T0).linear_x == pytest.approx(DEFAULT_MAX_LINEAR_MPS * 0.8)

    state.handle_key(KEY_TURN_LEFT, T0)
    assert state.evaluate(T0).angular_z == pytest.approx(DEFAULT_MAX_ANGULAR_RPS * 0.8)


def test_equals_key_is_an_alias_for_plus() -> None:
    """★ `=` 는 `+` 와 동일하게 속도 단계를 올린다 (Shift 없이 조작하기 위한 별칭)."""
    assert KEY_SPEED_UP_ALIAS == "="

    state = _state(speed_step_count=5)
    state.handle_key(KEY_SPEED_DOWN, T0)
    state.handle_key(KEY_SPEED_DOWN, T0)
    assert state.speed_step == 3

    state.handle_key(KEY_SPEED_UP_ALIAS, T0)

    assert state.speed_step == 4


def test_equals_and_plus_produce_identical_state() -> None:
    """`=` 만 쓴 상태와 `+` 만 쓴 상태가 완전히 같다 (속도·발행값 모두)."""
    with_plus = _state(speed_step_count=5)
    with_equals = _state(speed_step_count=5)

    for _ in range(3):
        with_plus.handle_key(KEY_SPEED_DOWN, T0)
        with_equals.handle_key(KEY_SPEED_DOWN, T0)
    with_plus.handle_key(KEY_SPEED_UP, T0)
    with_equals.handle_key(KEY_SPEED_UP_ALIAS, T0)

    assert with_equals.speed_step == with_plus.speed_step
    assert with_equals.speed_scale() == pytest.approx(with_plus.speed_scale())

    with_plus.handle_key(KEY_FORWARD, T0)
    with_equals.handle_key(KEY_FORWARD, T0)
    plus_command = with_plus.evaluate(T0)
    equals_command = with_equals.evaluate(T0)

    assert equals_command.linear_x == pytest.approx(plus_command.linear_x)
    assert equals_command.angular_z == pytest.approx(plus_command.angular_z)
    assert equals_command.status is plus_command.status


def test_equals_key_is_clamped_at_maximum() -> None:
    """`=` 로도 최대 단계를 넘지 않는다."""
    state = _state(speed_step_count=5)
    for _ in range(8):
        state.handle_key(KEY_SPEED_UP_ALIAS, T0)

    assert state.speed_step == 5
    state.handle_key(KEY_FORWARD, T0)
    assert state.evaluate(T0).linear_x == pytest.approx(DEFAULT_MAX_LINEAR_MPS)


def test_equals_key_does_not_refresh_the_lease() -> None:
    """`=` 도 속도 키이므로 lease 를 갱신하지 않는다 (`+` 와 동일)."""
    state = _state(input_timeout_sec=1.0)
    state.handle_key(KEY_FORWARD, T0)
    state.handle_key(KEY_SPEED_UP_ALIAS, T0 + 0.9)

    assert state.evaluate(T0 + 1.0).status is TeleopStatus.TIMEOUT


def test_equals_key_shows_its_own_label() -> None:
    """마지막 입력 키 표시는 실제로 누른 키(`=`)를 보여준다."""
    state = _state()
    state.handle_key(KEY_SPEED_UP_ALIAS, T0)

    label = state.evaluate(T0).last_key_label
    assert "=" in label


@pytest.mark.parametrize("step_count", [1, 2, 5, 10])
def test_speed_never_exceeds_the_configured_maximum(step_count: int) -> None:
    """★ 어떤 단계 수·어떤 조작 순서에서도 상한을 넘지 않는다."""
    state = _state(speed_step_count=step_count)
    for _ in range(step_count * 3):
        state.handle_key(KEY_SPEED_UP, T0)

    for key in (KEY_FORWARD, KEY_BACKWARD, KEY_TURN_LEFT, KEY_TURN_RIGHT):
        state.handle_key(key, T0)
        command = state.evaluate(T0)
        assert abs(command.linear_x) <= DEFAULT_MAX_LINEAR_MPS + 1e-12
        assert abs(command.angular_z) <= DEFAULT_MAX_ANGULAR_RPS + 1e-12


# ---------------------------------------------------------------------------
# 종료 상태는 항상 zero
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", [KEY_QUIT, KEY_ESCAPE])
def test_quit_keys_request_quit_and_zero(key: str) -> None:
    """q / Esc 는 종료를 요청하고 즉시 zero 로 만든다."""
    state = _state()
    state.handle_key(KEY_FORWARD, T0)

    state.handle_key(key, T0 + 0.1)
    command = state.evaluate(T0 + 0.1)

    assert state.quit_requested is True
    assert command.status is TeleopStatus.QUIT
    assert command.is_zero


def test_quit_stays_zero_afterwards() -> None:
    """종료 요청 후에는 어떤 시각·어떤 키에도 zero 를 유지한다."""
    state = _state()
    state.handle_key(KEY_QUIT, T0)

    state.handle_key(KEY_FORWARD, T0 + 0.1)
    assert state.evaluate(T0 + 0.1).is_zero
    assert state.evaluate(T0 + 10.0).is_zero


def test_request_quit_from_signal_zeroes_output() -> None:
    """외부 신호(SIGINT 등) 경로도 zero 를 보장한다."""
    state = _state()
    state.handle_key(KEY_FORWARD, T0)

    state.request_quit()
    command = state.evaluate(T0)

    assert command.status is TeleopStatus.QUIT
    assert command.is_zero


# ---------------------------------------------------------------------------
# 외부 /cmd_vel Publisher 충돌 차단
# ---------------------------------------------------------------------------


def test_external_publisher_disarms_and_zeroes() -> None:
    """★ 외부 Publisher 가 감지되면 즉시 DISARMED + zero 다."""
    state = _state()
    state.handle_key(KEY_FORWARD, T0)
    assert state.evaluate(T0).status is TeleopStatus.ARMED

    state.set_external_publisher_count(1)
    command = state.evaluate(T0)

    assert command.status is TeleopStatus.DISARMED
    assert command.is_zero
    assert command.external_publisher_count == 1


def test_motion_keys_are_blocked_while_disarmed() -> None:
    """DISARMED 중에는 주행 키를 눌러도 non-zero 가 되지 않는다."""
    state = _state()
    state.set_external_publisher_count(2)

    state.handle_key(KEY_FORWARD, T0)
    command = state.evaluate(T0)

    assert command.status is TeleopStatus.DISARMED
    assert command.is_zero
    # 라벨은 갱신해 사용자가 입력이 먹히지 않는 이유를 화면에서 알 수 있게 한다.
    assert command.last_key_label != ""


def test_clearing_conflict_does_not_auto_resume() -> None:
    """★ 충돌이 사라져도 자동 재가동하지 않는다 — 새 키가 있어야 움직인다."""
    state = _state()
    state.handle_key(KEY_FORWARD, T0)
    state.set_external_publisher_count(1)
    state.handle_key(KEY_FORWARD, T0 + 0.1)  # 충돌 중 입력 — 저장되지 않아야 한다

    state.set_external_publisher_count(0)
    assert state.evaluate(T0 + 0.2).status is TeleopStatus.STOPPED
    assert state.evaluate(T0 + 0.2).is_zero

    state.handle_key(KEY_FORWARD, T0 + 0.3)
    assert state.evaluate(T0 + 0.3).status is TeleopStatus.ARMED


def test_negative_external_count_is_treated_as_zero() -> None:
    """음수 Publisher 수(계산 오차)는 0 으로 취급해 오작동하지 않는다."""
    state = _state()
    state.set_external_publisher_count(-1)

    assert state.disarmed is False
    assert state.external_publisher_count == 0


def test_quit_takes_priority_over_disarmed() -> None:
    """종료 요청이 DISARMED 보다 우선한다 (둘 다 zero 지만 상태 표시가 다르다)."""
    state = _state()
    state.set_external_publisher_count(1)
    state.request_quit()

    assert state.evaluate(T0).status is TeleopStatus.QUIT


# ---------------------------------------------------------------------------
# 비정상 파라미터 검증
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("max_linear_mps", 0.0),
        ("max_linear_mps", -0.13),
        ("max_linear_mps", float("nan")),
        ("max_linear_mps", float("inf")),
        ("max_angular_rps", 0.0),
        ("max_angular_rps", -0.6),
        ("max_angular_rps", float("nan")),
        ("input_timeout_sec", 0.0),
        ("input_timeout_sec", -1.0),
        ("input_timeout_sec", float("nan")),
        ("input_timeout_sec", float("inf")),
    ],
)
def test_invalid_parameters_raise_value_error(name: str, value: float) -> None:
    """0 이하·비유한 파라미터는 ValueError 이고 메시지에 이름이 담긴다."""
    with pytest.raises(ValueError, match=name):
        _state(**{name: value})


@pytest.mark.parametrize("step_count", [0, -1])
def test_invalid_speed_step_count_raises_value_error(step_count: int) -> None:
    """속도 단계 수가 1 미만이면 ValueError 다."""
    with pytest.raises(ValueError, match="speed_step_count"):
        TeleopState(speed_step_count=step_count)


@pytest.mark.parametrize("now_sec", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_now_sec_raises_value_error(now_sec: float) -> None:
    """시각이 유한하지 않으면 handle_key/evaluate 모두 ValueError 다."""
    state = _state()

    with pytest.raises(ValueError, match="now_sec"):
        state.handle_key(KEY_FORWARD, now_sec)
    with pytest.raises(ValueError, match="now_sec"):
        state.evaluate(now_sec)


# ---------------------------------------------------------------------------
# 구조 계약: 순수 모듈이 ROS·터미널·Serial 에 의존하지 않는다
# ---------------------------------------------------------------------------


def test_teleop_keys_imports_stay_pure() -> None:
    """★ teleop_keys 는 rclpy·termios·serial·stm_serial_bridge 를 import 하지 않는다.

    이 계약이 깨지면 하드웨어·ROS 없이 테스트할 수 없게 되고, "teleop 은 Serial
    포트를 열지 않는다"는 안전 요구도 검증할 수 없다. AST 로 직접 확인한다.
    """
    source_path = (
        Path(__file__).resolve().parent.parent / "cart_teleop" / "teleop_keys.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    forbidden = {
        "rclpy",
        "termios",
        "tty",
        "select",
        "serial",
        "geometry_msgs",
        "std_msgs",
        "stm_serial_bridge",
    }
    assert not (imported & forbidden), f"금지된 import: {sorted(imported & forbidden)}"


def test_teleop_node_does_not_import_serial_or_the_bridge() -> None:
    """★ 노드도 Serial·Bridge 내부 모듈을 import 하지 않는다.

    Serial 포트 소유자는 stm_serial_bridge 하나뿐이라는 요구를 코드로 고정한다.
    """
    source_path = (
        Path(__file__).resolve().parent.parent / "cart_teleop" / "teleop_node.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    forbidden = {"serial", "stm_serial_bridge", "pyserial"}
    assert not (imported & forbidden), f"금지된 import: {sorted(imported & forbidden)}"
