"""slam_toolbox (online async) 매핑 실행.

전제: /scan 토픽과 odom -> base_link TF 가 이미 존재해야 함.
      (lidar.launch.py + laser_odom.launch.py 먼저 실행)
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    share_dir = get_package_share_directory('choll_slam_bringup')
    default_params = os.path.join(share_dir, 'config', 'slam_toolbox_mapping.yaml')

    slam_params_file = LaunchConfiguration('slam_params_file')

    return LaunchDescription([
        DeclareLaunchArgument(
            'slam_params_file',
            default_value=default_params,
            description='slam_toolbox 파라미터 YAML 경로',
        ),
        Node(
            package='slam_toolbox',
            executable='async_slam_toolbox_node',
            name='slam_toolbox',
            output='screen',
            parameters=[slam_params_file],
        ),
    ])
