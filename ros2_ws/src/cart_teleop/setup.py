from setuptools import find_packages, setup

package_name = "cart_teleop"

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
    maintainer="choll-em-dev",
    maintainer_email="em-dev@anonymized.invalid",
    description=(
        "SSH terminal WASD keyboard teleop publishing /cmd_vel "
        "for manual SLAM mapping."
    ),
    license="MIT",
    entry_points={
        "console_scripts": [
            # launch ?뚯씪? ?먯? ?딅뒗????teleop ? stdin(tty)???먯쑀?댁빞 ?섎?濡?
            # `ros2 run` ?쇰줈 ?ㅽ뻾?쒕떎.
            "keyboard_teleop = cart_teleop.teleop_node:main",
        ],
    },
)

