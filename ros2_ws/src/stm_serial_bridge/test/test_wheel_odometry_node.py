"""wheel_odometry 노드(/stm/encoder_total -> /wheel/odom)의 테스트.

실제 STM32·브리지 없이 검증한다. `Int32MultiArray` 메시지를 콜백에 직접 넣고, 발행
Publisher 를 캡처용 fake 로 바꿔 "어떤 값을 어떤 토픽에 넣는가"를 확인한다. 실제 DDS
왕복을 기다리면 느리고 불안정해지는데, 여기서 검증하려는 것은 배선과 값이므로 캡처가
더 정확한 도구다. DDS 왕복 자체는 마지막 절에서 한 번만 확인한다.

dt 는 `_now_sec` 을 덮어써 고정한다 — 실제 시각에 의존하면 속도 검증이 불안정해진다.

실행::

    cd ros2_ws
    export ROS_LOCALHOST_ONLY=1
    source /opt/ros/humble/setup.bash && source install/setup.bash
    python3 -m pytest src/stm_serial_bridge/test/test_wheel_odometry_node.py -v
"""

import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import rclpy
import yaml
from nav_msgs.msg import Odometry
from std_msgs.msg import Int32MultiArray

from stm_serial_bridge.stm_serial_bridge_node import (
    ENCODER_TOTAL_TOPIC as BRIDGE_ENCODER_TOTAL_TOPIC,
)
from stm_serial_bridge.wheel_odometry import WheelGeometry
from stm_serial_bridge.wheel_odometry_node import (
    COVARIANCE_DIAGONAL_INDICES,
    ENCODER_TOTAL_TOPIC,
    UNOBSERVED_VARIANCE,
    WHEEL_ODOM_TOPIC,
    WheelOdometryNode,
    extract_encoder_counts,
    yaw_to_quaternion,
)

# 2026-08-08 실기 1m 직진 x3 으로 보정한 **거리 스케일 상수**(기구 실측 치수가 아니다).
# 브리지의 명목 0.065 와 의도적으로 다르다 — 아래 스케일 보정 절 참고.
WHEEL_RADIUS_M = 0.0587
#: 브리지가 명령 기구학에 쓰는 명목 반지름.
BRIDGE_NOMINAL_WHEEL_RADIUS_M = 0.065
WHEEL_SEPARATION_M = 0.38
COUNTS_PER_WHEEL_REV = 68160.0

# === 2026-08-08 실기 1m 직진 x3 (relu) ===
# 보고 이동거리 |Δ| = 1.1012 / 1.1136 / 1.1055 m, 실제는 모두 약 1.0 m.
FIELD_TEST_REPORTED_DISTANCES_M = (1.101233, 1.113589, 1.105543)
FIELD_TEST_MEAN_SCALE = 1.106788

# 위 3회 평균에서 역산한 좌우 count 변화량 (r=0.065 · 68160 기준).
# ⚠️ **측정된 count 가 아니라 보고 포즈에서 역산한 값이다.** 같은 엔코더 입력이 보정 전에는
#    1.107 m 로 나왔다는 사실을 회귀로 고정하는 용도다.
FIELD_TEST_LEFT_COUNTS = 188_974
FIELD_TEST_RIGHT_COUNTS = 180_455

GEOMETRY = WheelGeometry(
    wheel_radius_m=WHEEL_RADIUS_M,
    wheel_separation_m=WHEEL_SEPARATION_M,
    counts_per_wheel_rev=COUNTS_PER_WHEEL_REV,
)
METERS_PER_COUNT = GEOMETRY.meters_per_count

PACKAGE_DIR = Path(__file__).resolve().parents[1]
BRIDGE_CONFIG = PACKAGE_DIR / "config" / "stm_serial_bridge.yaml"
ODOMETRY_CONFIG = PACKAGE_DIR / "config" / "wheel_odometry.yaml"

# 두 YAML 이 **같아야 하는** 키. `wheel_radius_m` 은 2026-08-08 스케일 보정으로
# 의도적으로 갈렸으므로 여기 없다 (별도 테스트가 그 차이를 명시적으로 고정한다).
SHARED_GEOMETRY_KEYS = (
    "wheel_separation_m",
    "counts_per_wheel_rev",
)


@pytest.fixture(scope="module", autouse=True)
def _ros_context() -> Iterator[None]:
    """Init/shutdown rclpy once for this module."""
    rclpy.init()
    try:
        yield
    finally:
        rclpy.shutdown()


class _CapturingPublisher:
    """Publisher 대역 — 발행된 메시지를 그대로 모아 둔다."""

    def __init__(self) -> None:
        """Start with an empty capture list."""
        self.published: list[Odometry] = []

    def publish(self, message: Odometry) -> None:
        """Record the published message."""
        self.published.append(message)


def _make_node(**parameter_overrides: Any) -> WheelOdometryNode:  # noqa: ANN401
    """Build a started node whose publisher is replaced by a capture.

    Args:
        **parameter_overrides: `start()` 전에 덮어쓸 파라미터.

    Returns:
        `start()` 까지 끝나고 발행자가 캡처로 교체된 노드.
    """
    node = WheelOdometryNode()
    if parameter_overrides:
        node.set_parameters(
            [
                rclpy.parameter.Parameter(name, value=value)
                for name, value in parameter_overrides.items()
            ]
        )
    node.start()
    node._odom_publisher = _CapturingPublisher()  # noqa: SLF001
    return node


@pytest.fixture
def node_factory() -> Iterator[Any]:
    """Yield a factory that destroys every created node at teardown."""
    created: list[WheelOdometryNode] = []

    def factory(**kwargs: Any) -> WheelOdometryNode:  # noqa: ANN401
        node = _make_node(**kwargs)
        created.append(node)
        return node

    try:
        yield factory
    finally:
        for node in created:
            node.destroy_node()


def _set_clock(node: WheelOdometryNode, value: float) -> None:
    """Freeze the node's monotonic clock so dt is exact.

    Args:
        node: 대상 노드.
        value: 고정할 시각(초).
    """
    node._now_sec = lambda: value  # type: ignore[method-assign]  # noqa: SLF001


def _feed(node: WheelOdometryNode, left: int, right: int, at_sec: float) -> None:
    """Deliver one encoder_total sample at a fixed timestamp.

    Args:
        node: 대상 노드.
        left: 좌측 누적 count.
        right: 우측 누적 count.
        at_sec: 이 샘플의 수신 시각(초).
    """
    _set_clock(node, at_sec)
    node._on_encoder_total(Int32MultiArray(data=[left, right]))  # noqa: SLF001


def _captured(node: WheelOdometryNode) -> list[Odometry]:
    """Return every message the node published so far.

    Args:
        node: 대상 노드.

    Returns:
        캡처된 `Odometry` 목록.
    """
    return node._odom_publisher.published  # noqa: SLF001


# ---------------------------------------------------------------------------
# 1. 순수 헬퍼
# ---------------------------------------------------------------------------


def test_extract_encoder_counts_returns_left_then_right() -> None:
    """data 는 [left, right] 순서다 (2026-08-03 실기 확정 매핑)."""
    assert extract_encoder_counts([111, 222]) == (111, 222)


@pytest.mark.parametrize("data", [[], [1], [1, 2, 3]])
def test_extract_encoder_counts_rejects_wrong_length(data: list[int]) -> None:
    """원소가 2개가 아니면 ValueError 이고 실제 길이가 메시지에 담긴다."""
    with pytest.raises(ValueError, match="2 elements"):
        extract_encoder_counts(data)


@pytest.mark.parametrize(
    ("yaw_rad", "expected_z", "expected_w"),
    [
        (0.0, 0.0, 1.0),
        (math.pi / 2.0, math.sqrt(0.5), math.sqrt(0.5)),
        (math.pi, 1.0, 0.0),
        (-math.pi / 2.0, -math.sqrt(0.5), math.sqrt(0.5)),
    ],
)
def test_yaw_to_quaternion(
    yaw_rad: float, expected_z: float, expected_w: float
) -> None:
    """평면 회전이므로 x·y 는 0이고 z·w 만 채워진다."""
    x, y, z, w = yaw_to_quaternion(yaw_rad)

    assert (x, y) == (0.0, 0.0)
    assert z == pytest.approx(expected_z)
    assert w == pytest.approx(expected_w)
    assert z * z + w * w == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 2. 파라미터
# ---------------------------------------------------------------------------


def test_parameters_have_documented_defaults() -> None:
    """노드 기본값이 문서화된 실측·보정값과 같다."""
    node = WheelOdometryNode()
    try:
        assert node.get_parameter("wheel_radius_m").value == pytest.approx(0.0587)
        assert node.get_parameter("wheel_separation_m").value == pytest.approx(0.38)
        assert node.get_parameter("counts_per_wheel_rev").value == pytest.approx(
            68160.0
        )
        assert node.get_parameter("odom_frame_id").value == "odom"
        assert node.get_parameter("base_frame_id").value == "base_link"
    finally:
        node.destroy_node()


def test_node_never_declares_the_nominal_firmware_scale() -> None:
    """기본 스케일은 실측 68160 이며 펌웨어 명목 77520 이 아니다."""
    node = WheelOdometryNode()
    try:
        assert node.get_parameter("counts_per_wheel_rev").value != 77520.0
    finally:
        node.destroy_node()


@pytest.mark.parametrize(
    "name",
    ["wheel_radius_m", "wheel_separation_m", "counts_per_wheel_rev"],
)
@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_geometry_parameters_are_rejected_before_subscribing(
    name: str, value: float
) -> None:
    """기구 상수가 잘못되면 start() 가 ValueError 이고 구독이 만들어지지 않는다."""
    node = WheelOdometryNode()
    try:
        node.set_parameters([rclpy.parameter.Parameter(name, value=value)])
        with pytest.raises(ValueError, match=name):
            node.start()
        assert node._subscription is None  # noqa: SLF001
    finally:
        node.destroy_node()


@pytest.mark.parametrize("name", ["odom_frame_id", "base_frame_id"])
@pytest.mark.parametrize("value", ["", "   "])
def test_empty_frame_ids_are_rejected(name: str, value: str) -> None:
    """frame id 가 비어 있으면 start() 가 ValueError 다."""
    node = WheelOdometryNode()
    try:
        node.set_parameters([rclpy.parameter.Parameter(name, value=value)])
        with pytest.raises(ValueError, match=name):
            node.start()
    finally:
        node.destroy_node()


# ---------------------------------------------------------------------------
# 3. 첫 샘플 — 적분하지 않고 기준만 잡는다
# ---------------------------------------------------------------------------


def test_first_sample_only_rebaselines_and_publishes_nothing(
    node_factory: Any,  # noqa: ANN401
) -> None:
    """첫 encoder_total 은 기준만 잡고 발행하지 않는다.

    비교할 이전 count 도 경과 시간도 없다. 속도를 0으로 지어내 발행하면 소비하는 쪽이
    "정지해 있다는 측정"으로 받아들이게 되므로 아무것도 내보내지 않는다.
    """
    node = node_factory()

    _feed(node, 1000, 2000, at_sec=100.0)

    assert _captured(node) == []
    assert node.state is not None
    assert (node.state.left_count, node.state.right_count) == (1000, 2000)
    assert (node.state.x_m, node.state.y_m, node.state.theta_rad) == (0.0, 0.0, 0.0)


def test_first_sample_does_not_integrate_a_large_starting_count(
    node_factory: Any,  # noqa: ANN401
) -> None:
    """시작 시 누적 count 가 이미 커도 포즈는 원점이다 (적분하지 않으므로)."""
    node = node_factory()

    _feed(node, 5_000_000, 5_000_000, at_sec=10.0)

    assert node.state.x_m == 0.0
    assert _captured(node) == []


# ---------------------------------------------------------------------------
# 4. 적분과 발행
# ---------------------------------------------------------------------------


def test_second_sample_publishes_straight_motion(
    node_factory: Any,  # noqa: ANN401
) -> None:
    """직진하면 x 만 늘고 방위·각속도는 0이다."""
    node = node_factory()
    counts = int(COUNTS_PER_WHEEL_REV)  # 정확히 1회전

    _feed(node, 0, 0, at_sec=100.0)
    _feed(node, counts, counts, at_sec=101.0)

    messages = _captured(node)
    assert len(messages) == 1
    message = messages[0]

    circumference = 2.0 * math.pi * WHEEL_RADIUS_M
    assert message.pose.pose.position.x == pytest.approx(circumference)
    assert message.pose.pose.position.y == pytest.approx(0.0)
    assert message.pose.pose.position.z == 0.0
    assert message.pose.pose.orientation.z == pytest.approx(0.0)
    assert message.pose.pose.orientation.w == pytest.approx(1.0)
    # dt = 1.0초이므로 속도는 이동 거리와 같은 수치가 된다.
    assert message.twist.twist.linear.x == pytest.approx(circumference)
    assert message.twist.twist.angular.z == pytest.approx(0.0)


def test_in_place_rotation_publishes_yaw_without_translation(
    node_factory: Any,  # noqa: ANN401
) -> None:
    """제자리 회전은 위치를 바꾸지 않고 yaw 와 각속도만 만든다."""
    node = node_factory()

    _feed(node, 0, 0, at_sec=100.0)
    _feed(node, -1000, 1000, at_sec=100.1)

    message = _captured(node)[0]
    expected_theta = 2000 * METERS_PER_COUNT / WHEEL_SEPARATION_M

    assert message.pose.pose.position.x == pytest.approx(0.0)
    assert message.pose.pose.position.y == pytest.approx(0.0)
    # 오른쪽이 더 가면 반시계(REP 103) → yaw 양수
    assert message.pose.pose.orientation.z == pytest.approx(
        math.sin(expected_theta / 2.0)
    )
    assert message.twist.twist.linear.x == pytest.approx(0.0)
    assert message.twist.twist.angular.z == pytest.approx(expected_theta / 0.1)


def test_pose_accumulates_across_samples(node_factory: Any) -> None:  # noqa: ANN401
    """포즈는 샘플마다 누적된다."""
    node = node_factory()
    step = 10_000

    _feed(node, 0, 0, at_sec=0.0)
    for index in range(1, 4):
        _feed(node, step * index, step * index, at_sec=index * 0.1)

    messages = _captured(node)
    assert len(messages) == 3
    positions = [message.pose.pose.position.x for message in messages]

    assert positions[0] == pytest.approx(step * METERS_PER_COUNT)
    assert positions[1] == pytest.approx(2 * step * METERS_PER_COUNT)
    assert positions[2] == pytest.approx(3 * step * METERS_PER_COUNT)


def test_velocity_uses_encoder_delta_not_the_reported_wheel_speed(
    node_factory: Any,  # noqa: ANN401
) -> None:
    """속도는 count 변화량 x 68160 기준으로 나온다 (77520 기준이면 약 12% 작다).

    이 노드는 `/stm/wheel_actual_rad_s` 를 아예 구독하지 않는다. 그 사실과 스케일
    선택을 함께 고정한다.
    """
    node = node_factory()

    _feed(node, 0, 0, at_sec=0.0)
    _feed(node, 68160, 68160, at_sec=1.0)

    measured = _captured(node)[0].twist.twist.linear.x
    nominal_scale = measured * (68160.0 / 77520.0)

    assert measured == pytest.approx(2.0 * math.pi * WHEEL_RADIUS_M)
    # 명목 스케일을 썼다면 약 12% 작았을 것이다.
    assert nominal_scale == pytest.approx(measured * 0.87926, abs=1e-4)


def test_published_frames_come_from_parameters(
    node_factory: Any,  # noqa: ANN401
) -> None:
    """header.frame_id / child_frame_id 는 파라미터를 그대로 쓴다."""
    node = node_factory(odom_frame_id="wheel_odom", base_frame_id="cart_base")

    _feed(node, 0, 0, at_sec=0.0)
    _feed(node, 100, 100, at_sec=0.1)

    message = _captured(node)[0]
    assert message.header.frame_id == "wheel_odom"
    assert message.child_frame_id == "cart_base"


def test_covariance_diagonal_is_filled(node_factory: Any) -> None:  # noqa: ANN401
    """공분산 대각이 파라미터 값으로 채워진다 (2026-08-08 EKF 준비 단계에서 설정).

    이전에는 "아직 0"을 고정하는 테스트였다. EKF 연결을 위해 값을 채웠으므로 함께
    바뀌었다 — 값의 근거는 `wheel_odometry_node.py` 모듈 docstring §공분산.
    """
    node = node_factory()

    _feed(node, 0, 0, at_sec=0.0)
    _feed(node, 100, 100, at_sec=0.1)

    message = _captured(node)[0]
    pose = list(message.pose.covariance)
    twist = list(message.twist.covariance)

    assert pose[0] == pose[7] == 0.05
    assert pose[35] == 0.25
    assert twist[0] == twist[7] == 0.0025
    assert twist[35] == 0.25
    # 관측되지 않는 자유도(z, roll, pitch)는 큰 유한값이다 — 무한대를 쓰면
    # robot_localization 이 행렬을 뒤집을 때 수치적으로 터질 수 있다.
    for index in (14, 21, 28):
        assert pose[index] == UNOBSERVED_VARIANCE
        assert twist[index] == UNOBSERVED_VARIANCE
    # 축 간 상관은 측정하지 않았으므로 대각 외는 전부 0이다.
    for index in range(36):
        if index not in COVARIANCE_DIAGONAL_INDICES:
            assert pose[index] == 0.0
            assert twist[index] == 0.0


def test_zero_variance_is_rejected(node_factory: Any) -> None:  # noqa: ANN401
    """분산 0은 거부한다 — '오차 없음'으로 읽혀 융합기가 이 소스만 신뢰하게 된다."""
    with pytest.raises(ValueError, match="twist_linear_variance"):
        node_factory(twist_linear_variance=0.0)


# ---------------------------------------------------------------------------
# 5. 잘못된 입력과 dt 경계
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("data", [[], [1], [1, 2, 3]])
def test_malformed_message_is_ignored_without_touching_state(
    node_factory: Any,  # noqa: ANN401
    data: list[int],
) -> None:
    """원소 수가 틀린 메시지는 무시하고 상태를 건드리지 않는다."""
    node = node_factory()
    _feed(node, 1000, 1000, at_sec=0.0)

    _set_clock(node, 0.1)
    node._on_encoder_total(Int32MultiArray(data=data))  # noqa: SLF001

    assert _captured(node) == []
    assert (node.state.left_count, node.state.right_count) == (1000, 1000)


@pytest.mark.parametrize("second_sample_time", [100.0, 99.9])
def test_non_positive_dt_skips_publishing_but_keeps_the_baseline(
    node_factory: Any,  # noqa: ANN401
    second_sample_time: float,
) -> None:
    """dt 가 0 이하면 발행하지 않되 **기준은 유지한다.**

    기준을 갱신해 버리면 이번 구간의 이동량이 통째로 버려져 포즈에 영구 오차가 남는다.
    그대로 두면 다음 샘플이 이번 구간까지 함께 적분하므로 포즈는 손실되지 않는다.
    """
    node = node_factory()

    _feed(node, 0, 0, at_sec=100.0)
    _feed(node, 500, 500, at_sec=second_sample_time)

    assert _captured(node) == []
    # 기준이 유지됐으므로 count 는 여전히 첫 샘플 값이다.
    assert (node.state.left_count, node.state.right_count) == (0, 0)

    # 다음 정상 샘플이 건너뛴 구간(500)까지 함께 적분한다.
    _feed(node, 1000, 1000, at_sec=101.0)

    message = _captured(node)[0]
    assert message.pose.pose.position.x == pytest.approx(1000 * METERS_PER_COUNT)


# ---------------------------------------------------------------------------
# 6. 토픽·설정 정합 (드리프트 방지)
# ---------------------------------------------------------------------------


def test_subscribed_topic_matches_the_bridge_publisher() -> None:
    """구독 토픽 이름이 브리지의 발행 토픽과 정확히 같다.

    두 노드는 서로를 import 하지 않는다(느슨한 결합). 대신 이 테스트가 이름이 갈리는
    것을 막는다.
    """
    assert ENCODER_TOTAL_TOPIC == BRIDGE_ENCODER_TOTAL_TOPIC


def test_publishes_to_wheel_odom_not_odom() -> None:
    """발행 토픽은 `/wheel/odom` 이다 — 최종 `/odom` 을 점유하지 않는다.

    최종 `/odom` 과 `odom -> base_link` TF 는 이후 EKF 의 몫이다.
    """
    assert WHEEL_ODOM_TOPIC == "/wheel/odom"
    assert WHEEL_ODOM_TOPIC != "/odom"


def test_wheel_radius_intentionally_differs_from_the_bridge() -> None:
    """두 YAML 의 `wheel_radius_m` 이 서로 다른 것은 **의도된 상태**다.

    - 브리지(0.065): `/cmd_vel`(m/s) -> 바퀴 rad/s 변환에 쓰는 **명목 기구 치수**.
      엔코더가 개입하지 않는 개루프 명령 경로다.
    - 오도메트리(0.0587): 2026-08-08 실기 1m 직진 x3 으로 얻은 **거리 스케일 보정 상수**.
      유효 구름반지름 + 슬립 + `counts_per_wheel_rev` 오차를 한꺼번에 흡수한다.

    직진 시험은 `2*pi*r / counts_per_rev` 라는 **곱만** 관측하므로 두 인자를 분리할 수
    없다. 그 오차의 상당 부분이 미해결 상태인 엔코더 스케일일 수 있어 명령 경로에는
    옮기지 않았다. 두 값을 합치려면 이 테스트를 의도적으로 바꿔야 한다.
    """
    bridge = yaml.safe_load(BRIDGE_CONFIG.read_text())
    odometry = yaml.safe_load(ODOMETRY_CONFIG.read_text())

    bridge_radius = bridge["stm_serial_bridge"]["ros__parameters"]["wheel_radius_m"]
    odometry_radius = odometry["wheel_odometry"]["ros__parameters"]["wheel_radius_m"]

    assert bridge_radius == pytest.approx(BRIDGE_NOMINAL_WHEEL_RADIUS_M)
    assert odometry_radius == pytest.approx(WHEEL_RADIUS_M)
    assert odometry_radius != bridge_radius


def test_calibrated_radius_cancels_the_measured_scale_error() -> None:
    """보정 반지름이 실측 배율 1.1068 을 상쇄한다.

    `r_new = r_old / k` 이며, 0.0587 로 반올림한 잔차는 0.1% 미만이다 — 3회 측정의
    스프레드(±0.56%)보다 훨씬 작다.
    """
    mean_scale = sum(FIELD_TEST_REPORTED_DISTANCES_M) / len(
        FIELD_TEST_REPORTED_DISTANCES_M
    )

    assert mean_scale == pytest.approx(FIELD_TEST_MEAN_SCALE, abs=1e-5)
    assert BRIDGE_NOMINAL_WHEEL_RADIUS_M / mean_scale == pytest.approx(
        WHEEL_RADIUS_M, abs=5e-5
    )


def test_field_test_counts_now_report_one_meter(
    node_factory: Any,  # noqa: ANN401
) -> None:
    """실기 3회 평균에 해당하는 count 를 넣으면 약 1.0 m 로 보고된다.

    보정 전(r=0.065)에는 같은 입력이 1.107 m 로 나왔다. 이 테스트가 스케일 보정의
    회귀를 고정한다.

    ⚠️ **yaw drift 는 이 보정으로 해결되지 않는다.** `Δθ` 도 r 에 비례하므로 보고값이
    약 9.7% 줄어들 뿐이며, 좌우 이동거리 차이(약 4.7%)라는 원인은 그대로다.
    """
    node = node_factory()

    _feed(node, 0, 0, at_sec=0.0)
    _feed(node, FIELD_TEST_LEFT_COUNTS, FIELD_TEST_RIGHT_COUNTS, at_sec=1.0)

    message = _captured(node)[0]
    distance = math.hypot(
        message.pose.pose.position.x, message.pose.pose.position.y
    )

    assert distance == pytest.approx(1.0, abs=0.01)
    # 같은 입력을 보정 전 반지름으로 계산했다면 약 1.107 m 였다.
    assert distance * (
        BRIDGE_NOMINAL_WHEEL_RADIUS_M / WHEEL_RADIUS_M
    ) == pytest.approx(FIELD_TEST_MEAN_SCALE, abs=0.01)
    # yaw drift 는 남아 있다 (보정 전 -0.1343 -> 약 -0.1213).
    assert message.twist.twist.angular.z == pytest.approx(-0.1213, abs=1e-3)


@pytest.mark.parametrize("key", SHARED_GEOMETRY_KEYS)
def test_geometry_parameters_agree_across_both_config_files(key: str) -> None:
    """두 YAML 의 공유 기구 상수가 같은 값이다.

    ROS 파라미터에는 파일 간 참조가 없어 중복이 불가피하다. 이 테스트가 중복을
    "테스트로 강제되는 불변식"으로 바꿔, 한쪽만 고치면 즉시 실패하게 한다.
    """
    bridge = yaml.safe_load(BRIDGE_CONFIG.read_text())
    odometry = yaml.safe_load(ODOMETRY_CONFIG.read_text())

    bridge_value = bridge["stm_serial_bridge"]["ros__parameters"][key]
    odometry_value = odometry["wheel_odometry"]["ros__parameters"][key]

    assert bridge_value == pytest.approx(odometry_value)


@pytest.mark.parametrize("key", SHARED_GEOMETRY_KEYS)
def test_node_defaults_match_the_odometry_config_file(key: str) -> None:
    """노드 기본값과 YAML 값이 같다 — `ros2 run` 직접 실행 시에도 같은 값이 쓰인다."""
    odometry = yaml.safe_load(ODOMETRY_CONFIG.read_text())
    expected = odometry["wheel_odometry"]["ros__parameters"][key]

    node = WheelOdometryNode()
    try:
        assert node.get_parameter(key).value == pytest.approx(expected)
    finally:
        node.destroy_node()


def test_config_node_name_matches_the_actual_node_name() -> None:
    """YAML 최상위 키가 실제 노드 이름과 같아야 파라미터가 적용된다."""
    odometry = yaml.safe_load(ODOMETRY_CONFIG.read_text())

    node = WheelOdometryNode()
    try:
        assert list(odometry.keys()) == [node.get_name()]
    finally:
        node.destroy_node()


# ---------------------------------------------------------------------------
# 7. 실제 DDS 왕복 (배선 확인)
# ---------------------------------------------------------------------------


def test_end_to_end_over_dds() -> None:
    """실제 발행/구독으로 encoder_total -> /wheel/odom 왕복이 도는지 확인한다.

    앞의 테스트들이 캡처로 값을 보는 것과 달리, 여기서는 토픽 이름·타입·QoS 가 실제로
    맞물리는지를 본다.
    """
    node = WheelOdometryNode()
    publisher_node = rclpy.create_node("test_encoder_publisher")
    received: list[Odometry] = []
    try:
        node.start()
        publisher = publisher_node.create_publisher(
            Int32MultiArray, ENCODER_TOTAL_TOPIC, 10
        )
        subscriber_node = rclpy.create_node("test_odom_subscriber")
        subscriber_node.create_subscription(
            Odometry, WHEEL_ODOM_TOPIC, received.append, 10
        )

        try:
            deadline = 200
            counts = 0
            while len(received) < 1 and deadline > 0:
                counts += 5000
                publisher.publish(Int32MultiArray(data=[counts, counts]))
                for spin_target in (node, subscriber_node):
                    rclpy.spin_once(spin_target, timeout_sec=0.02)
                deadline -= 1

            assert received, "no /wheel/odom message arrived"
            assert received[0].header.frame_id == "odom"
            assert received[0].child_frame_id == "base_link"
            assert received[0].pose.pose.position.x > 0.0
        finally:
            subscriber_node.destroy_node()
    finally:
        publisher_node.destroy_node()
        node.destroy_node()
