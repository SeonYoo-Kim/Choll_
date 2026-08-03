"""Nav2 네비게이션 스택 런치 (SLAM+Nav 모드).

slam_toolbox가 map→odom TF와 /map을 제공하는 상태에서 실행한다
(choll_slam_bringup/bringup.launch.py 먼저). AMCL/map_server 없이
navigation_launch.py만 포함 — 지도 없이도 "goal 찍으면 주행"이 가능.

파라미터 파일은 RewrittenYaml로 감싸 BackUp 리커버리를 제거한 커스텀 BT
(behavior_trees/navigate_to_pose_no_backup.xml) 경로를 주입한다 —
기본 BT의 BackUp은 velocity_smoother를 우회해 카트를 후진시키기 때문.

모터리스 벤치 검증:
    ros2 launch choll_nav2 nav.launch.py bench:=true
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from nav2_common.launch import RewrittenYaml


def generate_launch_description() -> LaunchDescription:
    """Nav2 네비게이션 런치 구성을 생성한다."""
    pkg_dir = get_package_share_directory("choll_nav2")
    nav2_bringup_dir = get_package_share_directory("nav2_bringup")
    default_params = os.path.join(pkg_dir, "config", "nav2_params.yaml")
    bench_params = os.path.join(pkg_dir, "config", "nav2_params_bench.yaml")
    no_backup_bt = os.path.join(
        pkg_dir, "behavior_trees", "navigate_to_pose_no_backup.xml"
    )

    bench_arg = DeclareLaunchArgument(
        "bench",
        default_value="false",
        description="true면 모터리스 벤치용 파라미터(진행 체크 완화) 사용",
    )
    autostart_arg = DeclareLaunchArgument(
        "autostart",
        default_value="true",
        description="Nav2 라이프사이클 노드 자동 활성화",
    )

    # IfCondition과 동일하게 'true'/'True'/'1' 모두 허용
    params_file = PythonExpression(
        [
            "'",
            bench_params,
            "' if '",
            LaunchConfiguration("bench"),
            "'.strip().lower() in ('true', '1') else '",
            default_params,
            "'",
        ]
    )

    # 커스텀 BT 절대경로 주입 (yaml의 default_nav_to_pose_bt_xml: "" 치환)
    configured_params = RewrittenYaml(
        source_file=params_file,
        param_rewrites={"default_nav_to_pose_bt_xml": no_backup_bt},
        convert_types=True,
    )

    navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_bringup_dir, "launch", "navigation_launch.py")
        ),
        launch_arguments={
            "params_file": configured_params,
            "use_sim_time": "false",
            "autostart": LaunchConfiguration("autostart"),
            # 노트북 단계는 프로세스 분리(디버깅 용이). Jetson에서는 True 검토
            "use_composition": "False",
        }.items(),
    )

    return LaunchDescription([bench_arg, autostart_arg, navigation])
