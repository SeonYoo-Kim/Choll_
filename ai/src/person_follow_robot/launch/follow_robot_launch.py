"""
사용법:
    ros2 launch person_follow_robot follow_robot_launch.py

Launch the full pipeline: camera → detector → tracker → re-id → control → motor
(+ debug visualization). The motor node publishes /wheel_speed_cmd for the STM32
(micro-ROS agent must be running separately for the command to reach the MCU).
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
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
            default_value="0.70",
            description="Re-ID cosine similarity threshold "
            "(reid_node similarity_threshold). 예: threshold:=0.80",
        ),
        DeclareLaunchArgument(
            "fe_bridge",
            default_value="false",
            description="FE 타겟 선택 브릿지(영상·트랙 하행, 선택 상행) 실행. "
            "auto_select:=false와 함께 사용.",
        ),
        DeclareLaunchArgument(
            "auto_select",
            default_value="true",
            description="최근접 인물 자동 선택. false면 /select_target "
            "수동/FE 선택 대기.",
        ),
        DeclareLaunchArgument(
            "be_video_ws_url",
            default_value="ws://localhost:8080/ws/carts/1/video/publish",
            description="BE 영상 릴레이 발행 endpoint (fe_bridge용).",
        ),
        DeclareLaunchArgument(
            "mqtt_host",
            default_value="localhost",
            description="MQTT 브로커 호스트 (fe_bridge용).",
        ),
        DeclareLaunchArgument(
            "mqtt_username",
            default_value="",
            description="MQTT 브로커 계정 (EC2 브로커는 필수, 로컬은 빈 값).",
        ),
        DeclareLaunchArgument(
            "mqtt_password",
            default_value="",
            description="MQTT 브로커 비밀번호.",
        ),
        DeclareLaunchArgument(
            "legacy_control",
            default_value="true",
            description="AI 직접 구동(레거시 PID). false면 EM Nav2가 바퀴를 "
            "굴리는 구성: motor_node 미실행 + control_node의 /cmd_vel을 "
            "/cmd_vel_legacy로 격리 (거리 측정 /target_distance는 유지). "
            "예: legacy_control:=false",
        ),
        DeclareLaunchArgument(
            "map_target",
            default_value="true",
            description="target_position_node(/target_position 지도좌표 발행) 실행. "
            "EM Nav2 추종에는 필수. 단순 추종(legacy_control:=true)에서는 소비자가 "
            "없으므로 false로 꺼서 메모리를 아낄 수 있다. 예: map_target:=false",
        ),
        DeclareLaunchArgument(
            "debug_viz",
            default_value="true",
            description="debug_visualization_node(오버레이 영상) 실행. false면 "
            "약 115MB 절약. FE 영상은 fe_bridge_node가 따로 보내므로 영향 없다. "
            "예: debug_viz:=false",
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
                # 실측: 동일인 재등장 <0.80, 타인(원거리 검은옷) 0.92+ —
                # 유사도 단독으론 분리 불가. 타당성 게이트+연속 확인과 조합해
                # 0.70 사용. threshold:=값 으로 실험 가능
                "similarity_threshold": ParameterValue(
                    LaunchConfiguration("threshold"), value_type=float
                ),
                "osnet_device": "auto",
                # 최대 bbox(=최근접) 자동 선택. FE 선택 모드는 auto_select:=false
                "auto_select_enabled": ParameterValue(
                    LaunchConfiguration("auto_select"), value_type=bool
                ),
                "auto_select_stable_frames": 15,  # 30fps 기준 0.5초 연속 최대
                "auto_select_min_area_px": 5000.0,
                "feature_sample_interval_sec": 0.3,  # 뱅크 다양성 (매 프레임 추가 금지)
                "recovery_margin": 0.05,          # 재탐색 1위-2위 최소 격차
                "crop_side_margin_px": 4.0,       # 좌우 잘린 크롭 배제 여유
                "crop_max_area_fraction": 0.5,    # 초근접(몸통 조각) 크롭 배제
                "recovery_confirm_frames": 10,    # 재잠금 연속 확인 (30fps 0.33초)
                "recovery_max_speed_px_per_sec": 300.0,  # 타당성: 중심 이동 속도
                "recovery_center_slack_px": 60.0,
                "recovery_size_change_rate": 0.7,  # 타당성: 초당 크기 비율 변화
                "post_recovery_update_delay_sec": 2.0,  # 재잠금 후 뱅크 갱신 유예
            }],
        ),
        Node(
            package="person_follow_robot",
            executable="control_node",
            name="control_node",
            output="screen",
            # legacy_control:=false면 /cmd_vel을 격리 토픽으로 보내 EM Nav2와의
            # 이중 발행 충돌을 막는다 (노드는 계속 떠서 /target_distance 발행)
            remappings=[(
                "/cmd_vel",
                PythonExpression([
                    "'/cmd_vel' if '",
                    LaunchConfiguration("legacy_control"),
                    "'.lower() in ('true', '1') else '/cmd_vel_legacy'",
                ]),
            )],
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
                # 🔴 후진 금지. 사서가 책을 꺼내려 다가와도 물러서지 않는다.
                #    거리가 target_distance_m 보다 가까우면 그냥 정지하고,
                #    회전은 유지해 사서를 계속 바라본다.
                "allow_reverse": False,
                # 🔴 전방 장애물 정지. Nav2 없이 단순 추종만 돌릴 때의 유일한
                #    충돌 방어다. 임계값은 target_distance_m(1.0)보다 작아야
                #    한다 — 같거나 크면 추종 대상 본인이 걸려 전진을 못 한다.
                "obstacle_stop_enabled": True,
                "min_obstacle_distance_m": 0.8,
                "front_half_span_deg": 30.0,
            }],
        ),
        Node(
            package="person_follow_robot",
            executable="motor_node",
            name="motor_node",
            output="screen",
            # EM Nav2 구성(legacy_control:=false)에서는 /wheel_speed_cmd 발행 자체를
            # 중단해야 하므로 노드를 띄우지 않는다 (타임아웃 정지 발행도 충돌 요인)
            condition=IfCondition(LaunchConfiguration("legacy_control")),
            parameters=[{
                "wheel_radius_m": 0.065,
                "wheel_separation_m": 0.30,   # TODO: 조립 후 실측값으로 교체
                "max_rpm": 200,               # TODO: 모터 스펙 확정 시 조정
                "publish_rate_hz": 10.0,
            }],
        ),
        Node(
            package="person_follow_robot",
            executable="fe_bridge_node",
            name="fe_bridge_node",
            output="screen",
            condition=IfCondition(LaunchConfiguration("fe_bridge")),
            parameters=[{
                "video_ws_url": LaunchConfiguration("be_video_ws_url"),
                "mqtt_host": LaunchConfiguration("mqtt_host"),
                "mqtt_port": 1883,
                "mqtt_username": LaunchConfiguration("mqtt_username"),
                "mqtt_password": LaunchConfiguration("mqtt_password"),
                "tracks_topic": "status/target",
                "command_topic": "cmd/move/cart",
                "video_fps": 10.0,
                "jpeg_quality": 70,
                "tracks_rate_hz": 5.0,
            }],
        ),
        Node(
            package="person_follow_robot",
            executable="target_position_node",
            name="target_position_node",
            output="screen",
            # 단순 추종(legacy_control:=true)에서는 EM goal_forwarder 를 쓰지 않아
            # /target_position 소비자가 없다. Orin Nano 통합 메모리를 아끼려고 끈다
            # (2026-08-13: reid_node 가 CUDA OOM 으로 죽어 추종이 안 됐다).
            condition=IfCondition(LaunchConfiguration("map_target")),
            parameters=[{
                "cart_pose_topic": "/robot_pose",  # EM SLAM 포즈 계약 확정 시 갱신
                "target_position_topic": "/target_position",
                "map_frame_id": "map",
                "camera_fov_deg": 58.0,
                "image_width": 640,
                "lidar_yaw_offset_deg": 0.0,
                "lidar_mirrored": True,
                "bbox_span_scale": 0.8,
                "pose_timeout_sec": 1.0,
            }],
        ),
        Node(
            package="person_follow_robot",
            executable="debug_visualization_node",
            name="debug_visualization_node",
            output="screen",
            # 오버레이 영상은 디버그용. FE 영상은 fe_bridge_node 가 따로 보내므로
            # 꺼도 FE 화면에는 영향이 없다.
            condition=IfCondition(LaunchConfiguration("debug_viz")),
            parameters=[{
                "save_debug_video": LaunchConfiguration("save_debug_video"),
                "debug_video_path": LaunchConfiguration("debug_video_path"),
                "debug_video_fps": 30.0,
                "recovery_overlay_duration_sec": 2.0,
                "distance_display_timeout_sec": 1.0,  # 거리 수신 끊기면 라벨 숨김
            }],
        ),
    ])
