"""choll_mqtt_bridge 런치 — 파라미터 정본.

BE 브로커 접속 정보와 토픽 매핑을 한곳에서 관리한다. 노트북 검증 시
Jetson과 client_id가 겹치지 않게 client_id:=choll-laptop-bridge 로 실행.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """MQTT 브릿지 노드 런치 구성을 생성한다."""
    client_id_arg = DeclareLaunchArgument(
        "client_id",
        default_value="choll-jetson-bridge",
        description="MQTT 클라이언트 ID (기기마다 달라야 함 — 중복 시 상호 강퇴)",
    )

    bridge = Node(
        package="choll_mqtt_bridge",
        executable="mqtt_bridge",
        name="mqtt_bridge",
        output="screen",
        parameters=[
            {
                "broker_host": "your-server.example.com",
                "broker_port": 1883,
                "username": "choll",
                "password": "CHANGE_ME",
                "client_id": LaunchConfiguration("client_id"),
                # EM-BE MQTT 명세서 (상행 status/*, 하행 cmd/*)
                "cmd_topic": "cmd/move/cart",  # MQTT-04 (BE→Jetson)
                "position_topic": "status/position",  # MQTT-01 (Jetson→BE)
                "position_min_period_sec": 0.5,  # 2Hz — TODO-확인(BE)
                "nav_result_topic": "status/nav-result",  # (Jetson→BE)
                # AI-EM ROS2 명세서
                "pose_topic": "/robot_pose",  # ROS2-08
                "target_pose_topic": "/cart/target_pose",  # ROS2-14
                "cancel_topic": "/cart/cancel",  # ROS2-15
                "nav_status_topic": "/cart/nav_status",  # ROS2-16 (래치)
            }
        ],
    )

    return LaunchDescription([client_id_arg, bridge])
