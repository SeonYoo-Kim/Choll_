"""전체 매핑 스택 원커맨드 실행.

순서: 라이다(0초) -> rf2o 오도메트리(3초) -> slam_toolbox(6초)
/scan 이 먼저 살아있어야 rf2o가 붙고, TF가 준비된 뒤 SLAM이 붙도록 시차를 둠.

실행: ros2 launch choll_slam_bringup bringup.launch.py
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description() -> LaunchDescription:
    launch_dir = os.path.join(
        get_package_share_directory('choll_slam_bringup'), 'launch')

    lidar = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_dir, 'lidar.launch.py')))

    laser_odom = TimerAction(
        period=3.0,
        actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(launch_dir, 'laser_odom.launch.py')))])

    slam = TimerAction(
        period=6.0,
        actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(launch_dir, 'slam.launch.py')))])

    return LaunchDescription([lidar, laser_odom, slam])
