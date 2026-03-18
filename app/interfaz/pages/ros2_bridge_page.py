# interfaz/pages/ros2_bridge_page.py
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox

from config import DRONE_IP, REFRESH_MS
from sensores.streams import SensorStream

from ros2_bridge import ROS2_AVAILABLE, Ros2TelemetryBridge

# Olympe (opcional)
HAVE_OLYMPE = False
try:
    import olympe  # type: ignore
    HAVE_OLYMPE = True
except Exception:
    HAVE_OLYMPE = False


class Ros2BridgePage(tk.Frame):
    """Page that publishes Olympe telemetry into ROS2 topics.

    Thesis-friendly workflow:
    - Keep this Tkinter interface as-is.
    - Read telemetry from Olympe (no video dependency).
    - Publish to ROS2 so autonomy nodes can subscribe.

    Topics published (namespace /anafi):
    - /anafi/drone/altitude (Float32, BEST_EFFORT)
    - /anafi/drone/state (String, RELIABLE)
    - /anafi/drone/steady (Bool, BEST_EFFORT)
    - /anafi/battery/percentage (UInt8, RELIABLE)
    - /anafi/drone/rpy (Vector3Stamped, BEST_EFFORT)
    - /anafi/drone/attitude (QuaternionStamped, BEST_EFFORT)
    - /anafi/drone/speed (Vector3Stamped, BEST_EFFORT)
    - /anafi/drone/gps/fix (Bool, RELIABLE)
    - /anafi/drone/gps/satellites (UInt8, RELIABLE)
    - /anafi/drone/gps/location (NavSatFix, BEST_EFFORT)

    Also includes a minimal autonomy test button (takeoff + moveBy up 1m + land)
    using Olympe directly.
    """

    def __init__(self, parent, drone=None):
        super().__init__(parent, bg="#161b22")

        self._drone = drone
        self.sensor_stream: SensorStream | None = None
        self._owns_stream = False

        self.bridge = Ros2TelemetryBridge(namespace="/anafi")
        self.bridge.on_action = self._handle_action_code
        self._bridge_enabled = False

        # ---------------- UI ----------------
        tk.Label(
            self,
            text="ROS2 Bridge (Olympe → ROS2)",
            fg="white",
            bg="#161b22",
            font=("Segoe UI", 14, "bold"),
        ).pack(pady=(10, 6))

        info = tk.Frame(self, bg="#161b22")
        info.pack(fill="x", padx=12)

        self.var_ros2 = tk.StringVar(value="Disponible" if ROS2_AVAILABLE else "No disponible")
        self.var_stream = tk.StringVar(value="Desconectado")
        self.var_pub = tk.StringVar(value="Detenido")

        self._kv(info, "ROS2:", self.var_ros2).pack(side="left", padx=(0, 16), pady=4)
        self._kv(info, "Sensores:", self.var_stream).pack(side="left", padx=(0, 16), pady=4)
        self._kv(info, "Publicando:", self.var_pub).pack(side="left", padx=(0, 16), pady=4)

        btns = tk.Frame(self, bg="#161b22")
        btns.pack(fill="x", padx=12, pady=(6, 10))

        self.btn_connect = ttk.Button(btns, text="Conectar sensores", command=self._toggle_sensors)
        self.btn_start = ttk.Button(btns, text="▶ Iniciar ROS2", command=self._start_bridge)
        self.btn_stop = ttk.Button(btns, text="■ Detener ROS2", command=self._stop_bridge, state="disabled")

        self.btn_connect.pack(side="left", padx=4)
        self.btn_start.pack(side="left", padx=4)
        self.btn_stop.pack(side="left", padx=4)

        # Telemetry display
        panel = tk.LabelFrame(self, text="Telemetría (Olympe)", bg="#161b22", fg="white")
        panel.pack(fill="x", padx=12, pady=(0, 10))

        self.var_state = tk.StringVar(value="—")
        self.var_batt = tk.StringVar(value="—")
        self.var_alt = tk.StringVar(value="—")
        self.var_rpy = tk.StringVar(value="—")
        self.var_speed = tk.StringVar(value="—")
        self.var_gps = tk.StringVar(value="—")
        self.var_sats = tk.StringVar(value="—")

        row1 = tk.Frame(panel, bg="#161b22")
        row1.pack(fill="x", padx=8, pady=4)
        self._kv(row1, "State:", self.var_state).pack(side="left", padx=(0, 18))
        self._kv(row1, "Batería:", self.var_batt).pack(side="left", padx=(0, 18))
        self._kv(row1, "Alt(m):", self.var_alt).pack(side="left", padx=(0, 18))

        row2 = tk.Frame(panel, bg="#161b22")
        row2.pack(fill="x", padx=8, pady=4)
        self._kv(row2, "RPY(rad):", self.var_rpy).pack(side="left", padx=(0, 18))
        self._kv(row2, "Vel(m/s):", self.var_speed).pack(side="left", padx=(0, 18))

        row3 = tk.Frame(panel, bg="#161b22")
        row3.pack(fill="x", padx=8, pady=4)
        self._kv(row3, "GPS:", self.var_gps).pack(side="left", padx=(0, 18))
        self._kv(row3, "Sats:", self.var_sats).pack(side="left", padx=(0, 18))

        # Autonomy test
        auto = tk.LabelFrame(self, text="Prueba de autonomía (Olympe)", bg="#161b22", fg="white")
        auto.pack(fill="x", padx=12, pady=(0, 10))

        tk.Label(
            auto,
            text="⚠️ Ejecuta SOLO en un lugar seguro. Prueba mínima: despegar, subir ~1m, esperar, aterrizar.",
            fg="#c9d1d9",
            bg="#161b22",
            justify="left",
        ).pack(anchor="w", padx=10, pady=(6, 2))

        auto_btns = tk.Frame(auto, bg="#161b22")
        auto_btns.pack(fill="x", padx=10, pady=(4, 8))

        self.btn_one_meter = ttk.Button(auto_btns, text="🚀 Takeoff + 1m + Land", command=self._one_meter_async)
        self.btn_emerg = ttk.Button(auto_btns, text="🛑 EMERGENCY", command=self._emergency_async)

        self.btn_one_meter.pack(side="left", padx=4)
        self.btn_emerg.pack(side="left", padx=4)

        # Help box
        help_box = tk.LabelFrame(self, text="Comandos útiles", bg="#161b22", fg="white")
        help_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.txt = tk.Text(help_box, height=10, bg="#0d1117", fg="#c9d1d9", insertbackground="white")
        self.txt.pack(fill="both", expand=True, padx=8, pady=8)
        self.txt.insert(
            "end",
            "Si el bridge está activo, puedes verificar desde otra terminal:\n\n"
            "  ros2 topic echo /anafi/drone/altitude --qos-reliability best_effort\n"
            "  ros2 topic echo /anafi/drone/state\n"
            "  ros2 topic echo /anafi/battery/percentage\n\n"
            "Para depurar QoS:\n"
            "  ros2 topic info -v /anafi/drone/altitude\n\n"
            "Nota: este bridge NO depende del stream de cámara.\n"
        )
        self.txt.configure(state="disabled")

        # periodic refresh
        self.after(REFRESH_MS, self._tick)

    # ------------ AppShell hooks ------------
    def set_drone(self, drone):
        self._drone = drone

    def on_show(self):
        # Try to reuse the SensorStream from the Sensores page (avoids double Olympe connections).
        try:
            root = self.winfo_toplevel()
            sp = getattr(root, "pages", {}).get("sensores")
            if sp is not None and hasattr(sp, "sensor_stream"):
                self.sensor_stream = sp.sensor_stream
                self._owns_stream = False
        except Exception:
            pass

        if self.sensor_stream is None:
            self.sensor_stream = SensorStream(DRONE_IP)
            self._owns_stream = True

    def on_hide(self):
        # If we created our own stream, stop it when leaving
        if self._owns_stream and self.sensor_stream is not None:
            try:
                self.sensor_stream.stop()
            except Exception:
                pass

    # ------------ UI helpers ------------
    def _kv(self, parent, k: str, var: tk.StringVar):
        f = tk.Frame(parent, bg=parent["bg"])
        tk.Label(f, text=k, fg="white", bg=parent["bg"]).pack(side="left")
        tk.Label(f, textvariable=var, fg="white", bg=parent["bg"]).pack(side="left", padx=6)
        return f

    def _toggle_sensors(self):
        if self.sensor_stream is None:
            self.sensor_stream = SensorStream(DRONE_IP)
            self._owns_stream = True

        # connected?
        is_connected = False
        try:
            is_connected = bool(self.sensor_stream.client.connected)
        except Exception:
            is_connected = False

        if not is_connected:
            try:
                self.sensor_stream.start()
                self.var_stream.set("Conectado")
                self.btn_connect.configure(text="Desconectar sensores")
            except Exception as e:
                messagebox.showerror("Sensores", f"No se pudo conectar a Olympe.\n\n{e}")
                self.var_stream.set("Error")
        else:
            try:
                self.sensor_stream.stop()
            except Exception:
                pass
            self.var_stream.set("Desconectado")
            self.btn_connect.configure(text="Conectar sensores")

    def _start_bridge(self):
        if not ROS2_AVAILABLE:
            messagebox.showwarning(
                "ROS2",
                "ROS2 (rclpy) no está disponible.\n\n"
                "Asegúrate de ejecutar en una terminal con ROS2 source, por ejemplo:\n"
                "  source /opt/ros/humble/setup.bash",
            )
            return

        if self.sensor_stream is None:
            self.sensor_stream = SensorStream(DRONE_IP)
            self._owns_stream = True

        try:
            self.bridge.start()
        except Exception as e:
            messagebox.showerror("ROS2", f"No se pudo iniciar el bridge ROS2.\n\n{e}")
            return

        self._bridge_enabled = True
        self.var_pub.set("Sí")
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")

    def _stop_bridge(self):
        self._bridge_enabled = False
        try:
            self.bridge.stop()
        except Exception:
            pass

        self.var_pub.set("Detenido")
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def _tick(self):
        # Update UI + publish
        snap = None
        try:
            if self.sensor_stream is not None:
                snap = self.sensor_stream.latest
        except Exception:
            snap = None

        if snap is not None:
            self.var_state.set(str(snap.flight_state or "—"))
            self.var_batt.set(f"{snap.battery_percent:.0f}%" if snap.battery_percent is not None else "—")
            self.var_alt.set(f"{snap.alt_rel:.2f}" if snap.alt_rel is not None else "—")

            if (snap.roll is not None) and (snap.pitch is not None) and (snap.yaw is not None):
                self.var_rpy.set(f"{snap.roll:.2f}, {snap.pitch:.2f}, {snap.yaw:.2f}")
            else:
                self.var_rpy.set("—")

            if (snap.vx is not None) and (snap.vy is not None) and (snap.vz is not None):
                self.var_speed.set(f"{snap.vx:.2f}, {snap.vy:.2f}, {snap.vz:.2f}")
            else:
                self.var_speed.set("—")

            if (snap.lat is not None) and (snap.lon is not None):
                self.var_gps.set(f"{snap.lat:.6f}, {snap.lon:.6f}")
            else:
                self.var_gps.set("—")

            self.var_sats.set(str(snap.num_sats) if snap.num_sats is not None else "—")

            # Publish into ROS2
            if self._bridge_enabled:
                try:
                    self.bridge.publish_snapshot(snap)
                except Exception:
                    # keep GUI alive
                    pass

        # Schedule next tick
        self.after(REFRESH_MS, self._tick)

# ------------ Autonomy test (Olympe) ------------
    def _handle_action_code(self, code: int) -> None:
        """Handle /anafi/drone/action commands (anafi_autonomy-style).

        Common codes:
          2 takeoff, 4 land, 3 emergency, 11 start demo mission (1m up + land)
        """
        th = threading.Thread(
            target=self._handle_action_code_run, args=(int(code),), daemon=True
        )
        th.start()

    def _handle_action_code_run(self, code: int) -> None:
        """Executes an action code using Olympe (blocking)."""
        if not HAVE_OLYMPE:
            return

        d = self._ensure_drone_for_control()
        if d is None:
            return

        try:
            from olympe.messages.ardrone3.Piloting import TakeOff, Landing, Emergency  # type: ignore
        except Exception:
            return

        try:
            if code == 2:  # takeoff
                exp = d(TakeOff())
                if not exp.wait(10).success():
                    raise RuntimeError(
                        "TakeOff no fue aceptado (¿otra app conectada? ¿estado inválido?)"
                    )
            elif code == 4:  # land
                exp = d(Landing())
                if not exp.wait(10).success():
                    raise RuntimeError("Landing no fue aceptado por el dron")
            elif code == 3:  # emergency
                d(Emergency()).wait(5)
            elif code == 11:  # demo mission
                self._one_meter_run()
        except Exception as e:
            try:
                self.after(0, lambda: messagebox.showerror("Acción", str(e)))
            except Exception:
                pass

    def _ensure_drone_for_control(self):
        """Return a connected olympe.Drone instance, reusing existing connections."""
        # 1) Prefer a drone already provided by AppShell
        if self._drone is not None:
            return self._drone

        # 2) Reuse the same Olympe connection used by SensorStream (best option)
        try:
            if self.sensor_stream is not None:
                client = getattr(self.sensor_stream, "client", None)
                # If telemetry polling isn't running yet, start it so we don't
                # create a second Olympe connection just for control.
                if client is not None and not getattr(client, "connected", False):
                    try:
                        self.sensor_stream.start()
                    except Exception:
                        pass

                if client is not None and getattr(client, "connected", False):
                    d = getattr(client, "drone", None) or getattr(client, "_drone", None)
                    if d is not None:
                        self._drone = d
                        return d
        except Exception:
            pass

        if not HAVE_OLYMPE:
            return None

        # 3) Fallback: try direct connection (may fail if another peer is already connected)
        try:
            d = olympe.Drone(DRONE_IP)  # type: ignore
            d.connect()
            self._drone = d
            return d
        except Exception:
            return None

    def _one_meter_async(self):
        threading.Thread(target=self._one_meter_run, daemon=True).start()

    def _emergency_async(self):
        threading.Thread(target=self._emergency_run, daemon=True).start()

    def _one_meter_run(self):
        """Takeoff, move up 1m, land. Runs in background thread."""
        if not HAVE_OLYMPE:
            self.after(0, lambda: messagebox.showwarning("Olympe", "Olympe no está disponible."))
            return

        d = self._ensure_drone_for_control()
        if d is None:
            self.after(
                0,
                lambda: messagebox.showerror(
                    "Olympe",
                    "No se pudo obtener una conexión Olympe para controlar el dron.\n\n"
                    "Tip: cierra otros programas que estén conectados al dron.",
                ),
            )
            return

        from olympe.messages.ardrone3.Piloting import TakeOff, Landing, moveBy  # type: ignore
        from olympe.messages.ardrone3.PilotingState import FlyingStateChanged  # type: ignore

        def ui(msg: str):
            try:
                self.after(0, lambda: self.var_state.set(msg))
            except Exception:
                pass

        try:
            ui("takeoff…")
            exp = d(TakeOff())
            if not exp.wait(10).success():
                raise RuntimeError("TakeOff no fue aceptado por el dron")

            # Wait until hovering/flying
            d(FlyingStateChanged(state="hovering") | FlyingStateChanged(state="flying")).wait(15)

            ui("moveBy dz=-1.0…")
            exp = d(moveBy(0.0, 0.0, -1.0, 0.0))
            if not exp.wait(10).success():
                raise RuntimeError("moveBy no fue aceptado por el dron")

            d(FlyingStateChanged(state="hovering") | FlyingStateChanged(state="flying")).wait(15)

            ui("landing…")
            d(Landing()).wait(10)
            d(FlyingStateChanged(state="landed")).wait(30)
            ui("LANDED")

        except Exception as e:
            err = str(e)
            self.after(0, lambda err=err: messagebox.showerror("Autonomía", "Fallo en prueba 1m:\n\n" + err))

    def _emergency_run(self):
        if not HAVE_OLYMPE:
            return
        d = self._ensure_drone_for_control()
        if d is None:
            return
        try:
            from olympe.messages.ardrone3.Piloting import Emergency  # type: ignore
            d(Emergency()).wait(5)
        except Exception:
            pass
