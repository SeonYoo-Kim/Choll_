"""휠 오도메트리 노드 — `/stm/encoder_total` 을 구독해 `/wheel/odom` 을 발행한다.

`stm_serial_bridge` 노드와 **분리된 별도 노드**다. Serial 포트를 열지 않으며,
브리지가 이미 발행 중인 토픽만 구독한다. 포트 소유자는 여전히 브리지 하나다.

```
STM32 -> stm_serial_bridge -> /stm/encoder_total -> wheel_odometry -> /wheel/odom
```

계산은 전부 순수 모듈 `wheel_odometry.py` 가 한다. 이 파일의 책임은 ROS 배선
(파라미터·구독·발행·시각 측정)뿐이다.

## 의도적으로 하지 않는 것

- **TF 를 발행하지 않는다.** `odom -> base_link` TF 는 이후 LiDAR 오도메트리와 융합하는
  **EKF 가 담당**한다. 여기서 TF 를 쏘면 EKF 와 충돌한다.
- **`/odom` 을 발행하지 않는다.** 이 노드의 출력은 EKF 의 **입력 하나**이지 최종
  오도메트리가 아니다. 그래서 토픽 이름도 `/wheel/odom` 이다.
- **`/stm/wheel_actual_rad_s` 를 쓰지 않는다.** 그 값은 펌웨어의 명목 상수
  77520 count/wheel-rev 기준이라 실제보다 약 12% 작다. 속도는 `encoder_total` 변화량과
  실측 기준값 68160(`counts_per_wheel_rev`)으로만 계산한다.
  (근거: embedded/motor/docs/serial_protocol.md "펌웨어와 ROS의 스케일 불일치" 절)
- **EKF 관련 코드는 없다.**

## ⚠️ 아직 처리하지 않는 것 — STM32 재부팅

첫 `encoder_total` 수신 시에만 적분 없이 기준을 잡는다(`initial_state()`). 그러나
**실행 중 STM32 가 재부팅해 카운터가 0 으로 돌아가는 경우는 아직 탐지하지 않는다.**
그런 일이 벌어지면 포즈가 크게 튄다.

순수 모듈에 `rebaseline()` 이 준비돼 있지만 **호출 조건(= reset 탐지 방법)이 아직
정해지지 않았다.** 특히 `/stm/connected` 의 false -> true 전이만으로는 충분하지 않다 —
STATUS 가 끊기지 않을 만큼 빠른 재부팅이나, 연결이 유지된 채 카운터만 초기화되는 경로를
놓칠 수 있다. 탐지 방법을 확정한 뒤 별도 단계에서 붙인다.

## ⚠️ 공분산은 0으로 남아 있다

`nav_msgs/Odometry` 의 `pose.covariance` / `twist.covariance` 를 채우지 않았다. 근거 있는
값이 없는 상태에서 숫자를 지어내지 않기 위해서다. **EKF 에 연결하기 전에 반드시 설정해야
한다** — 0 을 "오차가 없다"로 해석하는 융합기가 있다.
"""

import math
import time
from collections.abc import Sequence

import rclpy
from nav_msgs.msg import Odometry
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Int32MultiArray

from stm_serial_bridge.wheel_odometry import (
    OdometryState,
    WheelGeometry,
    advance,
    initial_state,
)

#: 구독 토픽. `stm_serial_bridge_node.ENCODER_TOTAL_TOPIC` 과 같아야 한다
#: (테스트가 두 값의 일치를 강제한다). 노드 간 결합을 만들지 않으려고 import 대신
#: 각자 정의하고, 어긋남은 테스트로 잡는다.
ENCODER_TOTAL_TOPIC = "/stm/encoder_total"

#: 발행 토픽. **최종 `/odom` 이 아니다** — EKF 의 입력 하나다.
WHEEL_ODOM_TOPIC = "/wheel/odom"

#: 브리지의 STATUS 계열 발행 depth 와 같은 값.
ODOM_QOS_DEPTH = 10

EXIT_SUCCESS = 0
EXIT_FAILURE = 1

#: `main()` 의 spin 루프가 한 번에 대기하는 시간(초).
SPIN_TIMEOUT_SEC = 0.1

COVARIANCE_NOTICE = (
    "pose/twist covariance는 0으로 남겨둔다 — 근거 있는 값이 아직 없다. "
    "EKF에 연결하기 전에 반드시 설정할 것 (0을 '오차 없음'으로 읽는 융합기가 있다)."
)


def extract_encoder_counts(data: Sequence[int]) -> tuple[int, int]:
    """`Int32MultiArray.data` 에서 좌우 누적 count 를 꺼낸다.

    브리지는 `[left, right]` 순서로 원소 2개를 싣는다. 좌우 매핑은 2026-08-03 실기에서
    확정됐다(물리 왼쪽 바퀴 ↔ `data[0]`).

    Args:
        data: 수신한 메시지의 `data` 필드.

    Returns:
        `(left_count, right_count)`.

    Raises:
        ValueError: 원소 수가 2가 아닐 때. 실제 길이를 메시지에 담는다.
    """
    if len(data) != 2:
        raise ValueError(
            f"encoder_total must have exactly 2 elements [left, right], "
            f"got {len(data)}"
        )
    return (int(data[0]), int(data[1]))


def yaw_to_quaternion(yaw_rad: float) -> tuple[float, float, float, float]:
    """평면 yaw 를 쿼터니언으로 바꾼다.

    z 축 회전만 있으므로 x·y 성분은 0이다.

    Args:
        yaw_rad: yaw 각 (rad).

    Returns:
        `(x, y, z, w)` 순서의 쿼터니언.
    """
    half = yaw_rad / 2.0
    return (0.0, 0.0, math.sin(half), math.cos(half))


class WheelOdometryNode(Node):
    """Integrate `/stm/encoder_total` into a `/wheel/odom` pose and twist.

    생성은 두 단계다: `__init__` 은 파라미터만 준비하고, `start()` 가 값을 검증한 뒤에야
    발행자와 구독을 만든다. 잘못된 파라미터로는 구독조차 시작되지 않는 것이 구조적으로
    보장된다(`stm_serial_bridge` 노드와 같은 방식).
    """

    def __init__(self) -> None:
        """Declare and log parameters. 구독·발행은 모두 `start()` 에서 한다."""
        super().__init__("wheel_odometry")

        # ⚠️ 2026-08-08 실기 1m 직진 x3 으로 보정한 값이며, 브리지의 0.065 와 **다르다.**
        # 보고 이동거리가 실제보다 평균 10.7% 컸다(1.1012/1.1136/1.1055 m) → 0.065/1.1068.
        # 이것은 "바퀴 반지름 실측치"가 아니라 (유효 구름반지름 + 슬립 + counts_per_rev 오차)를
        # 전부 흡수한 **거리 스케일 보정 상수**다. 직진 시험은 `2*pi*r / counts_per_rev` 라는
        # 곱만 관측하므로 r 과 counts_per_rev 를 분리할 수 없다.
        # 브리지의 wheel_radius_m 은 엔코더가 개입하지 않는 **명령 기구학**에 쓰이므로
        # 이 보정을 옮기지 않았다(config/wheel_odometry.yaml 주석 참고).
        self.declare_parameter("wheel_radius_m", 0.0587)
        self.declare_parameter("wheel_separation_m", 0.38)
        # 2026-08-08 실측 기준값(좌우 공통). ⚠️ 펌웨어 명목값 77520 이 아니다.
        self.declare_parameter("counts_per_wheel_rev", 68160.0)
        # 발행 메시지의 frame. TF 는 발행하지 않으므로 이 값들은 **메시지 라벨일 뿐**이며,
        # odom -> base_link 변환을 실제로 방송하는 것은 이후의 EKF 다.
        self.declare_parameter("odom_frame_id", "odom")
        self.declare_parameter("base_frame_id", "base_link")

        self._log_parameters()

        self._geometry: WheelGeometry | None = None
        self._odom_frame_id = ""
        self._base_frame_id = ""

        # None = 아직 첫 encoder_total 을 받지 않음.
        self._state: OdometryState | None = None
        self._last_sample_time_sec: float | None = None

        self._odom_publisher: object | None = None
        self._subscription: object | None = None

        self._sample_count = 0
        self._malformed_count = 0
        self._skipped_dt_count = 0

    def start(self) -> None:
        """Validate parameters, then create the publisher and subscription.

        Raises:
            ValueError: 기구 상수가 0 이하·비유한이거나 frame id 가 빈 문자열일 때.
                `WheelGeometry` 가 던지는 메시지를 그대로 전달한다 — 검증을 중복해서
                구현하지 않는다.
        """
        self._geometry = WheelGeometry(
            wheel_radius_m=float(self._param_value("wheel_radius_m")),
            wheel_separation_m=float(self._param_value("wheel_separation_m")),
            counts_per_wheel_rev=float(self._param_value("counts_per_wheel_rev")),
        )
        self._odom_frame_id = self._validated_frame_id("odom_frame_id")
        self._base_frame_id = self._validated_frame_id("base_frame_id")

        self._odom_publisher = self.create_publisher(
            Odometry, WHEEL_ODOM_TOPIC, ODOM_QOS_DEPTH
        )
        self._subscription = self.create_subscription(
            Int32MultiArray,
            ENCODER_TOTAL_TOPIC,
            self._on_encoder_total,
            ODOM_QOS_DEPTH,
        )

        self.get_logger().info(
            f"wheel_odometry 시작: {ENCODER_TOTAL_TOPIC} -> {WHEEL_ODOM_TOPIC} "
            f"(m/count={self._geometry.meters_per_count:.9f})"
        )
        self.get_logger().info("TF는 발행하지 않는다 — odom -> base_link는 EKF의 몫이다.")
        self.get_logger().warning(COVARIANCE_NOTICE)

    def _on_encoder_total(self, message: Int32MultiArray) -> None:
        """Integrate one encoder sample and publish the resulting odometry.

        첫 샘플에서는 **적분하지 않고 기준만 잡는다** — 비교할 이전 count 도, 경과 시간도
        없기 때문이다. 이때는 발행하지 않는다. 속도를 0으로 지어내 발행하면 소비하는 쪽이
        "정지해 있다는 측정"으로 받아들이게 된다.

        Args:
            message: `/stm/encoder_total` 메시지 (`[left, right]`).
        """
        try:
            left_count, right_count = extract_encoder_counts(message.data)
        except ValueError as error:
            self._malformed_count += 1
            self.get_logger().warning(
                f"encoder_total 무시 (#{self._malformed_count}): {error}"
            )
            return

        now_sec = self._now_sec()

        if self._state is None:
            self._state = initial_state(left_count, right_count)
            self._last_sample_time_sec = now_sec
            self.get_logger().info(
                f"첫 encoder_total: 적분 없이 기준만 잡는다 "
                f"(L={left_count}, R={right_count})"
            )
            return

        dt_sec = now_sec - float(self._last_sample_time_sec or 0.0)
        if dt_sec <= 0.0:
            # 기준(count·시각)을 **그대로 둔다.** 여기서 기준을 갱신하면 이번 구간의
            # 이동량이 통째로 버려져 포즈에 영구 오차가 남는다. 그대로 두면 다음
            # 샘플이 이번 구간까지 함께 적분한다.
            self._skipped_dt_count += 1
            self.get_logger().warning(
                f"dt={dt_sec:.6f}s 는 적분할 수 없어 이번 샘플을 건너뛴다 "
                f"(#{self._skipped_dt_count}). 기준은 유지되므로 포즈는 손실되지 않는다."
            )
            return

        self._state, linear_x_mps, angular_z_rps = advance(
            self._state, left_count, right_count, self._geometry, dt_sec
        )
        self._last_sample_time_sec = now_sec
        self._sample_count += 1

        self._publish_odometry(self._state, linear_x_mps, angular_z_rps)

    def _publish_odometry(
        self, state: OdometryState, linear_x_mps: float, angular_z_rps: float
    ) -> None:
        """Fill and publish one `nav_msgs/Odometry` message.

        ⚠️ `pose.covariance` / `twist.covariance` 는 **0으로 남긴다.** 근거 있는 값이
        없어서이며, EKF 연결 전에 반드시 채워야 한다(모듈 docstring 참고).

        Args:
            state: 적분된 포즈.
            linear_x_mps: 선속도 (m/s).
            angular_z_rps: 각속도 (rad/s).
        """
        message = Odometry()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = self._odom_frame_id
        message.child_frame_id = self._base_frame_id

        message.pose.pose.position.x = state.x_m
        message.pose.pose.position.y = state.y_m
        message.pose.pose.position.z = 0.0

        quaternion_x, quaternion_y, quaternion_z, quaternion_w = yaw_to_quaternion(
            state.theta_rad
        )
        message.pose.pose.orientation.x = quaternion_x
        message.pose.pose.orientation.y = quaternion_y
        message.pose.pose.orientation.z = quaternion_z
        message.pose.pose.orientation.w = quaternion_w

        # 차동구동은 옆으로 미끄러지지 않으므로 linear.y/z 와 angular.x/y 는 0이다.
        message.twist.twist.linear.x = linear_x_mps
        message.twist.twist.angular.z = angular_z_rps

        self._odom_publisher.publish(message)

    @staticmethod
    def _now_sec() -> float:
        """Return the monotonic timestamp used for every dt calculation.

        시스템 시계(wall clock)가 아니라 `time.monotonic()` 을 쓴다 — 시스템 시간이
        바뀌어도 경과 시간이 뒤틀리지 않는다. 메시지 `header.stamp` 는 소비자를 위한
        ROS 시각이므로 별개로 둔다.

        ⚠️ 펌웨어 STATUS 에는 타임스탬프가 없다. 그래서 dt 는 **수신 시각 차이**일 수밖에
        없고, 그 지터는 속도에만 실린다(포즈는 count 로만 결정되므로 영향받지 않는다).

        Returns:
            단조 증가 시각(초).
        """
        return time.monotonic()

    def _validated_frame_id(self, name: str) -> str:
        """Return a non-empty frame id parameter.

        Args:
            name: 파라미터 이름.

        Returns:
            공백을 제거한 frame id.

        Raises:
            ValueError: 값이 비어 있거나 공백뿐일 때.
        """
        value = str(self._param_value(name)).strip()
        if not value:
            raise ValueError(f"{name} must not be empty")
        return value

    def _param_value(self, name: str) -> object:
        """Return the current value of a declared parameter.

        Args:
            name: 선언된 파라미터 이름.

        Returns:
            파라미터의 현재 값.
        """
        return self.get_parameter(name).value

    def _log_parameters(self) -> None:
        """Log every declared parameter once at startup."""
        logger = self.get_logger()
        logger.info("파라미터:")
        logger.info(f"  wheel_radius_m       = {self._param_value('wheel_radius_m')}")
        logger.info(
            f"  wheel_separation_m   = {self._param_value('wheel_separation_m')}"
            "  <-- 2026-08-04 실측"
        )
        logger.info(
            f"  counts_per_wheel_rev = {self._param_value('counts_per_wheel_rev')}"
            "  <-- 2026-08-08 실측(좌우 공통). ⚠️ 펌웨어 명목 77520 과 다름"
        )
        logger.info(f"  odom_frame_id        = {self._param_value('odom_frame_id')}")
        logger.info(f"  base_frame_id        = {self._param_value('base_frame_id')}")

    @property
    def state(self) -> OdometryState | None:
        """현재 적분 상태. 첫 샘플 전에는 None."""
        return self._state


def main(args: Sequence[str] | None = None) -> int:
    """Start the wheel_odometry node.

    Args:
        args: ROS2 인자. None 이면 sys.argv 를 사용한다.

    Returns:
        프로세스 종료 코드.
    """
    rclpy.init(args=args)
    node = WheelOdometryNode()

    try:
        node.start()
    except ValueError as error:
        node.get_logger().error(f"노드를 시작할 수 없다: {error}")
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        return EXIT_FAILURE

    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=SPIN_TIMEOUT_SEC)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    return EXIT_SUCCESS
