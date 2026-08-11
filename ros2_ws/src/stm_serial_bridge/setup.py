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
        # launch ?뚯씪怨??뚮씪誘명꽣 YAML ? share/ 濡??ㅼ튂?댁빞
        # `ros2 launch` ? FindPackageShare 媛 李얠쓣 ???덈떎.
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
            # ???ㅻ룄硫뷀듃由? Serial ?ы듃瑜??댁? ?딄퀬 /stm/encoder_total 留?援щ룆?쒕떎.
            "wheel_odometry_node = "
            "stm_serial_bridge.wheel_odometry_node:main",
            # ?섎뱶?⑥뼱 ?놁씠 寃利앺븯湲??꾪븳 ?뚯뒪???꾧뎄.
            # ?ㅼ젣 ?μ튂(/dev/ttyACM*)瑜??댁? ?딅뒗??
            "mock_stm = stm_serial_bridge.mock_stm:main",
            "check_stm_topics = stm_serial_bridge.topic_checker:main",
        ],
    },
)

