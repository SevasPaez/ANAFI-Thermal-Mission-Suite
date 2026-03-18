# interfaz/pages/autonomy_page.py
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from config import DRONE_IP
from ros2_bridge import ROS2_AVAILABLE


class AutonomyPage(tk.Frame):
    """Autonomía ROS2 (central).

    Esta página concentra:
    - Estado + control del bridge Olympe→ROS2 (sin depender del RTSP).
    - Lanzador de procesos ROS2 (ros2 launch / ros2 run) con logs embebidos.

    Se apoya en `interfaz.ros2_controller.Ros2Controller` para mantener estado
    aunque cambies de página.
    """

    def __init__(self, parent, controller):
        super().__init__(parent, bg="#161b22")
        self.controller = controller

        # ---------------- Header ----------------
        tk.Label(
            self,
            text="Centro ROS2 y misión",
            fg="white",
            bg="#161b22",
            font=("Segoe UI", 14, "bold"),
        ).pack(pady=(10, 6))

        info = tk.Frame(self, bg="#161b22")
        info.pack(fill="x", padx=12)

        self.var_ros2 = tk.StringVar(value="Disponible" if ROS2_AVAILABLE else "No disponible")
        self.var_sensors = tk.StringVar(value="—")
        self.var_bridge = tk.StringVar(value="—")
        self.var_state = tk.StringVar(value="—")
        self.var_pub = tk.StringVar(value="0")
        self.var_auto = tk.StringVar(value="—")

        self._kv(info, "ROS2:", self.var_ros2).pack(side="left", padx=(0, 16), pady=4)
        self._kv(info, "Sensores:", self.var_sensors).pack(side="left", padx=(0, 16), pady=4)
        self._kv(info, "Bridge:", self.var_bridge).pack(side="left", padx=(0, 16), pady=4)
        self._kv(info, "Estado:", self.var_state).pack(side="left", padx=(0, 16), pady=4)
        self._kv(info, "Msgs:", self.var_pub).pack(side="left", padx=(0, 16), pady=4)
        self._kv(info, "Runner:", self.var_auto).pack(side="left", padx=(0, 16), pady=4)

        # ---------------- Controls: Bridge ----------------
        controls = tk.LabelFrame(self, text="Bridge Olympe → ROS2", bg="#161b22", fg="white")
        controls.pack(fill="x", padx=12, pady=(10, 8))

        btn_row = tk.Frame(controls, bg="#161b22")
        btn_row.pack(fill="x", padx=10, pady=8)

        self.btn_sensors = ttk.Button(btn_row, text="Conectar sensores", command=self._toggle_sensors)
        self.btn_bridge = ttk.Button(btn_row, text="▶ Iniciar bridge", command=self._toggle_bridge)
        self.btn_sensors.pack(side="left", padx=4)
        self.btn_bridge.pack(side="left", padx=4)

        ttk.Label(
            controls,
            text=(
                "Este bridge publica telemetría a /anafi/* y además escucha /anafi/drone/action (UInt8).\n"
                "Ejemplo (otra terminal): ros2 topic pub --once /anafi/drone/action std_msgs/msg/UInt8 '{data: 2}'"
            ),
            foreground="#9da7b3",
        ).pack(anchor="w", padx=12, pady=(0, 10))

        # ---------------- Controls: Runner ----------------
        runner = tk.LabelFrame(self, text="Runner ROS2 (launch/run + logs)", bg="#161b22", fg="white")
        runner.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        top = tk.Frame(runner, bg="#161b22")
        top.pack(fill="x", padx=10, pady=(8, 6))

        self.var_preset = tk.StringVar(value="Mission Manager (recomendado)")
        presets = [
            "Mission Manager (recomendado)",
            "anafi_ros_nodes driver (original)",
            "control_anafi_launch.py (driver + keyboard xterm)",
            "custom",
        ]
        ttk.Label(top, text="Preset:").pack(side="left")
        cb = ttk.Combobox(top, textvariable=self.var_preset, values=presets, state="readonly", width=40)
        cb.pack(side="left", padx=(6, 12))
        cb.bind("<<ComboboxSelected>>", lambda _e: self._apply_preset())

        ttk.Label(top, text="IP:").pack(side="left")
        self.var_ip = tk.StringVar(value=DRONE_IP)
        ttk.Entry(top, textvariable=self.var_ip, width=14).pack(side="left", padx=(6, 12))

        ttk.Label(top, text="Model:").pack(side="left")
        self.var_model = tk.StringVar(value="thermal")
        ttk.Combobox(top, textvariable=self.var_model, values=["thermal", "4k", "usa", "ai"], width=10, state="readonly").pack(
            side="left", padx=(6, 12)
        )

        ttk.Label(top, text="Namespace:").pack(side="left")
        self.var_ns = tk.StringVar(value="anafi")
        ttk.Entry(top, textvariable=self.var_ns, width=10).pack(side="left", padx=(6, 0))

        cmd_row = tk.Frame(runner, bg="#161b22")
        cmd_row.pack(fill="x", padx=10, pady=(0, 6))

        ttk.Label(cmd_row, text="Comando:").pack(side="left")
        self.var_cmd = tk.StringVar(value="")
        self.entry_cmd = ttk.Entry(cmd_row, textvariable=self.var_cmd)
        self.entry_cmd.pack(side="left", fill="x", expand=True, padx=(6, 6))

        btns = tk.Frame(runner, bg="#161b22")
        btns.pack(fill="x", padx=10, pady=(0, 8))

        self.btn_start = ttk.Button(btns, text="▶ Start", command=self._start_runner)
        self.btn_stop = ttk.Button(btns, text="■ Stop", command=self._stop_runner)
        self.btn_clear = ttk.Button(btns, text="🧹 Limpiar logs", command=self._clear_logs)
        self.btn_start.pack(side="left", padx=4)
        self.btn_stop.pack(side="left", padx=4)
        self.btn_clear.pack(side="left", padx=4)

        # Logs box
        self.txt = tk.Text(runner, height=14, bg="#0d1117", fg="#c9d1d9", insertbackground="white")
        self.txt.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._apply_preset()
        self.after(250, self._tick)

    def _kv(self, parent, k: str, var: tk.StringVar):
        f = tk.Frame(parent, bg=parent["bg"])
        tk.Label(f, text=k, fg="white", bg=parent["bg"]).pack(side="left")
        tk.Label(f, textvariable=var, fg="white", bg=parent["bg"]).pack(side="left", padx=6)
        return f

    # --------------- Bridge actions ---------------

    def _toggle_sensors(self):
        ok = self.controller.toggle_sensors()
        if not ok and self.controller.get_status().last_error:
            messagebox.showerror("Sensores", self.controller.get_status().last_error)

    def _toggle_bridge(self):
        if not ROS2_AVAILABLE:
            messagebox.showwarning(
                "ROS2",
                "ROS2 (rclpy) no está disponible.\n\n"
                "Inicia la app desde una terminal con ROS2, por ejemplo:\n"
                "  source /opt/ros/humble/setup.bash",
            )
            return

        ok = self.controller.toggle_ros2_bridge()
        if not ok and self.controller.get_status().last_error:
            messagebox.showerror("ROS2 Bridge", self.controller.get_status().last_error)

    # --------------- Runner presets ---------------

    def _apply_preset(self):
        ip = self.var_ip.get().strip() or DRONE_IP
        model = self.var_model.get().strip() or "thermal"
        ns = self.var_ns.get().strip() or "anafi"

        p = self.var_preset.get()
        if p.startswith("Mission Manager"):
            self.var_cmd.set(
                f"ros2 run anafi_mission_manager mission_manager --ros-args -r __ns:=/{ns}"
            )
        elif p.startswith("anafi_ros_nodes driver"):
            self.var_cmd.set(
                f"ros2 launch anafi_ros_nodes anafi_launch.py namespace:={ns} ip:='{ip}' model:='{model}'"
            )
        elif p.startswith("control_anafi_launch.py"):
            self.var_cmd.set(
                f"ros2 launch anafi_autonomy control_anafi_launch.py namespace:={ns} ip:='{ip}' model:='{model}'"
            )
        else:
            if not self.var_cmd.get().strip():
                self.var_cmd.set("ros2 topic list")

    # --------------- Runner actions ---------------

    def _start_runner(self):
        cmd = self.var_cmd.get().strip()
        if not cmd:
            return

        # Evitar doble conexión Olympe cuando el proceso externo controla el dron.
        preset = self.var_preset.get()
        if (
            "driver" in preset
            or preset.startswith("Mission Manager")
            or preset.startswith("anafi_autonomy")
            or preset.startswith("control_anafi")
        ):
            try:
                self.controller.stop_ros2_bridge()
                self.controller.stop_sensors()
            except Exception:
                pass

        ok = self.controller.start_autonomy_process(cmd)
        if not ok and self.controller.get_status().last_error:
            messagebox.showerror("Runner", self.controller.get_status().last_error)

    def _stop_runner(self):
        self.controller.stop_autonomy_process()

    def _clear_logs(self):
        self.txt.delete("1.0", "end")

    # --------------- Tick ---------------

    def _tick(self):
        st = self.controller.get_status()
        self.var_sensors.set("Conectado" if st.sensors_connected else "Desconectado")
        self.var_bridge.set("ON" if st.ros2_bridge_running else "OFF")
        self.var_state.set(st.ros2_last_state or "—")
        self.var_pub.set(str(st.ros2_published_msgs))
        self.var_auto.set("ON" if st.autonomy_running else "OFF")

        # Update buttons text
        self.btn_sensors.configure(text="Desconectar sensores" if st.sensors_connected else "Conectar sensores")
        self.btn_bridge.configure(text="■ Detener bridge" if st.ros2_bridge_running else "▶ Iniciar bridge")
        self.btn_start.configure(state=("disabled" if st.autonomy_running else "normal"))
        self.btn_stop.configure(state=("normal" if st.autonomy_running else "disabled"))

        # Drain logs
        lines = self.controller.drain_logs(max_lines=200)
        if lines:
            self.txt.configure(state="normal")
            for ln in lines:
                self.txt.insert("end", ln)
            self.txt.see("end")

        self.after(250, self._tick)

    def on_hide(self):
        # No detenemos nada: el estado debe persistir aunque cambies de página.
        pass
