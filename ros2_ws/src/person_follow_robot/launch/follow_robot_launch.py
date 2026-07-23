"""
사용법:
    ros2 launch person_follow_robot follow_robot_launch.py

Launch the camera, TensorRT detector, ByteTrack tracker, and Re-ID nodes.
Controller and motor nodes will be connected in their respective phases.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
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
            executable="debug_visualization_node",
            name="debug_visualization_node",
            output="screen",
            parameters=[{
                "save_debug_video": LaunchConfiguration("save_debug_video"),
                "debug_video_path": LaunchConfiguration("debug_video_path"),
                "debug_video_fps": 30.0,
                "recovery_overlay_duration_sec": 2.0,
            }],
        ),
    ])
