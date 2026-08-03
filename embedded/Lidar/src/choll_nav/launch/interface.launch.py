"""choll_nav 인터페이스 노드 런치 — 파라미터 정본.

cart_pose_publisher(/robot_pose 발행)와 goal_forwarder
(/cart/target_pose·/target_position → Nav2)를 함께 기동한다.

사서 추종 모드:
    ros2 launch choll_nav interface.launch.py approach_distance:=1.0
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
        default_value="0.0",
        description="목표 앞 유지 거리[m]. 사서 추종 시 1.0 권장, 0=원시 좌표",
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
            }
        ],
    )

    return LaunchDescription(
        [approach_distance_arg, cart_pose_publisher, goal_forwarder]
    )
