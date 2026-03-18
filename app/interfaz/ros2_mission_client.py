from __future__ import annotations

import json
import threading
import time
from typing import Any, Optional

ROS2_AVAILABLE = False

try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
    from std_srvs.srv import Trigger

    from anafi_suite_core.runtime_paths import get_current_mission_path, write_current_mission

    ROS2_AVAILABLE = True
except Exception:
    ROS2_AVAILABLE = False


class Ros2MissionClient:
    """Small ROS2 client used by the GUI to hand missions to the mission manager."""

    def __init__(self, namespace: str = "/anafi") -> None:
        self.namespace = "/" + namespace.strip("/")
        self._node: Optional[Node] = None
        self._status_lock = threading.Lock()
        self._last_status: dict[str, Any] = {
            "state": "unknown",
            "summary": "Sin datos",
            "mission_name": "",
            "current_waypoint": 0,
            "total_waypoints": 0,
            "running": False,
            "last_error": "",
            "mission_file": "",
        }

    def start(self) -> None:
        if not ROS2_AVAILABLE:
            raise RuntimeError("ROS2 no está disponible en esta terminal")
        if self._node is not None:
            return
        if not rclpy.ok():
            rclpy.init(args=None)
        self._node = rclpy.create_node("anafi_gui_mission_client")
        self._sub_status = self._node.create_subscription(
            String,
            f"{self.namespace}/mission/status",
            self._on_status,
            10,
        )
        self._cli_ping = self._node.create_client(Trigger, f"{self.namespace}/mission/ping")
        self._cli_start = self._node.create_client(Trigger, f"{self.namespace}/mission/start")
        self._cli_stop = self._node.create_client(Trigger, f"{self.namespace}/mission/stop")

    def destroy(self) -> None:
        if self._node is None:
            return
        try:
            self._node.destroy_node()
        except Exception:
            pass
        self._node = None

    def _on_status(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
            if isinstance(payload, dict):
                with self._status_lock:
                    self._last_status = payload
        except Exception:
            with self._status_lock:
                self._last_status = {
                    "state": "unknown",
                    "summary": msg.data,
                    "mission_name": "",
                    "current_waypoint": 0,
                    "total_waypoints": 0,
                    "running": False,
                    "last_error": "",
                    "mission_file": "",
                }

    def spin_once(self, timeout_sec: float = 0.0) -> None:
        if self._node is None:
            return
        try:
            rclpy.spin_once(self._node, timeout_sec=timeout_sec)
        except Exception:
            pass

    def get_last_status(self) -> dict[str, Any]:
        with self._status_lock:
            return dict(self._last_status)

    def manager_available(self, timeout_sec: float = 0.6) -> bool:
        self.start()
        if self._node is None:
            return False
        return bool(self._cli_ping.wait_for_service(timeout_sec=timeout_sec))

    def _call_trigger(self, client, timeout_sec: float = 3.0) -> tuple[bool, str]:
        if self._node is None:
            raise RuntimeError("El cliente ROS2 no está iniciado")
        if not client.wait_for_service(timeout_sec=timeout_sec):
            return False, "El mission manager no está disponible"
        future = client.call_async(Trigger.Request())
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            self.spin_once(timeout_sec=0.05)
            if future.done():
                try:
                    response = future.result()
                    return bool(response.success), str(response.message)
                except Exception as exc:
                    return False, str(exc)
        return False, "Timeout esperando respuesta del mission manager"

    def save_current_mission(self, mission: dict[str, Any]) -> str:
        self.start()
        return write_current_mission(mission)

    def start_mission(self, mission: dict[str, Any]) -> tuple[bool, str, str]:
        mission_file = self.save_current_mission(mission)
        ok, msg = self._call_trigger(self._cli_start)
        return ok, msg, mission_file

    def stop_mission(self) -> tuple[bool, str]:
        self.start()
        return self._call_trigger(self._cli_stop)

    def ping(self) -> tuple[bool, str]:
        self.start()
        return self._call_trigger(self._cli_ping)

    @property
    def current_mission_path(self) -> str:
        return get_current_mission_path()
