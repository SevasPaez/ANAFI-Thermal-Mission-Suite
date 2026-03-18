"""Launch Anafi (Thermal) + takeoff-and-ascend demo (conexión directa al dron).

Este launch NO pide argumentos. Edita constantes si tu conexión cambia.
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    # Valores fijos (cambia aquí si hace falta)
    NAMESPACE = "anafi"
    DEVICE_IP = "192.168.42.1"  # Conexión directa al dron
    MODEL = "thermal"  # {'4k', 'thermal', 'usa', 'ai'}

    config = os.path.join(
        get_package_share_directory("anafi_ros_nodes"),
        "config",
        "params.yaml",
    )

    anafi_node = Node(
        package="anafi_ros_nodes",
        namespace=NAMESPACE,
        executable="anafi",
        name="anafi",
        output="screen",
        emulate_tty=True,
        arguments=["--ros-args", "--log-level", "INFO"],
        parameters=[
            config,
            {"drone/model": MODEL},
            {"device/ip": DEVICE_IP},
        ],
    )

    takeoff_node = Node(
        package="anafi_ros_nodes",
        namespace=NAMESPACE,
        executable="takeoff_one_meter",
        name="takeoff_one_meter",
        output="screen",
        emulate_tty=True,
        arguments=["--ros-args", "--log-level", "INFO"],
    )

    return LaunchDescription([
        anafi_node,
        takeoff_node,
    ])
