"""Nav2 네비게이션 스택 런치 (SLAM+Nav 모드).

slam_toolbox가 map→odom TF와 /map을 제공하는 상태에서 실행한다
(choll_slam_bringup/bringup.launch.py 먼저). AMCL/map_server 없이
navigation_launch.py만 포함 — 지도 없이도 "goal 찍으면 주행"이 가능.

파라미터 파일은 실행 시점에 임시 yaml로 다시 써서 넘긴다. 주입하는 것은 두 가지다:

① BackUp 리커버리를 제거한 커스텀 BT 경로
   (behavior_trees/navigate_to_pose_no_backup.xml) — 기본 BT의 BackUp이 카트를
   후진시키기 때문 (후진 금지 설계의 1차 방어).
② 속도 상한 (`max_linear_vel` / `max_angular_vel`, 2026-08-10 도입).
   YAML을 매번 고치지 않고 한 곳에서 주행 성향을 바꾸기 위한 것이다.
   바꾸는 대상은 `_VELOCITY_PATHS`에 명시돼 있다 — DWB(1차 리미터)와
   velocity_smoother(2차·최종 리미터)를 **항상 같이** 바꾼다. 한쪽만 바꾸면
   낮은 쪽이 조용히 clamp해서 값을 올려도 실제 /cmd_vel이 안 바뀐다.

       ros2 launch choll_nav2 nav.launch.py max_linear_vel:=0.25 max_angular_vel:=0.35

🔴 `nav2_common.launch.RewrittenYaml`을 쓰지 않는 이유 (2026-08-10):
   그쪽은 `velocity_smoother.max_velocity[0]` 같은 **리스트 원소를 못 쓴다.**
   `pathify()`는 리스트 인덱스까지 경로로 만들어 주는데(rewritten_yaml.py:169-171)
   정작 대입하는 `updateYamlPathVals()`의 종단 분기가 `yaml[key]`를 문자열 키로
   그대로 쓴다(rewritten_yaml.py:127-128) — 리스트에 닿으면
   `TypeError: list indices must be integers` 로 런치가 죽는다. 실제로 재현했다.
   velocity_smoother의 최종 클램프가 전부 리스트 파라미터라 이 경로는 쓸 수 없다.

cmd_vel 단일화 (2026-08-09 실측 후 도입) — 후진 금지 설계의 2차 방어:
`SetRemap("cmd_vel", "cmd_vel_nav")`로 behavior_server의 출력을
velocity_smoother 입력단에 합류시킨다. 자세한 근거는 아래 GroupAction 주석 참조.

모터리스 벤치 검증:
    ros2 launch choll_nav2 nav.launch.py bench:=true
"""

import os
import tempfile
from typing import Any

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchContext, LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    GroupAction,
    IncludeLaunchDescription,
    OpaqueFunction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import SetRemap

#: 직진/후진 최대 속도 기본값 [m/s].
#: 2026-08-10 실주행 체감 반영 — 종전 실적용값 0.15 의 3배.
DEFAULT_MAX_LINEAR_VEL = "0.45"

#: 회전 최대 속도 기본값 [rad/s].
#: 2026-08-10 실주행 체감 반영 — 종전 실적용값 1.2 의 1/3.
#: 🔴 이 값은 모터 데드존과 정면으로 부딪친다. 0.4 rad/s 제자리 회전은 바퀴
#:    0.4 x 0.19 / 0.065 = 1.169 rad/s = PWM 11.7 (STM 개루프 10 PWM/rad/s,
#:    motor_config.h:119) 로, 실측 바닥 데드존 PWM 10~12 의 **하단 경계**다.
#:    제자리 회전이 아예 안 나오면 (2026-08-07 에 0.6 rad/s 로 겪은 증상)
#:    `--angular` 로 올리거나 stm_serial_bridge 의 `deadzone_wheel_rad_s` 를
#:    켜야 한다. 근거는 nav2_params.yaml 의 max_vel_theta 주석 참조.
DEFAULT_MAX_ANGULAR_VEL = "0.4"

#: 속도 상한을 적용할 YAML 경로. 점으로 구분하며 숫자 성분은 리스트 인덱스다.
#:
#: 🔴 DWB 와 velocity_smoother 를 반드시 같이 바꾼다. DWB 는 1차 리미터,
#:    velocity_smoother 가 최종 리미터라서 둘 중 낮은 쪽이 실제 /cmd_vel 상한이다.
#:    behavior_server(Spin) 도 SetRemap 으로 smoother 를 통과하지만, smoother 가
#:    잘라내기 **전에** 상한을 맞춰 두는 편이 로그가 읽기 쉽다.
#:
#: 여기에 없는 것과 그 이유:
#:    - velocity_smoother.min_velocity[0] (-0.10) : recovery BackUp 전용 후진 허용
#:      값이다. BT 의 backup_speed 0.10 과 한 세트라 배율을 따라가면 안 된다.
#:    - FollowPath.min_vel_x (0.0) : 정상 주행 후진 금지의 유일한 방어.
#:    - acc_lim_* / max_accel / max_decel : 이번 변경 범위 밖(가속도 미조정).
#:    - behavior_server.min_rotational_vel (0.70) : 데드존 탈출 실측값.
#:      Spin 은 min 을 먼저, max 를 나중에 적용하므로 max 보다 커도 무해하다.
_VELOCITY_PATHS: dict[str, tuple[str, ...]] = {
    "linear": (
        "controller_server.ros__parameters.FollowPath.max_vel_x",
        "controller_server.ros__parameters.FollowPath.max_speed_xy",
        "velocity_smoother.ros__parameters.max_velocity.0",
    ),
    "angular": (
        "controller_server.ros__parameters.FollowPath.max_vel_theta",
        "velocity_smoother.ros__parameters.max_velocity.2",
        "behavior_server.ros__parameters.max_rotational_vel",
    ),
    "angular_negated": ("velocity_smoother.ros__parameters.min_velocity.2",),
}

#: 커스텀 BT 경로를 넣을 자리 (yaml 의 `default_nav_to_pose_bt_xml: ""` 치환).
_BT_XML_PATH = "bt_navigator.ros__parameters.default_nav_to_pose_bt_xml"


def _set_path(data: dict, dotted_path: str, value: float | str) -> None:
    """점 경로로 지정한 자리에 값을 넣는다. 숫자 성분은 리스트 인덱스로 본다.

    경로가 없으면 **조용히 넘어가지 않고 예외를 낸다.** 오타 하나로 속도 상한이
    적용 안 된 채 기동하면 증상이 "왜 안 빨라지지"로만 보이기 때문이다 —
    런치 서술 생성 단계에서 죽는 편이 45초 뒤 주행 실패보다 낫다.

    Args:
        data: 파싱된 파라미터 트리 (제자리에서 수정된다).
        dotted_path: 예) `velocity_smoother.ros__parameters.max_velocity.0`.
        value: 넣을 값.

    Raises:
        KeyError: 경로 중간이나 종단이 yaml 에 없을 때.
    """
    keys = dotted_path.split(".")
    node: Any = data
    for key in keys[:-1]:
        try:
            node = node[int(key)] if isinstance(node, list) else node[key]
        except (KeyError, IndexError, ValueError) as exc:
            raise KeyError(f"파라미터 경로를 찾을 수 없다: {dotted_path}") from exc

    leaf = keys[-1]
    if isinstance(node, list):
        index = int(leaf)
        if index >= len(node):
            raise KeyError(f"리스트 범위를 벗어났다: {dotted_path}")
        node[index] = value
    elif leaf in node:
        node[leaf] = value
    else:
        raise KeyError(f"파라미터 경로를 찾을 수 없다: {dotted_path}")


def _write_configured_params(
    source_file: str, bt_xml: str, max_linear: float, max_angular: float
) -> str:
    """원본 파라미터 yaml 에 BT 경로와 속도 상한을 넣어 임시 파일로 쓴다.

    Args:
        source_file: 원본 yaml 경로 (`nav2_params.yaml` 또는 bench 판).
        bt_xml: 주입할 BT xml 절대경로.
        max_linear: 직진/후진 최대 속도 [m/s].
        max_angular: 회전 최대 속도 [rad/s]. 부호는 무시하고 절댓값을 쓴다.

    Returns:
        Nav2 에 넘길 임시 yaml 의 절대경로. `RewrittenYaml` 과 마찬가지로 이
        파일은 지우지 않는다 — 기동 후 실제 적용값을 사람이 확인할 수 있어야 한다.
    """
    with open(source_file) as handle:
        data = yaml.safe_load(handle)

    _set_path(data, _BT_XML_PATH, bt_xml)

    linear = abs(max_linear)
    angular = abs(max_angular)
    for path in _VELOCITY_PATHS["linear"]:
        _set_path(data, path, linear)
    for path in _VELOCITY_PATHS["angular"]:
        _set_path(data, path, angular)
    for path in _VELOCITY_PATHS["angular_negated"]:
        _set_path(data, path, -angular)

    handle_fd, out_path = tempfile.mkstemp(
        prefix="choll_nav2_params_", suffix=".yaml"
    )
    with os.fdopen(handle_fd, "w") as handle:
        yaml.safe_dump(data, handle, default_flow_style=False)
    return out_path


def _configure_navigation(context: LaunchContext) -> list[GroupAction]:
    """런치 인자를 확정하고 Nav2 포함 액션을 만든다.

    `OpaqueFunction` 을 쓰는 이유는 파라미터 yaml 을 **직접 다시 써야** 하기
    때문이다 (모듈 도크스트링의 RewrittenYaml 항목 참조). 값이 확정돼야
    yaml 을 만들 수 있으므로 치환을 여기서 먼저 푼다.

    Args:
        context: 런치 컨텍스트.

    Returns:
        Nav2 를 포함하는 액션 하나짜리 목록.

    Raises:
        RuntimeError: 속도 인자가 숫자가 아니거나 0 이하일 때.
    """
    pkg_dir = get_package_share_directory("choll_nav2")
    nav2_bringup_dir = get_package_share_directory("nav2_bringup")
    no_backup_bt = os.path.join(
        pkg_dir, "behavior_trees", "navigate_to_pose_no_backup.xml"
    )

    def value(name: str) -> str:
        return context.perform_substitution(LaunchConfiguration(name))

    bench = value("bench").strip().lower() in ("true", "1")
    source_file = os.path.join(
        pkg_dir,
        "config",
        "nav2_params_bench.yaml" if bench else "nav2_params.yaml",
    )

    # 🔴 빈 값을 기본값으로 되돌리는 것은 필수다. `DeclareLaunchArgument` 는
    #    **이미 설정된 configuration 을 덮어쓰지 않는다.** 상위 런치
    #    (choll_slam_bringup/demo.launch.py) 가 같은 이름을 빈 문자열 기본값으로
    #    선언해 두면 그 빈 값이 include 스코프로 그대로 상속돼 여기 기본값이
    #    죽는다 — 2026-08-10 실기에서 `max_linear_vel 은 숫자여야 한다: ''` 로
    #    Nav2 단계(26s)에서 스택 전체가 내려가는 것으로 재현했다.
    defaults = {
        "max_linear_vel": DEFAULT_MAX_LINEAR_VEL,
        "max_angular_vel": DEFAULT_MAX_ANGULAR_VEL,
    }
    speeds: dict[str, float] = {}
    for name in ("max_linear_vel", "max_angular_vel"):
        raw = value(name).strip() or defaults[name]
        try:
            speeds[name] = float(raw)
        except ValueError as exc:
            raise RuntimeError(f"{name} 은 숫자여야 한다: '{raw}'") from exc
        if speeds[name] <= 0.0:
            # 0 을 허용하면 그 축이 통째로 죽어 원인을 못 찾는다 (DWB 는 샘플
            # 공간이 비면 "no valid trajectories" 만 남긴다).
            raise RuntimeError(f"{name} 은 0 보다 커야 한다: '{raw}'")

    configured_params = _write_configured_params(
        source_file,
        no_backup_bt,
        speeds["max_linear_vel"],
        speeds["max_angular_vel"],
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
    return [
        GroupAction(
            [
                SetRemap("cmd_vel", "cmd_vel_nav"),
                IncludeLaunchDescription(
                    PythonLaunchDescriptionSource(
                        os.path.join(
                            nav2_bringup_dir, "launch", "navigation_launch.py"
                        )
                    ),
                    launch_arguments={
                        "params_file": configured_params,
                        "use_sim_time": "false",
                        "autostart": value("autostart"),
                        # ⚠ 위 SetRemap의 전제 — True로 바꾸지 말 것 (주석 참조)
                        "use_composition": "False",
                    }.items(),
                ),
            ]
        )
    ]


def generate_launch_description() -> LaunchDescription:
    """Nav2 네비게이션 런치 구성을 생성한다.

    Returns:
        런치 인자 선언과 Nav2 기동을 담은 런치 서술.
    """
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
    max_linear_arg = DeclareLaunchArgument(
        "max_linear_vel",
        default_value=DEFAULT_MAX_LINEAR_VEL,
        description=(
            "직진/후진 최대 속도[m/s]. DWB max_vel_x·max_speed_xy 와 "
            "velocity_smoother max_velocity[x] 를 동시에 덮어쓴다"
        ),
    )
    max_angular_arg = DeclareLaunchArgument(
        "max_angular_vel",
        default_value=DEFAULT_MAX_ANGULAR_VEL,
        description=(
            "회전 최대 속도[rad/s]. DWB max_vel_theta·behavior_server "
            "max_rotational_vel·velocity_smoother max_velocity[theta] 와 "
            "min_velocity[theta](부호 반전) 를 동시에 덮어쓴다"
        ),
    )

    return LaunchDescription(
        [
            bench_arg,
            autostart_arg,
            max_linear_arg,
            max_angular_arg,
            OpaqueFunction(function=_configure_navigation),
        ]
    )
