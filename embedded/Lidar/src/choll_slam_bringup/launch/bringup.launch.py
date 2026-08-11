"""전체 매핑 스택 원커맨드 실행.

순서: 라이다(0초) -> rf2o 오도메트리(3초) -> [EKF(5초)] -> slam_toolbox(6초)
/scan 이 먼저 살아있어야 rf2o가 붙고, TF가 준비된 뒤 SLAM이 붙도록 시차를 둠.

실행:
    ros2 launch choll_slam_bringup bringup.launch.py            # rf2o 가 TF 발행 (기존)
    ros2 launch choll_slam_bringup bringup.launch.py ekf:=true  # EKF 가 TF 발행 (융합)

🔴 `ekf:=true` 는 rf2o 의 `publish_tf` 를 자동으로 false 로 내린다 —
   odom -> base_link 발행자를 항상 하나로 유지하기 위해서다.
   융합 설계와 근거는 `config/ekf.yaml` 상단 주석이 정본.

⚠️ `ekf:=true` 를 쓰려면 다음 두 가지가 필요하다.
   1) `sudo apt install ros-humble-robot-localization`
   2) 별도 워크스페이스의 `/wheel/odom` 발행자(`stm_serial_bridge` 의
      `wheel_odometry_node`). 없으면 EKF 가 rf2o 만 쓰게 되어 융합 의미가 없다.
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression


def generate_launch_description() -> LaunchDescription:
    """Build the full mapping-stack launch description.

    Returns:
        `ekf` 인자 하나를 받는 라이다 + rf2o + (EKF) + slam_toolbox 실행 서술.
    """
    launch_dir = os.path.join(
        get_package_share_directory('choll_slam_bringup'), 'launch')

    use_ekf = LaunchConfiguration('ekf')
    # EKF 를 켜면 TF 발행권이 EKF 로 넘어간다 — rf2o 는 내려야 한다.
    rf2o_publish_tf = PythonExpression(
        ["'false' if '", use_ekf, "' == 'true' else 'true'"])

    lidar = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_dir, 'lidar.launch.py')))

    laser_odom = TimerAction(
        period=3.0,
        actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(launch_dir, 'laser_odom.launch.py')),
            launch_arguments={'publish_tf': rf2o_publish_tf}.items())])

    # rf2o 가 첫 odom 을 낸 뒤에 붙어야 EKF 가 빈 입력으로 시작하지 않는다.
    ekf = TimerAction(
        period=5.0,
        actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(launch_dir, 'ekf.launch.py')),
            condition=IfCondition(use_ekf))])

    slam = TimerAction(
        period=6.0,
        actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(launch_dir, 'slam.launch.py')))])

    return LaunchDescription([
        DeclareLaunchArgument(
            'ekf',
            default_value='false',
            choices=['true', 'false'],
            description=(
                'robot_localization EKF 로 rf2o + 휠 오도메트리를 융합할지. '
                'true 면 rf2o publish_tf 가 자동으로 false 가 된다'
            ),
        ),
        lidar, laser_odom, ekf, slam,
    ])
