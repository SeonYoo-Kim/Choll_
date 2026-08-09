"""Nav2 네비게이션 스택 런치 (SLAM+Nav 모드).

slam_toolbox가 map→odom TF와 /map을 제공하는 상태에서 실행한다
(choll_slam_bringup/bringup.launch.py 먼저). AMCL/map_server 없이
navigation_launch.py만 포함 — 지도 없이도 "goal 찍으면 주행"이 가능.

파라미터 파일은 RewrittenYaml로 감싸 BackUp 리커버리를 제거한 커스텀 BT
(behavior_trees/navigate_to_pose_no_backup.xml) 경로를 주입한다 —
기본 BT의 BackUp이 카트를 후진시키기 때문 (후진 금지 설계의 1차 방어).

cmd_vel 단일화 (2026-08-09 실측 후 도입) — 후진 금지 설계의 2차 방어:
`SetRemap("cmd_vel", "cmd_vel_nav")`로 behavior_server의 출력을
velocity_smoother 입력단에 합류시킨다. 자세한 근거는 아래 GroupAction 주석 참조.

모터리스 벤치 검증:
    ros2 launch choll_nav2 nav.launch.py bench:=true
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    GroupAction,
    IncludeLaunchDescription,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import SetRemap
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

    # cmd_vel 단일화 — behavior_server를 velocity_smoother 뒤로 보낸다.
    #
    # 왜 필요한가 (2026-08-09 실기 실측):
    #   nav2_bringup/navigation_launch.py는 controller_server(L122)와
    #   velocity_smoother(L182)에만 cmd_vel remap을 주고 behavior_server(L152)에는
    #   주지 않는다. nav2_behaviors/timed_behavior.hpp:130이 상대 이름 "cmd_vel"로
    #   퍼블리셔를 만들므로, Spin/BackUp/DriveOnHeading/Wait 4개 플러그인이
    #   /cmd_vel에 직접 발행해 velocity_smoother를 우회했다 (publisher 4개 실측).
    #   → 속도·가속도 클램프가 안 걸린 명령이 stm_serial_bridge로 직행.
    #
    # 전역 remap 하나로 입력단에 합류시킨다:
    #   controller_server ─┐
    #                      ├→ /cmd_vel_nav → velocity_smoother → /cmd_vel → 브릿지
    #   behavior_server ───┘
    #
    # 다른 노드에 미치는 영향 없음. launch_ros/actions/node.py:468-476이 전역
    # remap을 노드 자체 remap보다 **앞에** 배치하고 rcl은 첫 매칭 규칙을 쓰는데,
    #   - controller_server: 자체 규칙과 동일 → 무변화
    #   - velocity_smoother: 입력은 동일 규칙, 출력은 cmd_vel_smoothed→cmd_vel
    #                        (원본 이름이 달라 이 규칙에 안 걸림) → 무변화
    #   - planner/smoother_server/bt_navigator/waypoint_follower: cmd_vel 없음
    #
    # ⚠ 전제: use_composition=False. ComposableNode는 SetRemap(ros_remaps)을
    #   반영하지 않는다(launch_ros/descriptions/composable_node.py에 처리 없음).
    #   아래 use_composition을 True로 바꾸면 이 우회 차단이 조용히 무효화되므로,
    #   전환 시 반드시 `ros2 topic info /cmd_vel --verbose`로 publisher가
    #   velocity_smoother 1개인지 재확인할 것.
    navigation = GroupAction(
        [
            SetRemap("cmd_vel", "cmd_vel_nav"),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    os.path.join(nav2_bringup_dir, "launch", "navigation_launch.py")
                ),
                launch_arguments={
                    "params_file": configured_params,
                    "use_sim_time": "false",
                    "autostart": LaunchConfiguration("autostart"),
                    # ⚠ 위 SetRemap의 전제 — True로 바꾸지 말 것 (주석 참조)
                    "use_composition": "False",
                }.items(),
            ),
        ]
    )

    return LaunchDescription([bench_arg, autostart_arg, navigation])
