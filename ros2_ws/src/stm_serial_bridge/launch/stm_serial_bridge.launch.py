"""stm_serial_bridge 통합 실행 launch — 하드웨어 모드와 mock/PTY 모드를 한 파일로 다룬다.

공통 파라미터는 `config/stm_serial_bridge.yaml` 이 정본이고, launch 인자는 그 위에
개별 값만 덮어쓴다.

하드웨어 모드 (기본)::

    ros2 launch stm_serial_bridge stm_serial_bridge.launch.py
    ros2 launch stm_serial_bridge stm_serial_bridge.launch.py serial_port:=/dev/ttyACM1

mock/PTY 모드 (하드웨어 없이)::

    ros2 launch stm_serial_bridge stm_serial_bridge.launch.py mode:=mock

    # STATUS 를 5초 뒤 끊어 connected=false 타임아웃까지 확인
    ros2 launch stm_serial_bridge stm_serial_bridge.launch.py mode:=mock \\
        mock_stop_after_sec:=5.0

⚠️ `mode:=mock` 은 실제 장치를 절대 열지 않는다. mock 이 만든 PTY symlink 를
   `serial_port` 로 강제 덮어쓰므로, YAML 의 `/dev/ttyACM0` 값은 무시된다.

⚠️ mock 은 STM32 를 **모방**할 뿐이다. 수치 정확도(엔코더 스케일 등)는 검증할 수 없고,
   검증 대상은 "STATUS → 파싱 → 토픽 발행" 경로와 형식뿐이다.

속도 프로파일 (`max_wheel_rad_s` 상한을 단계적으로 올리기 위한 장치)::

    # bench(기본, 1.0) — base YAML 값 그대로
    ros2 launch stm_serial_bridge stm_serial_bridge.launch.py

    # slow(2.0) — 최초 통합 테스트 권장
    ros2 launch stm_serial_bridge stm_serial_bridge.launch.py speed_profile:=slow

    # nav2(6.0) — ⚠️ 실기 미검증
    ros2 launch stm_serial_bridge stm_serial_bridge.launch.py speed_profile:=nav2

    # 임의값 — 프로파일보다 우선한다
    ros2 launch stm_serial_bridge stm_serial_bridge.launch.py max_wheel_rad_s:=3.5

**파라미터 우선순위** (뒤가 앞을 덮어쓴다)::

    ① config/stm_serial_bridge.yaml           (base, 정본)
    ② config/speed_profile_<profile>.yaml     (speed_profile 오버레이. bench 는 없음)
    ③ launch 인자 (max_wheel_rad_s, serial_port / mock 의 PTY 경로)

⚠️ `speed_profile` 에 알 수 없는 값을 주면 **조용히 기본값으로 대체하지 않고 실패**한다.
"""

import os

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    LogInfo,
    OpaqueFunction,
    TimerAction,
)
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

PACKAGE_NAME = "stm_serial_bridge"

MODE_HARDWARE = "hardware"
MODE_MOCK = "mock"

# 속도 프로파일 -> 오버레이 YAML 파일명. None 이면 base YAML 값을 그대로 쓴다.
#
# 값의 근거와 위험은 각 YAML 파일 주석에 있다. 요약: Nav2 봉투(v=0.3, ω=0.6)를
# 무축소로 수용하려면 6.0 rad/s 가 필요하지만(`required_max_wheel_rad_s()` 참고)
# 실기 미검증이므로 기본값은 기존 벤치 안전값 1.0 을 유지한다.
SPEED_PROFILE_BENCH = "bench"
SPEED_PROFILE_SLOW = "slow"
SPEED_PROFILE_NAV2 = "nav2"
SPEED_PROFILE_FILES: dict[str, str | None] = {
    SPEED_PROFILE_BENCH: None,
    SPEED_PROFILE_SLOW: "speed_profile_slow.yaml",
    SPEED_PROFILE_NAV2: "speed_profile_nav2.yaml",
}

# mock 프로세스가 PTY 를 만들고 symlink 를 걸기까지 기다리는 시간.
# 브리지는 포트 open 실패 시 재시도 없이 종료하므로 순서를 보장해야 한다.
MOCK_BRIDGE_START_DELAY_SEC = 2.0


def _launch_setup(context, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN201, ARG001
    """`mode` 값에 따라 실행할 액션을 결정한다.

    launch 인자는 실행 시점에야 값이 확정되므로 `OpaqueFunction` 안에서 분기한다.

    Returns:
        실행할 launch 액션 목록.

    Raises:
        RuntimeError: `mode` 가 `hardware`/`mock` 이 아닐 때, `speed_profile` 이 알 수
            없는 값일 때, `max_wheel_rad_s` 가 float 로 해석되지 않을 때.
    """
    mode = LaunchConfiguration("mode").perform(context)
    params_file = LaunchConfiguration("params_file").perform(context)
    serial_port = LaunchConfiguration("serial_port").perform(context)
    speed_profile = LaunchConfiguration("speed_profile").perform(context)
    max_wheel_rad_s = LaunchConfiguration("max_wheel_rad_s").perform(context)
    mock_pty_link = LaunchConfiguration("mock_pty_link").perform(context)
    mock_stop_after_sec = LaunchConfiguration("mock_stop_after_sec").perform(context)
    mock_fault_after_sec = LaunchConfiguration("mock_fault_after_sec").perform(context)
    log_level = LaunchConfiguration("log_level").perform(context)

    if mode not in (MODE_HARDWARE, MODE_MOCK):
        msg = f"mode must be '{MODE_HARDWARE}' or '{MODE_MOCK}', got '{mode}'"
        raise RuntimeError(msg)

    # 알 수 없는 프로파일은 조용히 기본값으로 떨어지지 않게 여기서 실패시킨다.
    # (DeclareLaunchArgument 의 choices 가 1차 방어, 이 검사가 2차 방어)
    if speed_profile not in SPEED_PROFILE_FILES:
        valid = ", ".join(sorted(SPEED_PROFILE_FILES))
        msg = (
            f"speed_profile must be one of [{valid}], got '{speed_profile}'"
        )
        raise RuntimeError(msg)

    # ① base YAML -> ② 프로파일 오버레이 -> ③ launch 인자. 뒤가 앞을 덮어쓴다.
    param_sources: list[object] = [params_file]

    profile_basename = SPEED_PROFILE_FILES[speed_profile]
    if profile_basename is not None:
        package_share = FindPackageShare(PACKAGE_NAME).perform(context)
        param_sources.append(
            os.path.join(package_share, "config", profile_basename)
        )

    overrides: dict[str, object] = {}
    if mode == MODE_MOCK:
        # mock 모드는 실제 장치를 열 수 없도록 항상 PTY 경로를 강제한다.
        overrides["serial_port"] = mock_pty_link
    elif serial_port:
        overrides["serial_port"] = serial_port

    if max_wheel_rad_s:
        try:
            overrides["max_wheel_rad_s"] = float(max_wheel_rad_s)
        except ValueError as error:
            msg = (
                f"max_wheel_rad_s must be a float, got '{max_wheel_rad_s}'"
            )
            raise RuntimeError(msg) from error

    if overrides:
        param_sources.append(overrides)

    bridge_node = Node(
        package=PACKAGE_NAME,
        executable="stm_serial_bridge_node",
        name="stm_serial_bridge",
        output="screen",
        emulate_tty=True,
        parameters=param_sources,
        arguments=["--ros-args", "--log-level", log_level],
    )

    if max_wheel_rad_s:
        speed_description = (
            f"max_wheel_rad_s={max_wheel_rad_s} (launch 인자가 프로파일을 덮어씀)"
        )
    elif profile_basename is None:
        speed_description = (
            f"speed_profile={speed_profile} (base YAML 값 사용, 오버레이 없음)"
        )
    else:
        speed_description = f"speed_profile={speed_profile} ({profile_basename})"
    speed_info = LogInfo(msg=f"[launch] 속도 상한: {speed_description}")

    if mode == MODE_HARDWARE:
        return [
            LogInfo(
                msg=(
                    "[launch] mode=hardware — 실제 Serial 포트를 연다. "
                    "바퀴를 공중에 띄운 상태에서만 실행할 것."
                ),
            ),
            speed_info,
            bridge_node,
        ]

    mock_command = [
        "ros2",
        "run",
        PACKAGE_NAME,
        "mock_stm",
        "--link",
        mock_pty_link,
        "--stop-after-sec",
        mock_stop_after_sec,
        "--fault-after-sec",
        mock_fault_after_sec,
    ]

    return [
        LogInfo(
            msg=(
                f"[launch] mode=mock — 실제 장치를 열지 않는다. PTY={mock_pty_link} "
                f"(브리지는 {MOCK_BRIDGE_START_DELAY_SEC}s 뒤 기동)"
            ),
        ),
        speed_info,
        ExecuteProcess(cmd=mock_command, output="screen", emulate_tty=True),
        TimerAction(period=MOCK_BRIDGE_START_DELAY_SEC, actions=[bridge_node]),
    ]


def generate_launch_description() -> LaunchDescription:
    """launch 인자를 선언하고 설정 함수를 연결한다.

    Returns:
        LaunchDescription.
    """
    default_params_file = [
        FindPackageShare(PACKAGE_NAME),
        "/config/stm_serial_bridge.yaml",
    ]

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "mode",
                default_value=MODE_HARDWARE,
                choices=[MODE_HARDWARE, MODE_MOCK],
                description=(
                    "hardware = 실제 Serial 포트, mock = PTY 기반 테스트 "
                    "(실제 장치를 열지 않음)"
                ),
            ),
            DeclareLaunchArgument(
                "params_file",
                default_value=default_params_file,
                description="공통 파라미터 YAML 경로",
            ),
            DeclareLaunchArgument(
                "serial_port",
                default_value="",
                description=(
                    "비우면 YAML 값을 쓴다. 하드웨어 교체 시 이 인자만 바꾸면 된다 "
                    "(mode:=mock 에서는 무시된다)"
                ),
            ),
            DeclareLaunchArgument(
                "speed_profile",
                default_value=SPEED_PROFILE_BENCH,
                choices=sorted(SPEED_PROFILE_FILES),
                description=(
                    "바퀴 각속도 상한 프로파일. "
                    f"{SPEED_PROFILE_BENCH}=1.0(기본, 실기 검증됨) / "
                    f"{SPEED_PROFILE_SLOW}=2.0(최초 통합 권장) / "
                    f"{SPEED_PROFILE_NAV2}=6.0(Nav2 봉투 전체, ⚠️ 실기 미검증)"
                ),
            ),
            DeclareLaunchArgument(
                "max_wheel_rad_s",
                default_value="",
                description=(
                    "바퀴 각속도 상한을 직접 지정한다 [rad/s]. "
                    "비우면 speed_profile 값을 쓴다. 지정하면 프로파일보다 우선 — "
                    "실기에서 단계적으로 올릴 때 사용"
                ),
            ),
            DeclareLaunchArgument(
                "mock_pty_link",
                default_value="/tmp/stm_serial_bridge_mock_pty",  # noqa: S108
                description="mock 모드에서 브리지가 열 PTY symlink 경로",
            ),
            DeclareLaunchArgument(
                "mock_stop_after_sec",
                default_value="0.0",
                description=(
                    "mock 이 이 시간 뒤 STATUS 송신을 멈춘다(포트는 유지). "
                    "connected=false 타임아웃 확인용. 0 이면 멈추지 않음"
                ),
            ),
            DeclareLaunchArgument(
                "mock_fault_after_sec",
                default_value="0.0",
                description=(
                    "mock 이 이 시간 뒤 FAULT,STALL,LEFT 를 한 번 보낸다. 0 이면 안 보냄"
                ),
            ),
            DeclareLaunchArgument(
                "log_level",
                default_value="info",
                description="브리지 노드 로그 레벨 (debug/info/warn/error)",
            ),
            OpaqueFunction(function=_launch_setup),
        ],
    )
