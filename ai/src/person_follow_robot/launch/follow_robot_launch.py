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
from launch_ros.parameter_descriptions import ParameterValue


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
        DeclareLaunchArgument(
            "threshold",
            default_value="0.85",
            description="Re-ID cosine similarity threshold "
            "(reid_node similarity_threshold). 예: threshold:=0.80",
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
                # 0.90은 재등장 동일인도 기각 (실측). threshold:=값 으로 실험 가능
                "similarity_threshold": ParameterValue(
                    LaunchConfiguration("threshold"), value_type=float
                ),
                "osnet_device": "auto",
                "auto_select_enabled": True,      # 최대 bbox(=최근접) 자동 선택
                "auto_select_stable_frames": 15,  # 30fps 기준 0.5초 연속 최대
                "auto_select_min_area_px": 5000.0,
                "feature_sample_interval_sec": 0.3,  # 뱅크 다양성 (매 프레임 추가 금지)
                "recovery_margin": 0.05,          # 재탐색 1위-2위 최소 격차
                "crop_side_margin_px": 4.0,       # 좌우 잘린 크롭 배제 여유
                "crop_max_area_fraction": 0.5,    # 초근접(몸통 조각) 크롭 배제
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
                "bbox_span_scale": 0.8,       # bbox 폭 중 LiDAR 조회에 쓸 비율
                "distance_grace_period_sec": 0.5,  # 순간 드롭아웃 유예(직전 거리 유지)
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
