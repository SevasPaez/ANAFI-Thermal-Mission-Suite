"""interfaz/ros2_controller.py

Controlador global para dar "protagonismo" a ROS2 dentro de la GUI.

Objetivo:
- Unificar el estado de "Sensores" (telemetría Olympe) y el "ROS2 Bridge".
- Permitir start/stop desde la sidebar y mantener estado al cambiar de páginas.
- (Opcional) Lanzar procesos ROS2 (anafi_autonomy / anafi_ros_nodes) desde la UI
  y capturar logs.

Nota: este controlador es *agnóstico* a Tkinter. La UI debe hacer polling
periódico (after) para refrescar labels/botones.
"""

from __future__ import annotations

import os
import queue
import signal
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Optional

from config import DRONE_IP
from sensores.streams import SensorStream

from ros2_bridge import ROS2_AVAILABLE
from ros2_bridge.telemetry_bridge import Ros2TelemetryBridge


@dataclass
class ControllerStatus:
    sensors_connected: bool = False
    ros2_bridge_running: bool = False
    ros2_published_msgs: int = 0
    ros2_last_state: str = ""
    autonomy_running: bool = False
    autonomy_cmd: str = ""
    last_error: str = ""


class Ros2Controller:
    def __init__(
        self,
        ip: str = DRONE_IP,
        namespace: str = "/anafi",
        publish_hz: float = 10.0,
    ) -> None:
        self.ip = ip
        self.namespace = namespace
        self.publish_hz = float(publish_hz)

        self.sensor_stream: Optional[SensorStream] = None
        self.bridge = Ros2TelemetryBridge(namespace=self.namespace)
        self.bridge.on_action = self._handle_action_code

        self._bridge_running = False
        self._pub_stop = threading.Event()
        self._pub_thread: Optional[threading.Thread] = None

        # Autonomy process (ros2 launch ...)
        self._auto_proc: Optional[subprocess.Popen] = None
        self._auto_reader_thread: Optional[threading.Thread] = None
        self._log_q: "queue.Queue[str]" = queue.Queue()
        self._auto_cmd: str = ""

        self._lock = threading.Lock()
        self._last_error = ""

    # ------------------------ Sensors ------------------------

    def ensure_sensor_stream(self) -> SensorStream:
        if self.sensor_stream is None:
            self.sensor_stream = SensorStream(self.ip)
        return self.sensor_stream

    def sensors_connected(self) -> bool:
        try:
            return bool(self.sensor_stream is not None and self.sensor_stream.client.connected)
        except Exception:
            return False

    def start_sensors(self) -> bool:
        ss = self.ensure_sensor_stream()
        try:
            ss.start()
            return True
        except Exception as e:
            self._set_error(f"Sensores: {e}")
            return False

    def stop_sensors(self) -> None:
        if self.sensor_stream is None:
            return
        try:
            self.sensor_stream.stop()
        except Exception:
            pass
        try:
            self.sensor_stream = None
        except Exception:
            pass

    def toggle_sensors(self) -> bool:
        if self.sensors_connected():
            self.stop_sensors()
            return False
        return self.start_sensors()

    # ------------------------ ROS2 Bridge ------------------------

    def ros2_bridge_running(self) -> bool:
        return bool(self._bridge_running and self.bridge.is_running)

    def start_ros2_bridge(self) -> bool:
        if not ROS2_AVAILABLE:
            self._set_error(
                "ROS2 (rclpy) no está disponible. Ejecuta la app desde una terminal con ROS2 sourceteado."
            )
            return False

        # Ensure sensors
        if not self.sensors_connected():
            if not self.start_sensors():
                return False

        try:
            self.bridge.start()
        except Exception as e:
            self._set_error(f"ROS2 bridge: {e}")
            return False

        self._bridge_running = True
        self._start_publisher_thread()
        return True

    def stop_ros2_bridge(self) -> None:
        self._bridge_running = False
        self._stop_publisher_thread()
        try:
            self.bridge.stop()
        except Exception:
            pass

    def toggle_ros2_bridge(self) -> bool:
        if self.ros2_bridge_running():
            self.stop_ros2_bridge()
            return False
        return self.start_ros2_bridge()

    def _start_publisher_thread(self) -> None:
        if self._pub_thread and self._pub_thread.is_alive():
            return
        self._pub_stop.clear()
        self._pub_thread = threading.Thread(target=self._publisher_loop, daemon=True)
        self._pub_thread.start()

    def _stop_publisher_thread(self) -> None:
        self._pub_stop.set()

    def _publisher_loop(self) -> None:
        period = 1.0 / max(0.5, float(self.publish_hz))
        while not self._pub_stop.is_set():
            try:
                if self._bridge_running and self.bridge.is_running and self.sensor_stream is not None:
                    snap = self.sensor_stream.latest
                    if snap is not None:
                        self.bridge.publish_snapshot(snap)
            except Exception:
                # keep loop alive
                pass
            time.sleep(period)

    # ------------------------ ROS2 Action handling ------------------------

    def _handle_action_code(self, code: int) -> None:
        # Ejecutar en hilo (nunca bloquear publish loop)
        threading.Thread(target=self._handle_action_code_run, args=(int(code),), daemon=True).start()

    def _handle_action_code_run(self, code: int) -> None:
        """Ejecuta códigos /anafi/drone/action (compatibles con anafi_autonomy).

        Implementados:
          2 takeoff, 4 land, 3 emergency, 11 demo (takeoff + 1m + land)

        Otros códigos se ignoran (pero no rompen la app).
        """
        # Necesitamos Olympe
        try:
            import olympe  # type: ignore
            from olympe.messages.ardrone3.Piloting import TakeOff, Landing, Emergency, moveBy  # type: ignore
            from olympe.messages.ardrone3.PilotingState import FlyingStateChanged  # type: ignore
        except Exception:
            return

        d = None
        try:
            if self.sensor_stream is not None:
                d = getattr(self.sensor_stream.client, "drone", None) or getattr(self.sensor_stream.client, "_drone", None)
        except Exception:
            d = None

        if d is None:
            # Fallback (puede fallar si ya hay otro peer conectado)
            try:
                d = olympe.Drone(self.ip)  # type: ignore
                d.connect()
            except Exception:
                return

        try:
            if code == 2:
                d(TakeOff()).wait(10)
            elif code == 4:
                d(Landing()).wait(15)
            elif code == 3:
                d(Emergency()).wait(5)
            elif code == 11:
                # Demo: takeoff -> subir ~1m -> land
                d(TakeOff()).wait(10)
                d(FlyingStateChanged(state="hovering") | FlyingStateChanged(state="flying")).wait(15)
                d(moveBy(0.0, 0.0, -1.0, 0.0)).wait(12)
                d(FlyingStateChanged(state="hovering") | FlyingStateChanged(state="flying")).wait(15)
                d(Landing()).wait(15)
                d(FlyingStateChanged(state="landed")).wait(40)
            else:
                # No-op for now
                return
        except Exception:
            # Do not raise
            return

    # ------------------------ Autonomy process runner ------------------------

    def autonomy_running(self) -> bool:
        return bool(self._auto_proc is not None and self._auto_proc.poll() is None)

    def start_autonomy_process(self, cmd: str, cwd: Optional[str] = None, env: Optional[dict] = None) -> bool:
        """Start a long-running ROS2 process (e.g., ros2 launch ...).

        Captures stdout+stderr into an internal queue.
        """
        if self.autonomy_running():
            return True

        full_cmd = self._wrap_with_ros2_sources(cmd)

        # Prefer running in bash -lc so ROS2 env variables/aliases work.
        bash_cmd = ["bash", "-lc", full_cmd]
        try:
            self._auto_proc = subprocess.Popen(
                bash_cmd,
                cwd=cwd or None,
                env=env or os.environ.copy(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as e:
            self._set_error(f"Autonomía: {e}")
            self._auto_proc = None
            return False

        self._log_q.put(f"[runner] START: {cmd}\n")
        if full_cmd != cmd:
            # Nota: mostramos qué scripts se sourcetearon (sin spamear demasiado)
            self._log_q.put("[runner] Using sourced ROS2 environment (config.ROS2_SETUP_SCRIPTS)\n")

        self._auto_cmd = cmd
        self._auto_reader_thread = threading.Thread(target=self._read_autonomy_output, daemon=True)
        self._auto_reader_thread.start()
        return True

    def _wrap_with_ros2_sources(self, cmd: str) -> str:
        """Prefija el comando con `source ...` de overlays ROS2 si existen.

        Esto evita el error: "package 'X' not found, searching: ['/opt/ros/humble']"
        cuando tus paquetes están en un workspace colcon (~/ros2_ws, ~/anafi_ws, etc.).
        """

        scripts: list[str] = []
        try:
            from config import ROS2_SETUP_SCRIPTS  # type: ignore

            for s in ROS2_SETUP_SCRIPTS:
                p = os.path.expanduser(str(s))
                if os.path.exists(p):
                    scripts.append(p)
        except Exception:
            scripts = []

        if not scripts:
            return cmd

        # `source` en cascada (humble + overlay(s))
        prefix = " && ".join([f"source {shlex.quote(p)}" for p in scripts])
        return f"{prefix} && {cmd}"

    def _read_autonomy_output(self) -> None:
        p = self._auto_proc
        if p is None or p.stdout is None:
            return
        try:
            for line in p.stdout:
                self._log_q.put(line)
        except Exception:
            pass
        finally:
            try:
                try:
                    rc = p.wait(timeout=0.5)
                except Exception:
                    rc = p.poll()
                self._log_q.put(f"\n[runner] EXIT code={rc}\n")
            except Exception:
                pass

    def stop_autonomy_process(self) -> None:
        p = self._auto_proc
        if p is None:
            return
        if p.poll() is not None:
            self._auto_proc = None
            return

        self._log_q.put("[runner] STOP requested (SIGINT)\n")
        try:
            p.send_signal(signal.SIGINT)
            p.wait(timeout=6)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        self._auto_proc = None
        self._auto_cmd = ""

    def drain_logs(self, max_lines: int = 200) -> list[str]:
        out: list[str] = []
        for _ in range(max_lines):
            try:
                out.append(self._log_q.get_nowait())
            except Exception:
                break
        return out

    # ------------------------ Status / shutdown ------------------------

    def get_status(self) -> ControllerStatus:
        st = ControllerStatus()
        st.sensors_connected = self.sensors_connected()
        st.ros2_bridge_running = self.ros2_bridge_running()
        try:
            st.ros2_published_msgs = int(getattr(self.bridge.stats, "published_msgs", 0))
            st.ros2_last_state = str(getattr(self.bridge.stats, "last_state", ""))
        except Exception:
            pass
        st.autonomy_running = self.autonomy_running()
        try:
            st.autonomy_cmd = self._auto_cmd if self._auto_cmd else ("(running)" if self._auto_proc is not None else "")
        except Exception:
            pass
        st.last_error = self._last_error
        return st

    def _set_error(self, msg: str) -> None:
        with self._lock:
            self._last_error = str(msg)
        try:
            self._log_q.put(f"[error] {msg}\n")
        except Exception:
            pass

    def shutdown(self) -> None:
        # Stop child processes first
        try:
            self.stop_autonomy_process()
        except Exception:
            pass
        # Stop ROS2 bridge
        try:
            self.stop_ros2_bridge()
        except Exception:
            pass
        # Stop sensors
        try:
            self.stop_sensors()
        except Exception:
            pass
        # Try to shutdown rclpy
        try:
            import rclpy  # type: ignore

            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass
