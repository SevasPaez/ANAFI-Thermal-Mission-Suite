from setuptools import setup

package_name = "anafi_suite_core"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="OpenAI",
    maintainer_email="openai@example.com",
    description="Core mission runtime shared by the GUI and ROS2 mission manager.",
    license="MIT",
)
