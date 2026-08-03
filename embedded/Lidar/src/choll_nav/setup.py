"""choll_nav 패키지 설치 스크립트."""

import os
from glob import glob

from setuptools import find_packages, setup

package_name = "choll_nav"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "config"), glob("config/*.rviz")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="c101",
    maintainer_email="c101@ssafy.local",
    description=(
        "쫄래쫄래 카트 SLAM/NAV 인터페이스: 위치 발행 + Nav2 goal 전달"
    ),
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "cart_pose_publisher = choll_nav.cart_pose_publisher:main",
            "goal_forwarder = choll_nav.goal_forwarder:main",
        ],
    },
)
