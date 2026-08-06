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
    # 장착 확정 (2026-08-06 선반 카트 조립 — 이전 임시 장착에서 z축으로만
    # 이동, 수평 위치 불변): x=0.30(08-05 실측 유지), y=0.0(중심선),
    # yaw=0(기둥 대칭축 실측 +0.51° → 0 확정).
    # z=0.25는 조립 전 값 — 바닥→라이다 광학창 중심 높이 실측 후 갱신(TODO).
    # 2D SLAM에서 z는 기능 영향 없음(RViz 표시용) — 매핑 블로커 아님.
    #   --x  : 로봇 중심(base_link)에서 라이다까지 전방(+) 거리 [m]
    #   --y  : 좌측(+) 거리 [m]
    #   --z  : 바닥 기준 높이 [m]
    static_tf_node = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_link_to_laser_frame',
        arguments=[
            '--x', '0.30', '--y', '0.0', '--z', '0.25',
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
