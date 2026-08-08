"""rf2o 레이저 스캔매칭 오도메트리.

역할: /scan_raw 만으로 카트의 이동량을 추정한다. 바퀴 슬립·타이어 변형과 무관하므로
      **yaw 를 담당하는 소스**다(휠 오도메트리는 좌측 슬립 때문에 yaw 를 못 맡는다).

🔴 TF 소유권 — `publish_tf` 인자로 정한다.
   odom -> base_link 발행자는 **항상 하나**여야 한다.
   - `publish_tf:=true`  (기본): rf2o 가 직접 발행. EKF 없이 slam_toolbox 만 돌릴 때.
   - `publish_tf:=false`       : EKF 가 발행. `ekf.launch.py` 가 자동으로 넘긴다.
   기본값을 true 로 남긴 이유는, EKF 준비 전에 이 값을 내리면 TF 트리가 끊겨
   slam_toolbox 가 통째로 멈추기 때문이다.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    """Build the rf2o launch description.

    Returns:
        `publish_tf` 인자 하나를 받는 rf2o 노드 실행 서술.
    """
    publish_tf = LaunchConfiguration('publish_tf')

    return LaunchDescription([
        DeclareLaunchArgument(
            'publish_tf',
            default_value='true',
            choices=['true', 'false'],
            description=(
                'rf2o 가 odom -> base_link TF 를 직접 발행할지. '
                'EKF 를 함께 쓸 때만 false — 둘 다 발행하면 TF 트리가 깨진다'
            ),
        ),
        Node(
            package='rf2o_laser_odometry',
            executable='rf2o_laser_odometry_node',
            name='rf2o_laser_odometry',
            output='screen',
            parameters=[{
                # 🔴 반드시 마스킹 전 원본. 마스킹된 /scan을 주면 range 이미지에
                # 구멍이 생겨 정지 상태에서도 -0.4 deg/s 드리프트가 난다
                # (2026-08-07 실측, scripts/scan_mask_node.py 도크스트링 참조).
                'laser_scan_topic': '/scan_raw',
                'odom_topic': '/odom_rf2o',   # 휠 odom(/wheel/odom)과 이름 충돌 방지
                'publish_tf': ParameterValue(publish_tf, value_type=bool),
                'base_frame_id': 'base_link',
                'odom_frame_id': 'odom',
                # 반드시 빈 문자열 (기본값이면 외부 토픽을 기다림)
                'init_pose_from_topic': '',
                'freq': 10.0,
            }],
        ),
    ])
