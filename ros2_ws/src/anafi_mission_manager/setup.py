import os
from glob import glob
from setuptools import setup

package_name = "anafi_mission_manager"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="OpenAI",
    maintainer_email="openai@example.com",
    description="ROS2 mission manager for the unified ANAFI suite.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "mission_manager = anafi_mission_manager.mission_manager_node:main",
        ],
    },
)
