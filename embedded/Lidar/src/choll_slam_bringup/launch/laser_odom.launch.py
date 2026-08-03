"""rf2o 레이저 스캔매칭 오도메트리 (임시).

역할: STM32 휠 오도메트리가 아직 없는 동안 /scan 만으로
      odom -> base_link TF 를 만들어 slam_toolbox가 돌 수 있게 함.

나중에 휠 오도메트리(엔코더)가 올라오면:
  1) 이 노드를 아예 빼거나,
  2) publish_tf 를 False 로 바꾸고 robot_localization EKF 로
     휠 odom + rf2o 를 융합하는 방식으로 전환.
"""
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        Node(
            package='rf2o_laser_odometry',
            executable='rf2o_laser_odometry_node',
            name='rf2o_laser_odometry',
            output='screen',
            parameters=[{
                'laser_scan_topic': '/scan',
                'odom_topic': '/odom_rf2o',   # 휠 odom(/odom 예정)과 이름 충돌 방지
                'publish_tf': True,           # odom -> base_link TF 발행
                'base_frame_id': 'base_link',
                'odom_frame_id': 'odom',
                # 반드시 빈 문자열 (기본값이면 외부 토픽을 기다림)
                'init_pose_from_topic': '',
                'freq': 10.0,
            }],
        ),
    ])
