"""데모 원커맨드 런치 — 라이다부터 MQTT 상행까지 EM 스택 전부.

    ros2 launch choll_slam_bringup demo.launch.py map:=$HOME/maps/library_map.yaml

사람이 쓸 때는 이 파일을 직접 부르기보다 `choll-up` 별칭을 쓴다
(`embedded/Lidar/scripts/choll_up.sh`). 그쪽은 여기에 없는 것 —
낡은 프로세스 정리, AMCL 라이프사이클 강제 활성화, 초기 위치 발행,
기동 후 검증 — 까지 해 준다.

## 무엇이 뜨는가 (기동 순서 = 의존 순서)

    0s  라이다 + scan_mask + base_link->laser_frame static TF
    6s  rf2o (publish_tf:=false — odom->base_link 는 EKF 가 낸다)
   10s  odom_covariance + ZUPT + EKF          -> odom->base_link
   14s  map_server + AMCL                     -> map->odom
   26s  Nav2 (planner/controller/bt/smoother) -> /cmd_vel
   32s  cart_pose_publisher + goal_forwarder  -> /robot_pose, 추종 게이트
   36s  MQTT 브릿지                            -> status/position 등

지연은 임의값이 아니라 실기에서 얻은 것이다. 라이다가 /scan 을 내기 전에 rf2o 가
뜨면 스캔매칭이 빈 입력으로 시작하고, EKF 가 없는데 AMCL 이 뜨면 odom->base_link
가 없어 map->odom 을 못 만든다. Nav2 는 costmap 이 map 을 받아야 활성화된다.

## 여기 없는 것

- **모터(STM32) 브릿지** — 다른 워크스페이스(`ros2_ws`)라 여기서 include 하면
  그 워크스페이스가 소싱 안 된 환경에서 런치 서술 생성 단계부터 죽는다.
  `choll_up.sh` 가 별도로 띄운다.
- **AI 추종 스택** — `choll-em` 별칭(`~/Choll` 에서 실행, 모델을 상대경로로 찾음).
  `choll_up.sh --with-ai` 가 EM 스택 검증 **후에** 띄운다. 순서가 중요하다 —
  AI 를 먼저 띄우면 CPU 경합으로 AMCL 라이프사이클 전환이 타임아웃난다(실측).

🔴 `/cmd_vel` 발행자는 항상 Nav2 `velocity_smoother` 하나여야 한다.
   AI 는 `legacy_control:=false` 로 `/cmd_vel_legacy` 에 격리된다.

## 속도 상한

`max_linear_vel` / `max_angular_vel` 을 그대로 `choll_nav2/nav.launch.py` 에
전달한다. 여기서는 값을 해석하지도 기본값을 두지도 않는다 — 정본은 그쪽의
`DEFAULT_MAX_LINEAR_VEL` / `DEFAULT_MAX_ANGULAR_VEL` 이다.

    ros2 launch choll_slam_bringup demo.launch.py max_linear_vel:=0.25 \\
        max_angular_vel:=0.35
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchContext, LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    OpaqueFunction,
    TimerAction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

#: 각 단계의 기동 지연 [s]. 위 도크스트링의 의존 순서 근거 참조.
DELAY_LASER_ODOM = 6.0
DELAY_EKF = 10.0
DELAY_LOCALIZATION = 14.0
DELAY_NAV2 = 26.0
DELAY_INTERFACE = 32.0
DELAY_MQTT = 36.0


def _include(
    package: str, launch_file: str, arguments: dict[str, str]
) -> IncludeLaunchDescription:
    """다른 패키지의 런치를 인자와 함께 포함한다.

    🔴 arguments 의 값은 **이미 문자열로 확정된 값**이어야 한다.
       `LaunchConfiguration` 객체를 그대로 넘기면 `TimerAction` 으로 지연된
       include 안에서 치환이 하위 런치까지 전달되지 않는다 — 2026-08-10 실측으로
       `map` 이 빈 값이 되어 map_server 가
       `parameter 'yaml_filename' is not initialized` 로 죽고
       lifecycle_manager 가 "Failed to bring up all requested nodes" 로 중단됐다.
       그래서 이 파일은 `OpaqueFunction` 에서 먼저 값을 확정한다.

    Args:
        package: 패키지 이름.
        launch_file: `launch/` 아래 파일 이름.
        arguments: 넘길 런치 인자 (이름 -> **문자열** 값).

    Returns:
        포함 액션.
    """
    path = os.path.join(
        get_package_share_directory(package), "launch", launch_file
    )
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource(path),
        launch_arguments=list(arguments.items()),
    )


def generate_launch_description() -> LaunchDescription:
    """EM 데모 스택 전체의 런치 서술을 만든다.

    Returns:
        단계별 지연이 걸린 포함 액션들의 런치 서술.
    """
    map_arg = DeclareLaunchArgument(
        "map",
        # 🔴 데모장에서 지도를 새로 따면 이 인자만 바꾼다.
        #    BE `library_maps` 에 등록한 지도와 **반드시 같은 파일**이어야
        #    구역 판정·LED 가 맞는다.
        default_value=os.path.expanduser("~/maps/library_map.yaml"),
        description="AMCL/map_server 가 로드할 지도 yaml. 데모장 지도로 교체할 것",
    )
    approach_arg = DeclareLaunchArgument(
        "approach_distance",
        default_value="1.0",
        description="추종 시 사서 앞 유지 거리[m]. 0 이면 사람 좌표를 그대로 goal 로",
    )
    follow_gate_arg = DeclareLaunchArgument(
        "follow_gate_enabled",
        default_value="true",
        choices=["true", "false"],
        description="FOLLOW_START 전까지 /target_position 을 버릴지 여부",
    )
    nav2_arg = DeclareLaunchArgument(
        "nav2",
        default_value="true",
        choices=["true", "false"],
        description="Nav2 기동 여부. false 면 위치 발행까지만 (지도 제작·점검용)",
    )
    # 🔴 기본값을 여기에 적지 않는다 — 정본은 choll_nav2/launch/nav.launch.py 의
    #    DEFAULT_MAX_*_VEL 이고, 두 파일에 복사해 두면 한쪽만 고쳤을 때 갈린다.
    #    빈 문자열은 nav.launch.py 가 "지정 안 함"으로 해석해 자기 기본값을 쓴다.
    #    ⚠️ 여기서 선언하는 것만으로 빈 값이 하위 런치 스코프에 상속되고,
    #       `DeclareLaunchArgument` 는 이미 설정된 값을 덮어쓰지 않는다.
    #       그래서 "안 넘기면 하위 기본값이 산다"가 성립하지 않는다 — 빈 값 처리는
    #       반드시 nav.launch.py 쪽에도 있어야 한다 (2026-08-10 실기에서 재현).
    max_linear_vel_arg = DeclareLaunchArgument(
        "max_linear_vel",
        default_value="",
        description="직진/후진 최대 속도[m/s]. 비우면 nav.launch.py 기본값",
    )
    max_angular_vel_arg = DeclareLaunchArgument(
        "max_angular_vel",
        default_value="",
        description="회전 최대 속도[rad/s]. 비우면 nav.launch.py 기본값",
    )
    mqtt_arg = DeclareLaunchArgument(
        "mqtt",
        default_value="true",
        choices=["true", "false"],
        description="MQTT 브릿지 기동 여부",
    )
    client_id_arg = DeclareLaunchArgument(
        "client_id",
        default_value="choll-jetson-bridge",
        description="MQTT client_id. 🔴 같은 값으로 두 곳에서 붙으면 상호 강퇴된다",
    )

    return LaunchDescription(
        [
            map_arg,
            approach_arg,
            follow_gate_arg,
            nav2_arg,
            max_linear_vel_arg,
            max_angular_vel_arg,
            mqtt_arg,
            client_id_arg,
            OpaqueFunction(function=_stage_everything),
        ]
    )


def _stage_everything(context: LaunchContext) -> list:
    """런치 인자를 문자열로 확정한 뒤 단계별 기동 액션을 만든다.

    `OpaqueFunction` 을 쓰는 이유는 `_include` 도크스트링에 적은 치환 전달
    문제 때문이다. 여기서 `perform_substitution` 으로 값을 먼저 확정하면
    하위 런치가 `TimerAction` 뒤에 떠도 실제 값을 받는다.

    Args:
        context: 런치 컨텍스트 (인자 확정에 사용).

    Returns:
        지연이 걸린 포함 액션 목록.
    """
    def value(name: str) -> str:
        return context.perform_substitution(LaunchConfiguration(name))

    map_path = value("map")
    approach_distance = value("approach_distance")
    follow_gate = value("follow_gate_enabled")
    client_id = value("client_id")
    want_nav2 = value("nav2").lower() in ("true", "1")
    want_mqtt = value("mqtt").lower() in ("true", "1")

    if not os.path.isfile(map_path):
        # 여기서 죽는 편이 낫다 — 지도가 없으면 map_server 가 라이프사이클
        # configure 단계에서 실패하고 AMCL 까지 못 뜨는데, 그 로그는 45초 뒤에야
        # 보인다.
        raise RuntimeError(f"지도 파일이 없다: {map_path}")

    actions = [_include("choll_slam_bringup", "lidar.launch.py", {})]

    actions.append(
        TimerAction(
            period=DELAY_LASER_ODOM,
            # publish_tf:=false — odom->base_link 발행자는 EKF 하나여야 한다.
            actions=[
                _include(
                    "choll_slam_bringup",
                    "laser_odom.launch.py",
                    {"publish_tf": "false"},
                )
            ],
        )
    )
    actions.append(
        TimerAction(
            period=DELAY_EKF,
            actions=[_include("choll_slam_bringup", "ekf.launch.py", {})],
        )
    )
    actions.append(
        TimerAction(
            period=DELAY_LOCALIZATION,
            actions=[
                _include(
                    "choll_nav2", "localization.launch.py", {"map": map_path}
                )
            ],
        )
    )
    if want_nav2:
        # 빈 값은 넘기지 않는다 — 넘기면 nav.launch.py 의 기본값을 빈 문자열로
        # 덮어써서 `float('')` 가 ValueError 로 죽는다.
        nav2_arguments = {
            name: value(name)
            for name in ("max_linear_vel", "max_angular_vel")
            if value(name).strip()
        }
        actions.append(
            TimerAction(
                period=DELAY_NAV2,
                actions=[
                    _include("choll_nav2", "nav.launch.py", nav2_arguments)
                ],
            )
        )
    actions.append(
        TimerAction(
            period=DELAY_INTERFACE,
            actions=[
                _include(
                    "choll_nav",
                    "interface.launch.py",
                    {
                        "approach_distance": approach_distance,
                        "follow_gate_enabled": follow_gate,
                    },
                )
            ],
        )
    )
    if want_mqtt:
        actions.append(
            TimerAction(
                period=DELAY_MQTT,
                actions=[
                    _include(
                        "choll_mqtt_bridge",
                        "bridge.launch.py",
                        {"client_id": client_id},
                    )
                ],
            )
        )
    return actions
