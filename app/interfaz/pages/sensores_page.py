import math
import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from sensores.drone_client import SensorSnapshot
from sensores.streams import SensorStream
from interfaz.plot3d import Plot3D, make_cube
from config import DRONE_IP, REFRESH_MS, PATH_MAX_POINTS, CUBE_SIZE, DT_FALLBACK


class SensoresPage(tk.Frame):
    def __init__(self, parent, controller=None):
        super().__init__(parent, bg="#161b22")
        self.controller = controller

        # Unificar stream de telemetría si hay controlador global
        if self.controller is not None:
            self.sensor_stream = self.controller.ensure_sensor_stream()
        else:
            self.sensor_stream = SensorStream(DRONE_IP)

        self.connected = False
        self.path_pts = []
        self.base_cube = make_cube(CUBE_SIZE)

        # Top bar
        top = tk.Frame(self, bg="#0d1117")
        top.pack(side="top", fill="x")
        self.var_state = tk.StringVar(value="—")
        self.var_batt = tk.StringVar(value="—")
        self.btn_connect = tk.Button(top, text="Conectar", command=self.toggle_connect)
        self.btn_connect.pack(side="right", padx=10, pady=8)
        self._label(top, "Estado:", self.var_state).pack(side="left", padx=(12, 4), pady=8)
        self._label(top, "Batería:", self.var_batt).pack(side="left", padx=(16, 4))

        # Center: left info + right plot
        center = tk.Frame(self, bg="#161b22")
        center.pack(side="top", fill="both", expand=True)

        left = tk.LabelFrame(center, text="IMU / Vel / GPS", bg="#161b22", fg="white")
        left.pack(side="left", fill="y", padx=10, pady=10)

        self.var_roll = tk.StringVar(value="—")
        self.var_pitch = tk.StringVar(value="—")
        self.var_yaw = tk.StringVar(value="—")
        self.var_alt = tk.StringVar(value="—")
        self.var_vx = tk.StringVar(value="—")
        self.var_vy = tk.StringVar(value="—")
        self.var_vz = tk.StringVar(value="—")
        self.var_lat = tk.StringVar(value="—")
        self.var_lon = tk.StringVar(value="—")
        self.var_gps_alt = tk.StringVar(value="—")
        self.var_fix = tk.StringVar(value="—")
        self.var_sats = tk.StringVar(value="—")

        for lbl, var in [
            ("Roll (°):", self.var_roll),
            ("Pitch (°):", self.var_pitch),
            ("Yaw (°):", self.var_yaw),
            ("Alt (m):", self.var_alt),
            ("Vx (m/s):", self.var_vx),
            ("Vy (m/s):", self.var_vy),
            ("Vz (m/s):", self.var_vz),
            ("Lat:", self.var_lat),
            ("Lon:", self.var_lon),
            ("Alt GPS:", self.var_gps_alt),
            ("Fix:", self.var_fix),
            ("#Sats:", self.var_sats),
        ]:
            row = tk.Frame(left, bg="#161b22")
            row.pack(fill="x", padx=6, pady=3)
            tk.Label(row, text=lbl, fg="white", bg="#161b22").pack(side="left")
            tk.Label(row, textvariable=var, fg="white", bg="#161b22").pack(side="left", padx=6)

        right = tk.Frame(center, bg="#161b22")
        right.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        self.plot = Plot3D()
        self.canvas = FigureCanvasTkAgg(self.plot.fig, master=right)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # Disparar refresco periódico
        self._refresh = self._do_refresh  # alias por compatibilidad
        self.after(REFRESH_MS, self._do_refresh)

    def _label(self, parent, text, var):
        f = tk.Frame(parent, bg=parent["bg"])
        tk.Label(f, text=text, fg="white", bg=parent["bg"]).pack(side="left")
        tk.Label(f, textvariable=var, fg="white", bg=parent["bg"]).pack(side="left", padx=4)
        return f

    def toggle_connect(self):
        if self.controller is not None:
            self.controller.toggle_sensors()
            return

        # Modo legacy (sin controlador)
        if not self.connected:
            try:
                self.sensor_stream.start()
                self.connected = True
                self.btn_connect.configure(text="Desconectar")
            except Exception as e:
                print("Error al conectar sensores:", e)
                self.connected = False
        else:
            try:
                self.sensor_stream.stop()
            finally:
                self.connected = False
                self.btn_connect.configure(text="Conectar")

    def _do_refresh(self):
        # Estado real de conexión
        if self.controller is not None:
            self.connected = bool(self.controller.sensors_connected())
        # Sin controlador: self.connected se maneja en toggle_connect

        self.btn_connect.configure(text=("Desconectar" if self.connected else "Conectar"))

        snap: SensorSnapshot | None = self.sensor_stream.latest if self.connected else None
        if snap is not None:
            # Estado / batería
            self.var_state.set(snap.flight_state or "—")
            self.var_batt.set(f"{snap.battery_percent:.0f} %" if snap.battery_percent is not None else "N/A")
            # IMU
            self.var_roll.set(f"{math.degrees(snap.roll):.1f}" if snap.roll is not None else "—")
            self.var_pitch.set(f"{math.degrees(snap.pitch):.1f}" if snap.pitch is not None else "—")
            self.var_yaw.set(f"{math.degrees(snap.yaw):.1f}" if snap.yaw is not None else "—")
            # Alt/Vel
            self.var_alt.set(f"{snap.alt_rel:.2f}" if snap.alt_rel is not None else "—")
            self.var_vx.set(f"{snap.vx:.2f}" if snap.vx is not None else "—")
            self.var_vy.set(f"{snap.vy:.2f}" if snap.vy is not None else "—")
            self.var_vz.set(f"{snap.vz:.2f}" if snap.vz is not None else "—")
            # GPS
            self.var_lat.set(f"{snap.lat:.6f}" if snap.lat is not None else "—")
            self.var_lon.set(f"{snap.lon:.6f}" if snap.lon is not None else "—")
            self.var_gps_alt.set(f"{snap.alt_gps:.1f}" if snap.alt_gps is not None else "—")
            self.var_fix.set("OK" if snap.gps_fix else ("NO" if snap.gps_fix is not None else "—"))
            self.var_sats.set(str(snap.num_sats) if snap.num_sats is not None else "—")

            # ENU + path + 3D
            try:
                pos_enu = self.sensor_stream.client.compute_enu(snap, DT_FALLBACK)
                self.path_pts.append(pos_enu)
                if len(self.path_pts) > PATH_MAX_POINTS:
                    self.path_pts = self.path_pts[-PATH_MAX_POINTS:]

                if (snap.roll is not None) and (snap.pitch is not None) and (snap.yaw is not None):
                    self.plot.update_scene(snap.roll, snap.pitch, snap.yaw, pos_enu, self.base_cube)
                    self.plot.update_path(self.path_pts)
                    self.canvas.draw_idle()
            except Exception:
                pass

        self.after(REFRESH_MS, self._do_refresh)
