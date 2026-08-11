"""RViz 시각화 런치.

QoS가 미리 반영된 설정(config/view.rviz)으로 RViz를 연다:
- LaserScan Reliability = Best Effort (드라이버가 센서 QoS로 발행)
- Map Durability = Transient Local (slam_toolbox 래치 발행)
- Fixed Frame = map (라이다 단독 테스트 시 laser_frame으로 수동 변경)
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """RViz 런치 구성을 생성한다."""
    rviz_config = os.path.join(
        get_package_share_directory("choll_nav"), "config", "view.rviz"
    )
    rviz = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        output="screen",
        arguments=["-d", rviz_config],
    )
    return LaunchDescription([rviz])
