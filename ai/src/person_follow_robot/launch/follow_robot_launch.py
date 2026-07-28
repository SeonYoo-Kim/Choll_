"""
사용법:
    ros2 launch person_follow_robot follow_robot_launch.py

Launch the full pipeline: camera → detector → tracker → re-id → control → motor
(+ debug visualization). The motor node publishes /wheel_speed_cmd for the STM32
(micro-ROS agent must be running separately for the command to reach the MCU).
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        DeclareLaunchArgument(
            "video_path",
            default_value="",
            description="Optional mp4 input path. Empty value uses USB camera.",
        ),
        DeclareLaunchArgument(
            "save_debug_video",
            default_value="false",
            description="Save /debug/image overlay video to result.mp4 when true.",
        ),
        DeclareLaunchArgument(
            "debug_video_path",
            default_value="result.mp4",
            description="Output path for saved debug video.",
        ),
        Node(
            package="person_follow_robot",
            executable="camera_node",
            name="camera_node",
            output="screen",
            parameters=[{
                "camera_index": 0,
                "video_path": LaunchConfiguration("video_path"),
                "publish_rate_hz": 30.0,
            }],
        ),
        Node(
            package="person_follow_robot",
            executable="detector_node",
            name="detector_node",
            output="screen",
            parameters=[{
                "model_path": "models/yolov10s.engine",
                "confidence_threshold": 0.50,
            }],
        ),
        Node(
            package="person_follow_robot",
            executable="tracker_node",
            name="tracker_node",
            output="screen",
            parameters=[{
                "track_activation_threshold": 0.25,
                "lost_track_buffer": 30,
                "minimum_matching_threshold": 0.80,
                "frame_rate": 30,
            }],
        ),
        Node(
            package="person_follow_robot",
            executable="reid_node",
            name="reid_node",
            output="screen",
            parameters=[{
                "registration_duration_sec": 2.0,
                "memory_bank_max_features": 20,
                "similarity_threshold": 0.90,
                "osnet_device": "auto",
            }],
        ),
        Node(
            package="person_follow_robot",
            executable="control_node",
            name="control_node",
            output="screen",
            parameters=[{
                "target_distance_m": 1.0,
                "camera_fov_deg": 58.0,
                "image_width": 640,           # camera_node frame_width와 일치
                "lidar_yaw_offset_deg": 0.0,  # 조립 후 캘리브레이션으로 확정
                "lidar_mirrored": True,       # 실측: 좌우 반전 증상 확인 (2026-07-28)
                "target_timeout_sec": 1.0,
                "max_linear_vel": 0.5,
                "max_angular_vel": 1.0,
            }],
        ),
        Node(
            package="person_follow_robot",
            executable="motor_node",
            name="motor_node",
            output="screen",
            parameters=[{
                "wheel_radius_m": 0.065,
                "wheel_separation_m": 0.30,   # TODO: 조립 후 실측값으로 교체
                "max_rpm": 200,               # TODO: 모터 스펙 확정 시 조정
                "publish_rate_hz": 10.0,
            }],
        ),
        Node(
            package="person_follow_robot",
            executable="debug_visualization_node",
            name="debug_visualization_node",
            output="screen",
            parameters=[{
                "save_debug_video": LaunchConfiguration("save_debug_video"),
                "debug_video_path": LaunchConfiguration("debug_video_path"),
                "debug_video_fps": 30.0,
                "recovery_overlay_duration_sec": 2.0,
                "distance_display_timeout_sec": 1.0,  # 거리 수신 끊기면 라벨 숨김
            }],
        ),
    ])
