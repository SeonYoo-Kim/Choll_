"""목표 수신 → Nav2 NavigateToPose 전달 노드.

두 계약을 동시에 지원한다:
- AI 확정 계약(2026-07-31): /target_position (PointStamped, frame=map)
- README 계약: /cart/target_pose (PoseStamped, frame_id 필수 — map 외
  프레임은 TF로 자동 변환)

둘 다 공통 goal 처리 경로로 합류한다. 스로틀은 AI 연속 스트림
(/target_position)에만 적용 — 단발성 수동/BE 명령(/cart/target_pose)은
명시적 의도이므로 항상 선점한다. Nav2 미기동 시에는 /cart/nav_status로
NAV2_UNAVAILABLE을 알리고 goal을 버린다 (노드 자체는 정상 동작 — 배선
검증용).
"""

import functools

import rclpy
import tf2_geometry_msgs  # noqa: F401 — PoseStamped TF 변환 등록(임포트 부수효과)
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PointStamped, PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.action.client import ClientGoalHandle
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)
from rclpy.task import Future
from std_msgs.msg import String
from tf2_ros import Buffer, TransformException, TransformListener

from choll_nav.nav_logic import make_goal_pose_2d, should_send_goal

STATUS_IDLE = "IDLE"
STATUS_NAVIGATING = "NAVIGATING"
STATUS_SUCCEEDED = "SUCCEEDED"
STATUS_ABORTED = "ABORTED"
STATUS_CANCELED = "CANCELED"
STATUS_REJECTED = "REJECTED"
STATUS_NAV2_UNAVAILABLE = "NAV2_UNAVAILABLE"


class GoalForwarder(Node):
    """목표를 Nav2 NavigateToPose 액션으로 전달하는 노드."""

    def __init__(self) -> None:
        """파라미터·구독·발행·액션 클라이언트·워치독을 초기화한다."""
        super().__init__("goal_forwarder")
        self.declare_parameter("goal_pose_topic", "/cart/target_pose")
        self.declare_parameter("target_point_topic", "/target_position")
        self.declare_parameter("cancel_topic", "/cart/cancel")
        self.declare_parameter("status_topic", "/cart/nav_status")
        self.declare_parameter("navigate_action", "navigate_to_pose")
        self.declare_parameter("map_frame", "map")
        self.declare_parameter("base_frame", "base_link")
        self.declare_parameter("approach_distance", 0.0)
        self.declare_parameter("auto_orient", True)
        self.declare_parameter("min_goal_interval_sec", 1.0)
        self.declare_parameter("min_goal_move_dist", 0.3)
        self.declare_parameter("server_check_period_sec", 1.0)

        self._map_frame: str = str(self.get_parameter("map_frame").value)
        self._base_frame: str = str(self.get_parameter("base_frame").value)

        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)

        goal_pose_topic = str(self.get_parameter("goal_pose_topic").value)
        target_point_topic = str(
            self.get_parameter("target_point_topic").value
        )
        if goal_pose_topic:
            self.create_subscription(
                PoseStamped, goal_pose_topic, self._on_target_pose, 10
            )
        if target_point_topic:
            self.create_subscription(
                PointStamped, target_point_topic, self._on_target_point, 10
            )
        self.create_subscription(
            String,
            str(self.get_parameter("cancel_topic").value),
            self._on_cancel,
            10,
        )

        status_qos = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._status_pub = self.create_publisher(
            String, str(self.get_parameter("status_topic").value), status_qos
        )

        self._action_client = ActionClient(
            self,
            NavigateToPose,
            str(self.get_parameter("navigate_action").value),
        )

        self._status: str = ""
        self._active_goal_handle: ClientGoalHandle | None = None
        self._last_sent_xy: tuple[float, float] | None = None
        self._last_sent_time: float | None = None
        # send_goal_async 전송 후 응답 도착 전 창에서의 취소 유실 방지
        self._goal_pending: bool = False
        self._cancel_requested: bool = False

        self._set_status(STATUS_IDLE)
        self.create_timer(
            float(self.get_parameter("server_check_period_sec").value),
            self._check_server,
        )
        self.get_logger().info(
            f"goal_forwarder 시작: goal={goal_pose_topic or '(비활성)'}, "
            f"point={target_point_topic or '(비활성)'}, "
            f"approach_distance="
            f"{float(self.get_parameter('approach_distance').value)}"
        )

    # ── 콜백 ──────────────────────────────────────────────────────────

    def _on_target_pose(self, msg: PoseStamped) -> None:
        """PoseStamped 목표를 처리한다 (README 계약).

        Args:
            msg: 목표 pose. header.frame_id 필수.
        """
        try:
            # 단발성 수동/BE 명령은 명시적 의도 — 스로틀 없이 항상 선점
            # (스로틀에 걸려 조용히 유실되면 명령이 영영 사라짐)
            self._handle_goal(msg, throttle=False)
        except Exception as exc:  # noqa: BLE001 — 콜백은 죽지 않고 로깅
            self.get_logger().error(f"target_pose 처리 실패: {exc}")

    def _on_target_point(self, msg: PointStamped) -> None:
        """PointStamped 목표를 처리한다 (AI 확정 계약).

        방향 정보가 없으므로 미지정 쿼터니언으로 두고 auto_orient에
        맡긴다.

        Args:
            msg: AI가 발행한 목표 지점.
        """
        try:
            pose = PoseStamped()
            pose.header = msg.header
            pose.pose.position.x = msg.point.x
            pose.pose.position.y = msg.point.y
            pose.pose.position.z = 0.0
            self._handle_goal(pose)
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(f"target_position 처리 실패: {exc}")

    def _on_cancel(self, msg: String) -> None:
        """현재 주행을 취소한다. 진행 중인 goal이 없으면 로그만 남긴다.

        Args:
            msg: 취소 요청. data에 BE requestId를 담을 수 있음
                (선택 — 빈 문자열 허용, 상태 추적·로그 대조용).
        """
        try:
            request_id = msg.data.strip()
            tag = f" (requestId={request_id})" if request_id else ""
            acted = False
            if self._goal_pending:
                # goal 응답 대기 창에서 온 취소 — 수락 시점에 즉시 취소하도록 예약
                self._cancel_requested = True
                acted = True
            if (
                self._active_goal_handle is not None
                and self._status == STATUS_NAVIGATING
            ):
                self._active_goal_handle.cancel_goal_async()
                acted = True
            if acted:
                self.get_logger().info(f"주행 취소 요청{tag} → Nav2에 취소 전송")
            else:
                self.get_logger().info(
                    f"취소 요청 수신{tag} — 진행 중인 goal 없음"
                )
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(f"취소 처리 실패: {exc}")

    def _check_server(self) -> None:
        """주행 중 Nav2 서버 소실을 감지하는 워치독 (1Hz)."""
        try:
            if (
                self._status == STATUS_NAVIGATING
                and not self._action_client.server_is_ready()
            ):
                self.get_logger().error(
                    "주행 중 Nav2 액션 서버 소실 → NAV2_UNAVAILABLE"
                )
                self._active_goal_handle = None
                self._set_status(STATUS_NAV2_UNAVAILABLE)
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(f"서버 워치독 실패: {exc}")

    # ── goal 처리 파이프라인 ──────────────────────────────────────────

    def _handle_goal(self, pose: PoseStamped, throttle: bool = True) -> None:
        """공통 goal 처리: 프레임 변환 → 스로틀 → 서버 확인 → 전송.

        Args:
            pose: map 또는 임의 프레임의 목표 pose.
            throttle: 스로틀 적용 여부. AI 연속 스트림은 True,
                단발성 수동/BE 명령은 False (항상 선점).
        """
        if not pose.header.frame_id:
            self.get_logger().error(
                "goal의 header.frame_id가 비어 있음 — frame_id는 필수"
            )
            return
        if pose.header.frame_id != self._map_frame:
            try:
                # 신선한 stamp의 정확 시각 조회는 버퍼 최신 TF보다 미래라
                # ExtrapolationException 유발 — 최신 TF(stamp=0)로 변환.
                # (goal 프레임의 이동 속도 대비 수 ms 오차는 무시 가능)
                pose.header.stamp = rclpy.time.Time().to_msg()
                pose = self._tf_buffer.transform(pose, self._map_frame)
            except TransformException as exc:
                self.get_logger().error(
                    f"goal TF 변환 실패 "
                    f"({pose.header.frame_id}->{self._map_frame}): {exc}"
                )
                return

        target_xy = (pose.pose.position.x, pose.pose.position.y)
        now_sec = self.get_clock().now().nanoseconds * 1e-9
        if throttle and not should_send_goal(
            target_xy,
            now_sec,
            self._last_sent_xy,
            self._last_sent_time,
            self._status == STATUS_NAVIGATING,
            float(self.get_parameter("min_goal_interval_sec").value),
            float(self.get_parameter("min_goal_move_dist").value),
            after_success=self._status == STATUS_SUCCEEDED,
        ):
            return

        if not self._action_client.server_is_ready():
            # 스로틀 상태는 갱신하지 않는다 — Nav2 기동 직후 첫 goal이
            # 스로틀에 걸리지 않게.
            self._set_status(STATUS_NAV2_UNAVAILABLE)
            self.get_logger().warning(
                "Nav2 액션 서버 없음 — goal 무시 (NAV2_UNAVAILABLE)",
                throttle_duration_sec=5.0,
            )
            return

        robot_xy = self._lookup_robot_xy()
        quat_in = pose.pose.orientation
        goal_x, goal_y, quat = make_goal_pose_2d(
            robot_xy,
            target_xy,
            (quat_in.x, quat_in.y, quat_in.z, quat_in.w),
            float(self.get_parameter("approach_distance").value),
            bool(self.get_parameter("auto_orient").value),
        )

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose.header.frame_id = self._map_frame
        goal_msg.pose.header.stamp = self.get_clock().now().to_msg()
        goal_msg.pose.pose.position.x = goal_x
        goal_msg.pose.pose.position.y = goal_y
        goal_msg.pose.pose.orientation.x = quat[0]
        goal_msg.pose.pose.orientation.y = quat[1]
        goal_msg.pose.pose.orientation.z = quat[2]
        goal_msg.pose.pose.orientation.w = quat[3]

        # 새 goal은 그냥 전송 — Nav2 bt_navigator가 기존 goal을 선점한다.
        send_future = self._action_client.send_goal_async(goal_msg)
        send_future.add_done_callback(self._on_goal_response)
        self._goal_pending = True
        self._cancel_requested = False  # 새 goal은 이전 취소 요청을 대체
        self._last_sent_xy = target_xy
        self._last_sent_time = now_sec
        self.get_logger().info(
            f"goal 전송: ({goal_x:.2f}, {goal_y:.2f}) "
            f"[원시 목표 ({target_xy[0]:.2f}, {target_xy[1]:.2f})]"
        )

    def _lookup_robot_xy(self) -> tuple[float, float] | None:
        """TF에서 로봇 현재 위치를 조회한다.

        Returns:
            (x, y) 또는 미확보 시 None.
        """
        try:
            transform = self._tf_buffer.lookup_transform(
                self._map_frame, self._base_frame, rclpy.time.Time()
            )
            return (
                transform.transform.translation.x,
                transform.transform.translation.y,
            )
        except TransformException:
            self.get_logger().warning(
                "로봇 위치(TF map->base_link) 미확보 — 원시 goal 좌표 사용",
                throttle_duration_sec=5.0,
            )
            return None

    # ── 액션 결과 처리 ────────────────────────────────────────────────

    def _on_goal_response(self, future: Future) -> None:
        """Goal 수락/거절 응답을 처리한다.

        Args:
            future: send_goal_async의 future.
        """
        try:
            self._goal_pending = False
            handle = future.result()
            if handle is None or not handle.accepted:
                self._active_goal_handle = None
                self._cancel_requested = False
                self._set_status(STATUS_REJECTED)
                return
            self._active_goal_handle = handle
            self._set_status(STATUS_NAVIGATING)
            handle.get_result_async().add_done_callback(
                functools.partial(self._on_result, handle)
            )
            if self._cancel_requested:
                # 응답 대기 창에서 취소가 왔던 goal — 수락 즉시 취소
                self._cancel_requested = False
                self.get_logger().info("대기 중이던 취소 요청 실행")
                handle.cancel_goal_async()
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(f"goal 응답 처리 실패: {exc}")

    def _on_result(self, handle: ClientGoalHandle, future: Future) -> None:
        """주행 종료 결과를 상태로 반영한다.

        선점되어 교체된 이전 goal의 결과는 무시한다 (핸들 동일성 검사).

        Args:
            handle: 이 결과가 속한 goal 핸들.
            future: get_result_async의 future.
        """
        try:
            if handle is not self._active_goal_handle:
                return
            self._active_goal_handle = None
            status = future.result().status
            if status == GoalStatus.STATUS_SUCCEEDED:
                self._set_status(STATUS_SUCCEEDED)
            elif status == GoalStatus.STATUS_CANCELED:
                self._set_status(STATUS_CANCELED)
            elif status == GoalStatus.STATUS_ABORTED:
                self._set_status(STATUS_ABORTED)
            else:
                self.get_logger().warning(
                    f"예상 밖 GoalStatus={status} → ABORTED로 처리"
                )
                self._set_status(STATUS_ABORTED)
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(f"결과 처리 실패: {exc}")

    def _set_status(self, status: str) -> None:
        """상태를 갱신하고 변화 시에만 발행·로깅한다 (래치 QoS).

        Args:
            status: 새 상태 문자열.
        """
        if status == self._status:
            return
        self.get_logger().info(f"nav_status: {self._status or '(초기)'} → {status}")
        self._status = status
        msg = String()
        msg.data = status
        self._status_pub.publish(msg)


def main(args: list[str] | None = None) -> None:
    """goal_forwarder 노드를 실행한다.

    Args:
        args: rclpy 초기화 인자.
    """
    rclpy.init(args=args)
    node = GoalForwarder()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
