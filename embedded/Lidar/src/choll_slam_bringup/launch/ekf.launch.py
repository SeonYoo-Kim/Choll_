"""robot_localization EKF — rf2o + 휠 오도메트리 융합, odom -> base_link TF 발행.

이 런치는 **세 노드**를 띄운다.
  1) `odom_covariance_node.py` : rf2o 가 비워 두는 공분산을 찍어
                                 `/odom_rf2o_cov` 로 중계
  2) `zupt_node.py`            : 엔코더가 멈춰 있으면 `/odom_zupt` 로
                                 "확실히 정지"를 알린다 (정지 중 yaw 드리프트 방지)
  3) `ekf_filter_node`         : 위 둘과 `/wheel/odom` 을 융합

설계·근거는 `config/ekf.yaml` 상단 주석을 정본으로 본다.

🔴 전제 — odom -> base_link 발행자는 하나여야 한다.
   이 런치를 쓸 때는 rf2o 를 반드시 `publish_tf:=false` 로 띄운다.
   `bringup.launch.py ekf:=true` 는 그걸 자동으로 해 준다. rf2o 를 따로 띄웠다면
   직접 확인할 것 — 둘 다 발행하면 TF 트리가 깨지고 slam_toolbox 가 튄다.

🔴 전제 — `/wheel/odom` 발행자가 살아 있어야 한다(별도 워크스페이스):
   ros2 run stm_serial_bridge wheel_odometry_node --ros-args \
     --params-file <ros2_ws>/install/stm_serial_bridge/share/\
stm_serial_bridge/config/wheel_odometry.yaml
   없어도 EKF 는 rf2o 만으로 동작하지만, 그러면 융합의 의미가 없다.

실행:
    ros2 launch choll_slam_bringup ekf.launch.py
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """Build the covariance stamper + EKF launch description.

    Returns:
        공분산 스탬퍼와 `ekf_filter_node` 를 함께 띄우는 실행 서술.
    """
    ekf_params = os.path.join(
        get_package_share_directory('choll_slam_bringup'), 'config', 'ekf.yaml')

    # rf2o 는 공분산을 전혀 채우지 않는다(upstream 확인). EKF 는 0 을 "오차 없음"으로
    # 읽으므로 그대로 넣으면 rf2o 만 절대 신뢰하게 되어 융합이 성립하지 않는다.
    covariance_stamper = Node(
        package='choll_slam_bringup',
        executable='odom_covariance_node.py',
        name='odom_covariance',
        output='screen',
        emulate_tty=True,
        parameters=[{
            'input_topic': '/odom_rf2o',
            'output_topic': '/odom_rf2o_cov',
        }],
    )

    # 엔코더가 멈춰 있을 때만 "확실히 정지"를 알린다 (정지 중 yaw 드리프트 방지).
    zupt = Node(
        package='choll_slam_bringup',
        executable='zupt_node.py',
        name='zupt',
        output='screen',
        emulate_tty=True,
        parameters=[{'output_topic': '/odom_zupt'}],
    )

    ekf = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf_filter_node',
        output='screen',
        emulate_tty=True,
        parameters=[ekf_params],
    )

    return LaunchDescription([covariance_stamper, zupt, ekf])
