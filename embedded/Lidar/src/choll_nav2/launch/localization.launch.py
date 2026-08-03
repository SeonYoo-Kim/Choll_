"""저장 지도 기반 위치추정 런치 (map_server + AMCL).

⚠ slam_toolbox(slam.launch.py / bringup.launch.py)와 동시 실행 금지 —
map→odom TF 발행자는 항상 하나여야 한다. 이 런치는 지도 확정 후
매핑 대신 사용한다:
  1. ros2 launch choll_slam_bringup lidar.launch.py   (라이다 + 정적TF)
  2. ros2 launch choll_slam_bringup laser_odom.launch.py  (rf2o)
  3. ros2 launch choll_nav2 localization.launch.py map:=$HOME/maps/library_map.yaml
  4. RViz "2D Pose Estimate"로 초기 위치 지정
  5. ros2 launch choll_nav2 nav.launch.py
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description() -> LaunchDescription:
    """AMCL 위치추정 런치 구성을 생성한다."""
    pkg_dir = get_package_share_directory("choll_nav2")
    nav2_bringup_dir = get_package_share_directory("nav2_bringup")

    map_arg = DeclareLaunchArgument(
        "map",
        default_value=os.path.expanduser("~/maps/library_map.yaml"),
        description="map_server가 로드할 지도 yaml 경로",
    )
    params_arg = DeclareLaunchArgument(
        "params_file",
        default_value=os.path.join(pkg_dir, "config", "nav2_params.yaml"),
        description="AMCL/map_server 파라미터 파일",
    )

    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_bringup_dir, "launch", "localization_launch.py")
        ),
        launch_arguments={
            "map": LaunchConfiguration("map"),
            "params_file": LaunchConfiguration("params_file"),
            "use_sim_time": "false",
            "autostart": "true",
        }.items(),
    )

    return LaunchDescription([map_arg, params_arg, localization])
