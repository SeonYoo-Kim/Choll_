"""X4Pro 라이다 브링업: ydlidar_ros2_driver_node + base_link->laser_frame 정적 TF.

실행:  ros2 launch choll_slam_bringup lidar.launch.py
확인:  ros2 topic hz /scan   (X4Pro 기본 회전수 기준 6~12 Hz 기대)
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    share_dir = get_package_share_directory('choll_slam_bringup')
    default_params = os.path.join(share_dir, 'config', 'x4pro.yaml')

    params_file = LaunchConfiguration('params_file')

    driver_node = Node(
        package='ydlidar_ros2_driver',
        executable='ydlidar_ros2_driver_node',
        name='ydlidar_ros2_driver_node',
        output='screen',
        emulate_tty=True,
        parameters=[params_file],
    )

    # base_link -> laser_frame 정적 TF
    # TODO(실측 필요): 골조에 라이다를 장착한 뒤 실제 위치를 재서 수정할 것.
    #   --x  : 로봇 중심(base_link)에서 라이다까지 전방(+) 거리 [m]
    #   --y  : 좌측(+) 거리 [m]
    #   --z  : 바닥 기준 높이 [m]  (아래 0.20은 임시 플레이스홀더)
    #   --yaw: 장착 회전 [rad]. 커넥터/모터가 뒤쪽을 향하게 정방향 장착이면 0
    static_tf_node = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_link_to_laser_frame',
        arguments=[
            '--x', '0.0', '--y', '0.0', '--z', '0.20',
            '--roll', '0.0', '--pitch', '0.0', '--yaw', '0.0',
            '--frame-id', 'base_link',
            '--child-frame-id', 'laser_frame',
        ],
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='ydlidar_ros2_driver 파라미터 YAML 경로',
        ),
        driver_node,
        static_tf_node,
    ])
