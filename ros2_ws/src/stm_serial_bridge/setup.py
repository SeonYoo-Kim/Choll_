from glob import glob

from setuptools import find_packages, setup

package_name = "stm_serial_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        # launch 파일과 파라미터 YAML 은 share/ 로 설치해야
        # `ros2 launch` 와 FindPackageShare 가 찾을 수 있다.
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
        (f"share/{package_name}/config", glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="choll-em-dev",
    maintainer_email="em-dev@anonymized.invalid",
    description="Bridge ROS2 /cmd_vel to the STM32 motor controller over USB serial.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "stm_serial_bridge_node = "
            "stm_serial_bridge.stm_serial_bridge_node:main",
            # 휠 오도메트리. Serial 포트를 열지 않고 /stm/encoder_total 만 구독한다.
            "wheel_odometry_node = "
            "stm_serial_bridge.wheel_odometry_node:main",
            # 하드웨어 없이 검증하기 위한 테스트 도구.
            # 실제 장치(/dev/ttyACM*)를 열지 않는다.
            "mock_stm = stm_serial_bridge.mock_stm:main",
            "check_stm_topics = stm_serial_bridge.topic_checker:main",
        ],
    },
)
