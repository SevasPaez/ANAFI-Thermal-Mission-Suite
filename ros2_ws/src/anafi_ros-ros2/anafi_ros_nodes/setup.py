#!/usr/bin/env python3
import os
from glob import glob
from setuptools import setup

package_name = 'anafi_ros_nodes'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),

        # Launch files
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),

        # Config files (params.yaml, etc.)
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),

        # IMPORTANTE: algunos drivers buscan camera_*.yaml en la raíz de share/<pkg>
        # (p.ej. share/anafi_ros_nodes/camera_thermal.yaml). Instalamos también ahí.
        (os.path.join('share', package_name), glob('config/camera_*.yaml')),

        # Scripts opcionales
        (os.path.join('share', package_name, 'scripts'), glob('scripts/*.sh')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='andriy',
    maintainer_email='andriy@todo.todo',
    description='Anafi ROS2 nodes',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'anafi = anafi_ros_nodes.anafi:main',
            'test_anafi = anafi_ros_nodes.test_anafi:main',
            'sphinx = anafi_ros_nodes.sphinx:main',
            'example = anafi_ros_nodes.example:main',
            'takeoff_one_meter = anafi_ros_nodes.takeoff_one_meter:main',
        ],
    },
)
