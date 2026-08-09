"""choll_nav 인터페이스 노드 런치 — 파라미터 정본.

cart_pose_publisher(/robot_pose 발행)와 goal_forwarder
(/cart/target_pose·/target_position → Nav2)를 함께 기동한다.

사서 추종은 기본으로 켜져 있다 (approach_distance 1.0 + FOLLOW 버튼 게이트):
- `approach_distance=1.0` — goal 을 사람 위치가 아니라 **1 m 앞**에 찍는다.
  사서가 책을 꺼내려 다가와도 Nav2 는 이미 목표에 도착한 상태라 물러서지 않는다.
  0.0 이면 사람 좌표 자체가 goal 이 되어 카트가 사람을 밀고 들어간다.
- `follow_gate_enabled=true` — FE 추종 버튼(FOLLOW_START)을 받기 전까지
  `/target_position` 을 버린다. 버튼 없이 검증하려면 false 로 띄운다.

    ros2 launch choll_nav interface.launch.py                        # 데모 기본
    ros2 launch choll_nav interface.launch.py follow_gate_enabled:=false
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    """인터페이스 노드 런치 구성을 생성한다."""
    approach_distance_arg = DeclareLaunchArgument(
        "approach_distance",
        # 🔴 이 값이 "후진 금지"의 실체다. 사람 좌표 그대로(0.0)면 Nav2 가 사람을
        #    밀고 들어가고, 사서가 다가오면 카트가 물러선다.
        default_value="1.0",
        description="목표 앞 유지 거리[m]. 사서 추종 1.0(기본), 0=원시 좌표",
    )
    follow_gate_arg = DeclareLaunchArgument(
        "follow_gate_enabled",
        default_value="true",
        choices=["true", "false"],
        description="FOLLOW_START 를 받기 전까지 /target_position 을 버릴지 여부",
    )

    cart_pose_publisher = Node(
        package="choll_nav",
        executable="cart_pose_publisher",
        name="cart_pose_publisher",
        output="screen",
        parameters=[
            {
                # AI-EM ROS2 명세서 ROS2-08 (AI 확정 계약 2026-07-31).
                # BE 등 추가 구독처가 필요하면 이 배열에 토픽만 추가
                "pose_topics": ["/robot_pose"],
                "publish_rate_hz": 10.0,
                "map_frame": "map",
                "base_frame": "base_link",
            }
        ],
    )

    goal_forwarder = Node(
        package="choll_nav",
        executable="goal_forwarder",
        name="goal_forwarder",
        output="screen",
        parameters=[
            {
                "goal_pose_topic": "/cart/target_pose",
                "target_point_topic": "/target_position",
                "cancel_topic": "/cart/cancel",
                "status_topic": "/cart/nav_status",
                "navigate_action": "navigate_to_pose",
                "map_frame": "map",
                "base_frame": "base_link",
                "approach_distance": ParameterValue(
                    LaunchConfiguration("approach_distance"),
                    value_type=float,
                ),
                "auto_orient": True,
                "min_goal_interval_sec": 1.0,
                "min_goal_move_dist": 0.3,
                "server_check_period_sec": 1.0,
                "follow_mode_topic": "/cart/follow_mode",
                "follow_gate_enabled": ParameterValue(
                    LaunchConfiguration("follow_gate_enabled"),
                    value_type=bool,
                ),
            }
        ],
    )

    return LaunchDescription(
        [
            approach_distance_arg,
            follow_gate_arg,
            cart_pose_publisher,
            goal_forwarder,
        ]
    )
