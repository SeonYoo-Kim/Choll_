from glob import glob

from setuptools import find_packages, setup

package_name = "person_follow_robot"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/launch", glob("launch/*.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="theta",
    maintainer_email="theta@example.com",
    description="Library robot: person detection(YOLO) + LiDAR fusion + PID following",
    license="MIT",
    entry_points={
        "console_scripts": [
            "camera_node = person_follow_robot.camera_node:main",
            "detector_node = person_follow_robot.detector_node:main",
            "tracker_node = person_follow_robot.tracker_node:main",
            "reid_node = person_follow_robot.reid_node:main",
            "debug_visualization_node = "
            "person_follow_robot.debug_visualization_node:main",
            "control_node = person_follow_robot.control_node:main",
            "motor_node = person_follow_robot.motor_node:main",
            "target_position_node = person_follow_robot.target_position_node:main",
            "fe_bridge_node = person_follow_robot.fe_bridge_node:main",
        ],
    },
)
