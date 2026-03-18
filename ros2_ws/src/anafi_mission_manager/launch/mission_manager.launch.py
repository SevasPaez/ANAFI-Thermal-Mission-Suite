from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package="anafi_mission_manager",
            executable="mission_manager",
            name="mission_manager",
            namespace="anafi",
        )
    ])
