from setuptools import find_packages, setup

package_name = "stm_serial_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="relu",
    maintainer_email="em-dev@anonymized.invalid",
    description="Bridge ROS2 /cmd_vel to the STM32 motor controller over USB serial.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "stm_serial_bridge_node = "
            "stm_serial_bridge.stm_serial_bridge_node:main",
        ],
    },
)
