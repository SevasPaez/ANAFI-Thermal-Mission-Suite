from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger

from anafi_suite_core import MissionExecutor
from anafi_suite_core.runtime_paths import get_current_mission_path, get_suite_root


class MissionManagerNode(Node):
    def __init__(self) -> None:
        super().__init__("mission_manager")
        self.declare_parameter("mission_file", get_current_mission_path())
        self.declare_parameter("suite_root", get_suite_root())

        self._lock = threading.Lock()
        self._status: dict[str, Any] = {
            "state": "idle",
            "summary": "Listo",
            "mission_name": "",
            "current_waypoint": 0,
            "total_waypoints": 0,
            "running": False,
            "last_error": "",
            "mission_file": self.mission_file,
        }
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._executor = MissionExecutor()

        self.pub_status = self.create_publisher(String, "mission/status", 10)
        self.pub_progress = self.create_publisher(String, "mission/progress", 10)
        self.pub_event = self.create_publisher(String, "mission/event", 10)

        self.srv_ping = self.create_service(Trigger, "mission/ping", self._srv_ping)
        self.srv_start = self.create_service(Trigger, "mission/start", self._srv_start)
        self.srv_stop = self.create_service(Trigger, "mission/stop", self._srv_stop)

        self.timer = self.create_timer(0.5, self._publish_status_tick)
        self._set_status(state="idle", summary="Mission manager listo")
        self.get_logger().info(f"Mission manager listo. mission_file={self.mission_file}")

    @property
    def mission_file(self) -> str:
        return str(self.get_parameter("mission_file").value)

    def _srv_ping(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        del request
        response.success = True
        response.message = json.dumps(self._status, ensure_ascii=False)
        return response

    def _srv_start(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        del request
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                response.success = False
                response.message = "Ya hay una misión en ejecución"
                return response

            mission_path = Path(self.mission_file)
            if not mission_path.exists():
                response.success = False
                response.message = f"No existe el archivo de misión: {mission_path}"
                self._set_status(state="error", summary=response.message, last_error=response.message)
                return response

            try:
                mission = json.loads(mission_path.read_text(encoding="utf-8"))
            except Exception as exc:
                response.success = False
                response.message = f"No se pudo leer la misión: {exc}"
                self._set_status(state="error", summary=response.message, last_error=response.message)
                return response

            self._cancel.clear()
            self._thread = threading.Thread(target=self._run_mission_thread, args=(mission,), daemon=True)
            self._thread.start()
            response.success = True
            response.message = f"Misión enviada. Archivo: {mission_path}"
            self._set_status(
                state="starting",
                summary="Misión enviada al ejecutor",
                mission_name=str(mission.get("name", "mission")),
                total_waypoints=len(mission.get("waypoints", []) or []),
                last_error="",
            )
            return response

    def _srv_stop(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        del request
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                response.success = True
                response.message = "No hay misión ejecutándose"
                self._set_status(state="idle", summary=response.message, running=False)
                return response
            self._cancel.set()
            response.success = True
            response.message = "Solicitud de cancelación enviada"
            self._set_status(state="stopping", summary=response.message)
            return response

    def _run_mission_thread(self, mission: dict[str, Any]) -> None:
        mission_name = str(mission.get("name", "mission"))
        total_waypoints = len(mission.get("waypoints", []) or [])
        self._set_status(
            state="running",
            summary="Ejecutando misión",
            mission_name=mission_name,
            current_waypoint=0,
            total_waypoints=total_waypoints,
            running=True,
            last_error="",
        )
        result = self._executor.run(
            mission,
            cancel_event=self._cancel,
            on_status=self._on_executor_status,
            on_progress=self._on_executor_progress,
            on_event=self._on_executor_event,
        )
        if result.cancelled:
            self._set_status(
                state="cancelled",
                summary="Misión cancelada",
                running=False,
                last_error="",
            )
            self.get_logger().warning("Misión cancelada")
        elif result.ok:
            self._set_status(
                state="completed",
                summary="Misión completada",
                running=False,
                last_error="",
            )
            self.get_logger().info("Misión completada")
        else:
            self._set_status(
                state="error",
                summary=result.error or "Error en la misión",
                running=False,
                last_error=result.error or "Error en la misión",
            )
            self.get_logger().error(f"Error de misión: {result.error}")

    def _on_executor_status(self, msg: str) -> None:
        self._set_status(summary=msg, running=True)

    def _on_executor_progress(self, payload: dict[str, Any]) -> None:
        state = str(payload.get("state", self._status.get("state", "running")))
        current_waypoint = int(payload.get("current_waypoint", self._status.get("current_waypoint", 0) or 0))
        total_waypoints = int(payload.get("total_waypoints", self._status.get("total_waypoints", 0) or 0))
        mission_name = str(payload.get("mission_name", self._status.get("mission_name", "") or ""))
        detail = str(payload.get("detail", self._status.get("summary", "") or ""))
        self._set_status(
            state=state,
            summary=detail,
            current_waypoint=current_waypoint,
            total_waypoints=total_waypoints,
            mission_name=mission_name,
            running=state not in {"completed", "cancelled", "error", "idle"},
        )
        self._publish_json(self.pub_progress, payload)

    def _on_executor_event(self, payload: dict[str, Any]) -> None:
        self._publish_json(self.pub_event, payload)

    def _set_status(self, **updates: Any) -> None:
        with self._lock:
            self._status.update(updates)
            self._status["mission_file"] = self.mission_file
            if "running" not in updates:
                self._status["running"] = self._status.get("state") not in {"completed", "cancelled", "error", "idle"}
            payload = dict(self._status)
        self._publish_json(self.pub_status, payload)

    def _publish_json(self, publisher, payload: dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        publisher.publish(msg)

    def _publish_status_tick(self) -> None:
        with self._lock:
            payload = dict(self._status)
        self._publish_json(self.pub_status, payload)


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = MissionManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
