"""choll_mqtt_bridge 패키지 설치 스크립트."""

import os
from glob import glob

from setuptools import find_packages, setup

package_name = "choll_mqtt_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="c101",
    maintainer_email="c101@ssafy.local",
    description=(
        "쫄래쫄래 MQTT↔ROS2 브릿지: BE 명령 수신 + 위치 텔레메트리 발행"
    ),
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "mqtt_bridge = choll_mqtt_bridge.mqtt_bridge:main",
        ],
    },
)
