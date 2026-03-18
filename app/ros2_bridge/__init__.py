"""Optional ROS 2 bridge utilities.

This repository contains a Tkinter GUI that reads ANAFI telemetry using Parrot
Olympe. For the thesis workflow, it's very useful to *also* publish that same
telemetry as ROS2 topics, so you can:

- Visualize it with `ros2 topic echo` / RViz2.
- Reuse existing autonomy nodes that expect the `/anafi/...` topic namespace.
- Keep the GUI unchanged as a front-end while ROS2 handles autonomy.

Everything in this package is optional: if `rclpy` is not available (ROS2 not
sourced), the GUI still runs.
"""

from .telemetry_bridge import Ros2TelemetryBridge, ROS2_AVAILABLE

__all__ = ["Ros2TelemetryBridge", "ROS2_AVAILABLE"]
