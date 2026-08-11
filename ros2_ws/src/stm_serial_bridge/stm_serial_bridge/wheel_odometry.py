"""휠 오도메트리 — 엔코더 누적 count 로 평면 포즈와 속도를 계산한다.

이 모듈은 `rclpy`·ROS 메시지 타입·serial·**시계**에 의존하지 않는 **순수 계산 모듈**이다.
하드웨어나 ROS 실행 환경 없이 pytest 로 검증할 수 있도록 의도적으로 분리했다.
전역 상태를 두지 않으며, 상태는 호출자가 `OdometryState`(frozen)로 들고 다닌다.

입력은 STM32 STATUS 의 `LE`/`RE`(좌우 **누적** encoder count)이며, ROS 쪽에서는
`/stm/encoder_total`(`Int32MultiArray [left, right]`)로 이미 발행되고 있다.

⚠️ **`/stm/wheel_actual_rad_s`는 쓰지 않는다.** 그 값은 펌웨어의 **명목** 상수
77520 count/wheel-rev(= CPR 380 x Gear 51 x Quadrature 4) 기준이라 실제보다 약 12%
작게 보고된다. 휠 오도메트리는 `encoder_total` 변화량과 **실측** 기준값
68160 count/wheel-rev(`counts_per_wheel_rev` 파라미터)로만 계산한다. 두 스케일을 섞으면
문서화된 불일치가 코드로 새어 들어간다.
(근거: embedded/motor/docs/serial_protocol.md "펌웨어와 ROS의 스케일 불일치" 절)

이 모듈이 **하지 않는 것**:

- 토픽 발행과 TF 방송. 휠 오도메트리는 최종 `/odom`이 아니라 `/wheel/odom` 같은 별도
  토픽으로 나가고, 최종 `/odom`과 `odom -> base_link` TF 는 이후 LiDAR 오도메트리와
  융합하는 **EKF 가 담당**한다. 따라서 여기서도, 이 모듈을 쓰는 노드에서도 TF 를
  발행하지 않는다.
- 시각 측정. `dt_sec`는 인자로만 받는다.
- `rebaseline()` **호출 정책 결정**. 함수는 제공하지만 "언제 부를지"는 이 모듈의 관심사가
  아니다. 아래 `rebaseline()` docstring 의 경고를 참고할 것.

포즈와 속도의 정확도는 성질이 다르다:

- **포즈(x, y, theta)는 `dt_sec`와 무관하다.** count 변화량만으로 결정되므로 STATUS 수신
  간격이 흔들려도 영향을 받지 않는다.
- **속도(v, omega)는 `dt_sec`에 직접 비례한다.** 펌웨어 STATUS 에는 타임스탬프가 없어
  `dt_sec`를 수신 시각 차이로 만들 수밖에 없고, 그 지터가 그대로 속도에 실린다.
  속도를 소비하는 쪽(EKF 공분산 등)은 이 점을 전제로 다뤄야 한다.
"""

import math
from dataclasses import dataclass, replace

# 펌웨어가 STATUS 에 `%ld`로 싣는 누적 count 의 자료형은 int32 다. 범위를 넘으면
# 래핑되므로 단순 뺄셈으로 델타를 구할 수 없다(`encoder_delta()` 참고).
# `mock_stm.py`도 같은 범위로 래핑을 모사한다.
_INT32_SPAN = 1 << 32
_INT32_HALF = 1 << 31


@dataclass(frozen=True)
class WheelGeometry:
    """휠 오도메트리 계산에 필요한 기구·엔코더 상수 묶음.

    세 값이 항상 함께 쓰이므로 한 덩어리로 전달한다. 생성 시점에 한 번 검증하므로
    개별 함수는 값 검증을 반복하지 않는다.

    Attributes:
        wheel_radius_m: 바퀴 반지름 r (m).
        wheel_separation_m: 좌우 바퀴 중심 간 거리 L (m).
        counts_per_wheel_rev: 바퀴(출력축) 1회전당 누적 엔코더 count.
            **펌웨어 명목값 77520 이 아니라 실측 기준값 68160 을 넣는다.**
    """

    wheel_radius_m: float
    wheel_separation_m: float
    counts_per_wheel_rev: float

    def __post_init__(self) -> None:
        """세 값이 모두 유한하고 0보다 큰지 검증한다.

        `differential_drive`가 비유한 입력을 그대로 전파시키는 것과 달리 이 모듈은
        **유한성까지 막는다.** 그쪽 출력은 매 tick 새로 계산되는 일회성 명령이라
        NaN 이 스스로 사라지지만, 오도메트리 포즈는 **누적 상태**라서 NaN 이 한 번
        섞이면 그 뒤 모든 포즈가 영구히 오염되기 때문이다.

        Raises:
            ValueError: 값이 비유한(NaN/Inf)이거나 0 이하일 때. 어느 필드가 잘못됐는지
                이름과 값을 메시지에 담는다.
        """
        for name in (
            "wheel_radius_m",
            "wheel_separation_m",
            "counts_per_wheel_rev",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(
                    f"{name} must be a finite value greater than 0.0, got {value}"
                )

    @property
    def meters_per_count(self) -> float:
        """엔코더 1 count 당 바퀴 접지점 이동 거리 [m/count].

        `2 * pi * r / counts_per_wheel_rev` 이다. r=0.065, 68160 count/rev 기준으로
        약 6 마이크로미터이므로 양자화 오차는 실질적으로 무시할 수 있다.

        Returns:
            count 당 이동 거리 (m). 항상 양수.
        """
        return (2.0 * math.pi * self.wheel_radius_m) / self.counts_per_wheel_rev


@dataclass(frozen=True)
class OdometryState:
    """적분된 포즈와, 다음 델타 계산의 기준이 되는 마지막 raw count.

    frozen 이므로 `advance()`/`rebaseline()`은 원본을 바꾸지 않고 **새 상태를 돌려준다.**
    덕분에 여러 스텝을 이어 붙인 시퀀스를 그대로 단위 테스트할 수 있다.

    Attributes:
        x_m: odom 기준 x 좌표 (m).
        y_m: odom 기준 y 좌표 (m).
        theta_rad: odom 기준 yaw (rad). 항상 `(-pi, pi]`로 정규화되어 있다.
        left_count: 마지막으로 소비한 좌측 누적 count (raw int32).
        right_count: 마지막으로 소비한 우측 누적 count (raw int32).
    """

    x_m: float
    y_m: float
    theta_rad: float
    left_count: int
    right_count: int


def initial_state(left_count: int, right_count: int) -> OdometryState:
    """원점·무회전 포즈에서 시작하는 초기 상태를 만든다.

    첫 STATUS 를 받은 시점에 호출한다. 첫 샘플에는 비교할 이전 count 가 없으므로
    적분하지 않고 기준만 잡는 것이 맞다.

    Args:
        left_count: 좌측 누적 count.
        right_count: 우측 누적 count.

    Returns:
        포즈가 `(0, 0, 0)`이고 count 기준만 채워진 `OdometryState`.
    """
    return OdometryState(
        x_m=0.0,
        y_m=0.0,
        theta_rad=0.0,
        left_count=left_count,
        right_count=right_count,
    )


def rebaseline(
    state: OdometryState, left_count: int, right_count: int
) -> OdometryState:
    """포즈는 유지한 채 count 기준만 새 값으로 바꾼다.

    STM32 가 재부팅하면 `encoder_total`이 0 으로 돌아간다. 그 점프는 래핑 보정으로도
    걸러지지 않고 **정당한 큰 델타처럼 보이므로**, 그대로 적분하면 포즈가 순간이동한다.
    이 함수는 기준만 다시 잡아 그 점프를 적분에서 제외한다.

    **끊긴 구간의 실제 이동은 버린다 — 추정하지 않는다.** 그동안 카트가 움직였다면 그만큼
    오도메트리에 영구 오차로 남는다. 이는 근거 없이 값을 지어내는 것보다 나은 선택이며,
    소비하는 쪽(EKF)이 불연속을 알 수 있도록 노드가 별도로 알려야 한다.

    ⚠️ **언제 호출할지는 이 모듈이 정하지 않는다.** 특히 `/stm/connected`의 false -> true
    전이만으로 모든 STM reset 을 잡을 수 있다고 가정하지 말 것 — STATUS 가 끊기지 않을
    만큼 빠른 재부팅이나, 연결이 유지된 채 카운터만 초기화되는 경로를 놓칠 수 있다.
    호출 정책은 ROS 연결 단계에서 별도로 검토한다.

    Args:
        state: 직전 상태. 포즈만 그대로 승계한다.
        left_count: 새 기준이 될 좌측 누적 count.
        right_count: 새 기준이 될 우측 누적 count.

    Returns:
        포즈는 `state`와 같고 count 만 교체된 새 `OdometryState`.
    """
    return replace(state, left_count=left_count, right_count=right_count)


def encoder_delta(prev_count: int, curr_count: int) -> int:
    """int32 래핑을 고려해 두 누적 count 사이의 실제 변화량을 구한다.

    누적 count 는 int32 라 `2147483647` 다음에 `-2147483648` 로 넘어간다. 단순 뺄셈은
    이 순간 약 43억 count 짜리 가짜 델타를 만들어 포즈를 완전히 망가뜨린다.

    계산식::

        delta = ((curr - prev + 2**31) % 2**32) - 2**31

    부호 있는 32비트 범위로 되접는 표준 방식이며, **실제 변화량의 크기가 2**31 미만인 한
    항상 정확하다.** STATUS 는 10Hz 로 오므로 한 주기에 2**31 count(바퀴 약 31,500 회전)를
    넘길 일은 없다.

    Args:
        prev_count: 이전 누적 count.
        curr_count: 현재 누적 count.

    Returns:
        `[-2**31, 2**31)` 범위의 변화량.

    Note:
        실제 변화량이 정확히 `2**31`이면 `+2**31`과 `-2**31`을 구분할 수 없어
        `-2**31`을 돌려준다. 위 전제(주기당 변화량이 훨씬 작음)가 깨지지 않는 한
        도달할 수 없는 경계다.
    """
    return ((curr_count - prev_count + _INT32_HALF) % _INT32_SPAN) - _INT32_HALF


def wheel_distances(
    left_delta_count: int,
    right_delta_count: int,
    geometry: WheelGeometry,
) -> tuple[float, float]:
    """좌우 count 변화량을 좌우 바퀴의 이동 거리로 환산한다.

    Args:
        left_delta_count: 좌측 count 변화량(`encoder_delta()` 결과).
        right_delta_count: 우측 count 변화량.
        geometry: 기구·엔코더 상수.

    Returns:
        `(left_distance_m, right_distance_m)`. 전진이 양수.
    """
    meters_per_count = geometry.meters_per_count
    return (
        left_delta_count * meters_per_count,
        right_delta_count * meters_per_count,
    )


def twist_from_distances(
    left_distance_m: float,
    right_distance_m: float,
    geometry: WheelGeometry,
    dt_sec: float,
) -> tuple[float, float]:
    """좌우 이동 거리와 경과 시간으로 로봇의 선속도·각속도를 구한다.

    계산식::

        v     = (right_distance_m + left_distance_m) / 2 / dt_sec
        omega = (right_distance_m - left_distance_m) / L / dt_sec

    ROS2(REP 103) 규약대로 `omega > 0`이 반시계 방향이다. 오른쪽 바퀴가 더 많이 가면
    좌회전이므로 부호가 맞는다 — `differential_drive.cmd_vel_to_wheel_rad_s()`의 역변환이다.

    Args:
        left_distance_m: 좌측 바퀴 이동 거리 (m).
        right_distance_m: 우측 바퀴 이동 거리 (m).
        geometry: 기구·엔코더 상수.
        dt_sec: 경과 시간 (s). 유한하고 0보다 커야 한다.

    Returns:
        `(linear_x_mps, angular_z_rps)`.

    Raises:
        ValueError: `dt_sec`가 비유한이거나 0 이하일 때.
    """
    if not math.isfinite(dt_sec) or dt_sec <= 0.0:
        raise ValueError(
            f"dt_sec must be a finite value greater than 0.0, got {dt_sec}"
        )

    center_distance_m = (right_distance_m + left_distance_m) / 2.0
    delta_theta_rad = (
        right_distance_m - left_distance_m
    ) / geometry.wheel_separation_m

    return (center_distance_m / dt_sec, delta_theta_rad / dt_sec)


def advance(
    state: OdometryState,
    left_count: int,
    right_count: int,
    geometry: WheelGeometry,
    dt_sec: float,
) -> tuple[OdometryState, float, float]:
    """새 누적 count 를 받아 포즈를 적분하고 속도를 함께 돌려준다.

    포즈 적분은 **midpoint(2차)** 방식이다::

        d_c         = (d_left + d_right) / 2
        delta_theta = (d_right - d_left) / L
        x += d_c * cos(theta + delta_theta / 2)
        y += d_c * sin(theta + delta_theta / 2)
        theta = normalize(theta + delta_theta)

    스텝 중간 방위를 쓰므로, 바퀴 속도가 일정한 원호 구간에서는 **진행 방향이 정확히
    현(chord) 방향과 일치**한다. 남는 오차는 호 길이를 현 길이 대신 쓴 것뿐이라
    `delta_theta`의 제곱에 비례해 매우 작다. 정확한 원호(ICC) 적분은 `delta_theta -> 0`
    분기가 필요한데, 10Hz·저속에서 그 차이는 무시할 수준이라 분기 없는 쪽을 택했다.

    `theta_rad`는 `(-pi, pi]`로 정규화한다. 정규화하지 않으면 제자리 회전이 반복될 때
    값이 무한정 커진다. `nav_msgs/Odometry`는 쿼터니언을 싣기 때문에 누적 회전 수 정보는
    어차피 필요하지 않다.

    Args:
        state: 직전 상태. **변경되지 않는다**(frozen).
        left_count: 새 좌측 누적 count (raw int32).
        right_count: 새 우측 누적 count (raw int32).
        geometry: 기구·엔코더 상수.
        dt_sec: 직전 샘플 이후 경과 시간 (s). 유한하고 0보다 커야 한다.

    Returns:
        `(new_state, linear_x_mps, angular_z_rps)`.

    Raises:
        ValueError: `dt_sec`가 비유한이거나 0 이하일 때.

    Note:
        STM32 재부팅으로 count 가 초기화된 구간에는 이 함수를 쓰면 안 된다.
        그 판단은 호출자의 몫이며 `rebaseline()`을 대신 쓴다.
    """
    left_distance_m, right_distance_m = wheel_distances(
        encoder_delta(state.left_count, left_count),
        encoder_delta(state.right_count, right_count),
        geometry,
    )

    # dt 검증을 여기서 중복하지 않고 twist 계산에 맡긴다 — 검증이 한 곳에만 있게 된다.
    linear_x_mps, angular_z_rps = twist_from_distances(
        left_distance_m, right_distance_m, geometry, dt_sec
    )

    center_distance_m = (right_distance_m + left_distance_m) / 2.0
    delta_theta_rad = (
        right_distance_m - left_distance_m
    ) / geometry.wheel_separation_m
    mid_theta_rad = state.theta_rad + delta_theta_rad / 2.0

    new_state = OdometryState(
        x_m=state.x_m + center_distance_m * math.cos(mid_theta_rad),
        y_m=state.y_m + center_distance_m * math.sin(mid_theta_rad),
        theta_rad=normalize_angle(state.theta_rad + delta_theta_rad),
        left_count=left_count,
        right_count=right_count,
    )

    return (new_state, linear_x_mps, angular_z_rps)


def normalize_angle(angle_rad: float) -> float:
    """각도를 `(-pi, pi]` 범위로 되접는다.

    `math.remainder()`를 쓴다 — `angle - 2*pi*round(angle / (2*pi))`를 반올림 오차 없이
    계산해 주므로, 여러 바퀴를 돈 뒤에도 정밀도가 떨어지지 않는다.

    Args:
        angle_rad: 임의의 각도 (rad).

    Returns:
        `(-pi, pi]` 범위의 각도. 입력이 비유한이면 그대로 전파된다.
    """
    if not math.isfinite(angle_rad):
        return angle_rad

    normalized = math.remainder(angle_rad, 2.0 * math.pi)
    # remainder 는 [-pi, pi] 를 주므로 -pi 만 +pi 로 옮겨 (-pi, pi] 로 맞춘다.
    return math.pi if normalized == -math.pi else normalized
