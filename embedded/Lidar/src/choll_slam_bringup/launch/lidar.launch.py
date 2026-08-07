"""X4Pro 라이다 브링업: 드라이버 + 자기차폐 마스킹 + base_link->laser_frame 정적 TF.

토픽 배선 (2026-08-07 변경 — 근거는 scripts/scan_mask_node.py 도크스트링):
    드라이버 → /scan_raw ──→ rf2o          (전체 스캔 → 정지 드리프트 0)
                    └→ scan_mask_node → /scan → slam_toolbox / Nav2 / AI

드라이버 `ignore_array`로 마스킹하면 rf2o가 정지 상태에서 -0.4 deg/s 드리프트를
내므로 마스킹을 노드로 옮겼다. `/scan`은 계약 토픽이라 이름·QoS를 유지한다.

실행:  ros2 launch choll_slam_bringup lidar.launch.py
확인:  ros2 topic hz /scan /scan_raw   (X4Pro 기본 회전수 기준 6~12 Hz 기대)
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    share_dir = get_package_share_directory('choll_slam_bringup')
    default_params = os.path.join(share_dir, 'config', 'x4pro.yaml')

    params_file = LaunchConfiguration('params_file')

    driver_node = Node(
        package='ydlidar_ros2_driver',
        executable='ydlidar_ros2_driver_node',
        name='ydlidar_ros2_driver_node',
        output='screen',
        emulate_tty=True,
        parameters=[params_file],
        # 드라이버는 원본을 /scan_raw로 낸다 (rf2o 전용). 마스킹된 /scan은
        # scan_mask_node가 발행한다.
        remappings=[('scan', 'scan_raw'), ('point_cloud', 'point_cloud_raw')],
    )

    # 자기차폐 섹터를 NaN으로 만들어 /scan 재발행 (섹터 목록은 노드 기본값)
    scan_mask_node = Node(
        package='choll_slam_bringup',
        executable='scan_mask_node.py',
        name='scan_mask_node',
        output='screen',
        emulate_tty=True,
        parameters=[{'input_topic': '/scan_raw', 'output_topic': '/scan'}],
    )

    # base_link -> laser_frame 정적 TF
    # 장착 확정 (2026-08-06 선반 카트 조립 — 이전 임시 장착에서 z축으로만
    # 이동, 수평 위치 불변): x=0.30(08-05 실측 유지), y=0.0(중심선),
    # yaw=0(기둥 대칭축 실측 +0.51° → 0 확정).
    # z=0.32: 2026-08-07 사용자 줄자 실측 "바닥→라이다 광학창 중심 31.5~32 cm"
    #   의 상단값. 2D SLAM에서 z는 기능 영향 없음(RViz 표시용).
    # y=0.0 재확인: "30 cm 프로파일 좌우 중심 15 cm에 라이다" → 중심선 일치.
    # ⚠️ TODO-확인(x): 같은 실측에서 "모터에서 26~27 cm"가 나왔는데 현재 값은
    #   0.30(08-04 "바퀴축 중심→라이다 30 cm"). 모터 몸통 기준 대 차축 중심
    #   기준 차이로 보이며 3.5 cm 어긋난다. 2D 매핑 품질에는 영향이 없고
    #   Nav2 footprint 기하에만 영향 → base_link 기준점 확정 후 갱신.
    #   --x  : 로봇 중심(base_link=구동 차축 중심)에서 라이다까지 전방(+) 거리 [m]
    #   --y  : 좌측(+) 거리 [m]
    #   --z  : 바닥 기준 높이 [m]
    static_tf_node = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_link_to_laser_frame',
        arguments=[
            '--x', '0.30', '--y', '0.0', '--z', '0.32',
            '--roll', '0.0', '--pitch', '0.0', '--yaw', '0.0',
            '--frame-id', 'base_link',
            '--child-frame-id', 'laser_frame',
        ],
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='ydlidar_ros2_driver 파라미터 YAML 경로',
        ),
        driver_node,
        scan_mask_node,
        static_tf_node,
    ])
