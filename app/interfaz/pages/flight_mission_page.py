
from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import threading
import time
import datetime as _dt
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from sensores.photo_metadata import PhotoMetadataStore

from config import DRONE_IP, DRONE_RTSP_URL, RTSP_TRANSPORT
from interfaz.ros2_mission_client import Ros2MissionClient, ROS2_AVAILABLE as ROS2_MISSION_AVAILABLE

try:
    from config import MEDIA_ROOT
    _MEDIA_ROOT = MEDIA_ROOT
except Exception:
    _MEDIA_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media")

_MISSIONS_DIR = os.path.join(_MEDIA_ROOT, "missions")
os.makedirs(_MISSIONS_DIR, exist_ok=True)

_RGB_PHOTOS_DIR = os.path.join(_MEDIA_ROOT, "rgb", "photos")
_RGB_VIDEOS_DIR = os.path.join(_MEDIA_ROOT, "rgb", "videos")
os.makedirs(_RGB_PHOTOS_DIR, exist_ok=True)
os.makedirs(_RGB_VIDEOS_DIR, exist_ok=True)

MISSION_TYPES = [
    "moveby_waypoints",
    "grid",
    "orbit",
    "spiral",
    "rectangle",
    "custom",
]

FRAMES = ["BODY", "LOCAL_ENU"]

WP_ACTIONS = ["none", "photo", "video_start", "video_stop"]
SENSORS = ["thermal", "rgb"]

PHOTO_MODES = ["single", "burst"]
VIDEO_QUALITIES = ["1080p", "4k"]

BG_PRIMARY = "#161b22"
BG_PANEL = "#161b22"
FG_PRIMARY = "white"

class FlightMissionPage(tk.Frame):

    def __init__(self, parent, drone=None, controller=None):
        super().__init__(parent, bg=BG_PRIMARY)

        self._drone = drone
        self._controller = controller
        self._ros2_client = None
        self._ros2_managed = False
        self._cancel = threading.Event()
        self._runner_thread: threading.Thread | None = None
        self._video_proc: subprocess.Popen | None = None

        self.meta_store = PhotoMetadataStore(media_root=_MEDIA_ROOT)

        self.var_name = tk.StringVar(value="mision_1")
        self.var_type = tk.StringVar(value=MISSION_TYPES[0])
        self.var_frame = tk.StringVar(value=FRAMES[0])
        self.var_nwp = tk.IntVar(value=4)
        self.var_takeoff = tk.BooleanVar(value=True)
        self.var_land = tk.BooleanVar(value=True)
        self.var_speed_mps = tk.StringVar(value="1.0")
        self.var_gimbal_pitch_deg = tk.StringVar(value="-90.0")

        self._speed_cmd_checked = False
        self._speed_cmd_cls = None

        self.wp_dx = tk.StringVar(value="0.0")
        self.wp_dy = tk.StringVar(value="0.0")
        self.wp_dz = tk.StringVar(value="0.0")
        self.wp_dyaw = tk.StringVar(value="0.0")
        self.wp_wait = tk.StringVar(value="0.0")

        self.wp_action = tk.StringVar(value=WP_ACTIONS[0])
        self.wp_sensor = tk.StringVar(value=SENSORS[0])
        self.wp_mode = tk.StringVar(value="-")

        tk.Label(
            self,
            text="Misión de vuelo (JSON + ejecución)",
            fg=FG_PRIMARY,
            bg=BG_PRIMARY,
            font=("Segoe UI", 14, "bold"),
        ).pack(pady=(10, 6))

        top = tk.Frame(self, bg=BG_PRIMARY)
        top.pack(fill="x", padx=12, pady=(0, 8))

        row1 = tk.Frame(top, bg=BG_PRIMARY)
        row1.pack(fill="x", pady=2)
        self._lbl(row1, "Nombre:")
        ttk.Entry(row1, textvariable=self.var_name, width=26).pack(side="left", padx=(4, 12))

        self._lbl(row1, "Tipo:")
        ttk.Combobox(row1, textvariable=self.var_type, values=MISSION_TYPES, width=18, state="readonly").pack(
            side="left", padx=(4, 12)
        )

        self._lbl(row1, "Frame:")
        ttk.Combobox(row1, textvariable=self.var_frame, values=FRAMES, width=10, state="readonly").pack(
            side="left", padx=(4, 12)
        )

        self._lbl(row1, "# Waypoints:")
        sp = ttk.Spinbox(row1, from_=1, to=999, textvariable=self.var_nwp, width=6, command=self._sync_n_waypoints)
        sp.pack(side="left", padx=(4, 12))

        self._lbl(row1, "Velocidad (m/s):")
        tk.Entry(row1, textvariable=self.var_speed_mps, width=7, bg=BG_PRIMARY, fg=FG_PRIMARY, insertbackground=FG_PRIMARY, highlightthickness=1, highlightbackground=FG_PRIMARY).pack(side="left", padx=(4, 12))

        self._lbl(row1, "Gimbal pitch (°):")
        tk.Entry(row1, textvariable=self.var_gimbal_pitch_deg, width=7, bg=BG_PRIMARY, fg=FG_PRIMARY, insertbackground=FG_PRIMARY, highlightthickness=1, highlightbackground=FG_PRIMARY).pack(side="left", padx=(4, 12))

        ttk.Checkbutton(row1, text="Auto takeoff", variable=self.var_takeoff).pack(side="left", padx=(6, 10))
        ttk.Checkbutton(row1, text="Auto land", variable=self.var_land).pack(side="left")

        row2 = tk.Frame(top, bg=BG_PRIMARY)
        row2.pack(fill="x", pady=(6, 2))

        ttk.Button(row2, text="Nuevo", command=self._new_mission).pack(side="left", padx=4)
        ttk.Button(row2, text="Cargar JSON…", command=self._load_json).pack(side="left", padx=4)
        ttk.Button(row2, text="Guardar JSON…", command=self._save_json).pack(side="left", padx=4)
        ttk.Button(row2, text="Validar", command=self._validate_ui).pack(side="left", padx=4)

        ttk.Button(row2, text="Exportar metadatos…", command=self._export_metadata_dialog).pack(
            side="left", padx=(16, 4)
        )
        ttk.Button(row2, text="Limpiar metadatos", command=self._clear_metadata).pack(side="left", padx=4)

        self.btn_run = ttk.Button(row2, text="▶ Ejecutar", command=self._run_async)
        self.btn_stop = ttk.Button(row2, text="■ Detener", command=self._stop_run, state="disabled")
        self.btn_run.pack(side="left", padx=(16, 4))
        self.btn_stop.pack(side="left", padx=4)

        self.var_status = tk.StringVar(value="Listo")
        ttk.Label(row2, textvariable=self.var_status).pack(side="right", padx=6)

        main = tk.Frame(self, bg=BG_PRIMARY)
        main.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        main.grid_columnconfigure(0, weight=3)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(0, weight=1)

        left = tk.LabelFrame(main, text="Waypoints", bg=BG_PRIMARY, fg=FG_PRIMARY)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)

        cols = ("idx", "dx", "dy", "dz", "dyaw_deg", "wait_s", "action", "sensor", "mode")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=12)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=90 if c not in ("idx", "action", "sensor", "mode") else 80, anchor="center")
        self.tree.column("idx", width=50)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        yscroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        yscroll.grid(row=0, column=1, sticky="ns", pady=8)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        tools = tk.Frame(left, bg=BG_PRIMARY)
        tools.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
        ttk.Button(tools, text="↑ Subir", command=lambda: self._move_selected(-1)).pack(side="left", padx=4)
        ttk.Button(tools, text="↓ Bajar", command=lambda: self._move_selected(+1)).pack(side="left", padx=4)
        ttk.Button(tools, text="Insertar", command=self._insert_after).pack(side="left", padx=4)
        ttk.Button(tools, text="Eliminar", command=self._delete_selected).pack(side="left", padx=4)

        right = tk.LabelFrame(main, text="Editor de waypoint", bg=BG_PRIMARY, fg=FG_PRIMARY)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(1, weight=1)

        r = 0
        self._grid_kv(right, r, "dx (m, +adelante):", self.wp_dx); r += 1
        self._grid_kv(right, r, "dy (m, +derecha):", self.wp_dy); r += 1
        self._grid_kv(right, r, "dz (m, +abajo):", self.wp_dz); r += 1
        self._grid_kv(right, r, "dyaw (deg):", self.wp_dyaw); r += 1
        self._grid_kv(right, r, "wait_s:", self.wp_wait); r += 1

        ttk.Label(right, text="Acción:").grid(row=r, column=0, sticky="w", padx=10, pady=6)
        cb_action = ttk.Combobox(right, textvariable=self.wp_action, values=WP_ACTIONS, state="readonly")
        cb_action.grid(row=r, column=1, sticky="ew", padx=10, pady=6)
        cb_action.bind("<<ComboboxSelected>>", lambda _e: self._refresh_mode_choices())
        r += 1

        ttk.Label(right, text="Sensor:").grid(row=r, column=0, sticky="w", padx=10, pady=6)
        ttk.Combobox(right, textvariable=self.wp_sensor, values=SENSORS, state="readonly").grid(
            row=r, column=1, sticky="ew", padx=10, pady=6
        )
        r += 1

        ttk.Label(right, text="Modo:").grid(row=r, column=0, sticky="w", padx=10, pady=6)
        self.cb_mode = ttk.Combobox(right, textvariable=self.wp_mode, values=["-"], state="readonly")
        self.cb_mode.grid(row=r, column=1, sticky="ew", padx=10, pady=6)
        r += 1

        btn_apply = ttk.Button(right, text="Aplicar al waypoint seleccionado", command=self._apply_to_selected)
        btn_apply.grid(row=r, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 8))

        ttk.Label(
            right,
            text="Tip: dyaw está en grados aquí y se convierte a radianes al ejecutar moveBy.",
            foreground="#9da7b3",
        ).grid(row=r + 1, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))

        self._sync_n_waypoints()
        self._refresh_mode_choices()
        self.after(300, self._ros2_tick)

    def _lbl(self, parent, text: str):
        tk.Label(parent, text=text, fg=FG_PRIMARY, bg=BG_PRIMARY).pack(side="left")

    def _grid_kv(self, parent, row: int, label: str, var: tk.StringVar):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=10, pady=6)

    def _set_status(self, msg: str):
        try:
            self.var_status.set(msg)
        except Exception:
            pass

    def set_drone(self, drone):
        self._drone = drone
        self._controller = controller
        self._ros2_client = None
        self._ros2_managed = False

    def on_show(self):

        pass

    def _default_wp(self, idx: int) -> dict:
        return {
            "idx": idx + 1,
            "dx": 0.0,
            "dy": 0.0,
            "dz": 0.0,
            "dyaw_deg": 0.0,
            "wait_s": 0.0,
            "action": "none",
            "sensor": "thermal",
            "mode": "-",
        }

    def _sync_n_waypoints(self):

        n = max(1, int(self.var_nwp.get() or 1))
        existing = list(self.tree.get_children(""))

        while len(existing) < n:
            i = len(existing)
            wp = self._default_wp(i)
            iid = self.tree.insert("", "end", values=self._wp_to_row(wp))
            existing.append(iid)

        while len(existing) > n:
            iid = existing.pop()
            self.tree.delete(iid)

        self._reindex_tree()

        kids = self.tree.get_children("")
        if kids:
            self.tree.selection_set(kids[0])
            self.tree.focus(kids[0])
            self._on_select()

    def _reindex_tree(self):
        kids = list(self.tree.get_children(""))
        for i, iid in enumerate(kids):
            row = list(self.tree.item(iid, "values"))
            row[0] = str(i + 1)
            self.tree.item(iid, values=row)

    def _wp_to_row(self, wp: dict):
        return (
            str(wp.get("idx", "")),
            f"{wp.get('dx', 0.0):.3f}",
            f"{wp.get('dy', 0.0):.3f}",
            f"{wp.get('dz', 0.0):.3f}",
            f"{wp.get('dyaw_deg', 0.0):.1f}",
            f"{wp.get('wait_s', 0.0):.2f}",
            wp.get("action", "none"),
            wp.get("sensor", "thermal"),
            wp.get("mode", "-"),
        )

    def _row_to_wp(self, row_vals: tuple):

        return {
            "idx": int(row_vals[0]),
            "dx": float(row_vals[1]),
            "dy": float(row_vals[2]),
            "dz": float(row_vals[3]),
            "dyaw_deg": float(row_vals[4]),
            "wait_s": float(row_vals[5]),
            "action": row_vals[6],
            "sensor": row_vals[7],
            "mode": row_vals[8],
        }

    def _on_select(self, *_):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        vals = self.tree.item(iid, "values")
        if not vals:
            return
        wp = self._row_to_wp(vals)
        self.wp_dx.set(str(wp["dx"]))
        self.wp_dy.set(str(wp["dy"]))
        self.wp_dz.set(str(wp["dz"]))
        self.wp_dyaw.set(str(wp["dyaw_deg"]))
        self.wp_wait.set(str(wp["wait_s"]))
        self.wp_action.set(wp["action"])
        self.wp_sensor.set(wp["sensor"])
        self._refresh_mode_choices(prefer=wp.get("mode", "-"))

    def _apply_to_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        try:
            dx = float(self.wp_dx.get())
            dy = float(self.wp_dy.get())
            dz = float(self.wp_dz.get())
            dyaw = float(self.wp_dyaw.get())
            wait_s = float(self.wp_wait.get())
        except Exception:
            messagebox.showerror("Waypoint", "dx/dy/dz/dyaw/wait_s deben ser numéricos.")
            return

        action = self.wp_action.get()
        sensor = self.wp_sensor.get()
        mode = self.wp_mode.get()

        cur = list(self.tree.item(iid, "values"))

        cur[1] = f"{dx:.3f}"
        cur[2] = f"{dy:.3f}"
        cur[3] = f"{dz:.3f}"
        cur[4] = f"{dyaw:.1f}"
        cur[5] = f"{wait_s:.2f}"
        cur[6] = action
        cur[7] = sensor
        cur[8] = mode
        self.tree.item(iid, values=cur)

    def _move_selected(self, delta: int):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        kids = list(self.tree.get_children(""))
        i = kids.index(iid)
        j = max(0, min(len(kids) - 1, i + delta))
        if i == j:
            return
        vals_i = self.tree.item(kids[i], "values")
        vals_j = self.tree.item(kids[j], "values")
        self.tree.item(kids[i], values=vals_j)
        self.tree.item(kids[j], values=vals_i)
        self._reindex_tree()
        kids2 = list(self.tree.get_children(""))
        self.tree.selection_set(kids2[j])
        self.tree.focus(kids2[j])

    def _insert_after(self):
        kids = list(self.tree.get_children(""))
        sel = self.tree.selection()
        if sel:
            idx = kids.index(sel[0]) + 1
        else:
            idx = len(kids)
        wp = self._default_wp(idx)
        iid = self.tree.insert("", idx, values=self._wp_to_row(wp))
        self.var_nwp.set(len(kids) + 1)
        self._reindex_tree()
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self._on_select()

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        self.tree.delete(iid)
        kids = list(self.tree.get_children(""))
        self.var_nwp.set(max(1, len(kids)))
        self._reindex_tree()
        if kids:
            self.tree.selection_set(kids[min(len(kids) - 1, 0)])

    def _refresh_mode_choices(self, prefer: str | None = None):
        action = self.wp_action.get()
        if action == "photo":
            values = PHOTO_MODES
            state = "readonly"
        elif action == "video_start":
            values = VIDEO_QUALITIES
            state = "readonly"
        else:
            values = ["-"]
            state = "disabled"

        self.cb_mode.configure(values=values, state=state)
        if prefer in values:
            self.wp_mode.set(prefer)
        else:
            self.wp_mode.set(values[0] if values else "-")

    def _collect_mission_dict(self) -> dict:
        wps = []
        for iid in self.tree.get_children(""):
            vals = self.tree.item(iid, "values")
            wp = self._row_to_wp(vals)

            item = {
                "dx": wp["dx"],
                "dy": wp["dy"],
                "dz": wp["dz"],
                "dyaw_deg": wp["dyaw_deg"],
                "wait_s": wp["wait_s"],
                "action": {
                    "type": wp["action"],
                    "sensor": wp["sensor"],
                    "mode": wp["mode"],
                },
            }
            wps.append(item)

        return {
            "name": self.var_name.get().strip() or "mission",
            "type": self.var_type.get(),
            "frame": self.var_frame.get(),
            "auto": {"takeoff": bool(self.var_takeoff.get()), "land": bool(self.var_land.get())},
            "failsafe": {
                "on_failure": "land"
            },
            "params": {
                "speed_mps": float(self.var_speed_mps.get() or 0.0),
                "gimbal_pitch_deg": float(self.var_gimbal_pitch_deg.get() or 0.0),
            },
            "waypoints": wps,
        }

    def _apply_mission_dict(self, d: dict):
        self.var_name.set(d.get("name", "mission"))
        t = d.get("type", MISSION_TYPES[0])
        self.var_type.set(t if t in MISSION_TYPES else MISSION_TYPES[0])
        f = d.get("frame", FRAMES[0])
        self.var_frame.set(f if f in FRAMES else FRAMES[0])
        auto = d.get("auto", {}) if isinstance(d.get("auto", {}), dict) else {}
        self.var_takeoff.set(bool(auto.get("takeoff", True)))
        self.var_land.set(bool(auto.get("land", True)))

        params = d.get("params", {}) if isinstance(d.get("params", {}), dict) else {}
        self.var_speed_mps.set(str(params.get("speed_mps", 1.0)))
        self.var_gimbal_pitch_deg.set(str(params.get("gimbal_pitch_deg", 0.0)))

        waypoints = d.get("waypoints", [])
        if not isinstance(waypoints, list):
            waypoints = []

        for iid in self.tree.get_children(""):
            self.tree.delete(iid)

        for i, item in enumerate(waypoints):
            if not isinstance(item, dict):
                continue
            a = item.get("action", {}) if isinstance(item.get("action", {}), dict) else {}
            wp = {
                "idx": i + 1,
                "dx": float(item.get("dx", 0.0)),
                "dy": float(item.get("dy", 0.0)),
                "dz": float(item.get("dz", 0.0)),
                "dyaw_deg": float(item.get("dyaw_deg", 0.0)),
                "wait_s": float(item.get("wait_s", 0.0)),
                "action": a.get("type", "none"),
                "sensor": a.get("sensor", "thermal"),
                "mode": a.get("mode", "-"),
            }
            self.tree.insert("", "end", values=self._wp_to_row(wp))

        n = len(self.tree.get_children(""))
        self.var_nwp.set(max(1, n))
        if n == 0:
            self._sync_n_waypoints()
        else:
            self._reindex_tree()
            kids = self.tree.get_children("")
            self.tree.selection_set(kids[0])
            self.tree.focus(kids[0])
            self._on_select()

    def _new_mission(self):
        self.var_name.set("mision_1")
        self.var_type.set(MISSION_TYPES[0])
        self.var_frame.set(FRAMES[0])
        self.var_nwp.set(4)
        self.var_takeoff.set(True)
        self.var_land.set(True)
        self.var_speed_mps.set("1.0")
        self.var_gimbal_pitch_deg.set("0.0")
        self._sync_n_waypoints()
        self._set_status("Nueva misión")

    def _save_json(self):
        if not self._validate_ui(show_ok=False):
            return
        d = self._collect_mission_dict()
        default = (d.get("name") or "mission").strip().replace(" ", "_") + ".json"
        path = filedialog.asksaveasfilename(
            title="Guardar misión JSON",
            initialdir=_MISSIONS_DIR,
            initialfile=default,
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            self._set_status(f"Guardado: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Guardar", f"No se pudo guardar JSON.\n\n{e}")

    def _load_json(self):
        path = filedialog.askopenfilename(
            title="Cargar misión JSON",
            initialdir=_MISSIONS_DIR,
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                raise ValueError("El JSON no tiene un objeto raíz")
            self._apply_mission_dict(d)
            self._set_status(f"Cargado: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Cargar", f"No se pudo cargar JSON.\n\n{e}")

    def _validate_ui(self, show_ok: bool = True) -> bool:
        try:
            _ = self._collect_mission_dict()
        except Exception as e:
            messagebox.showerror("Validación", f"Error leyendo la misión.\n\n{e}")
            return False

        for iid in self.tree.get_children(""):
            vals = self.tree.item(iid, "values")
            try:
                wp = self._row_to_wp(vals)
            except Exception:
                messagebox.showerror("Validación", "Hay un waypoint con valores inválidos.")
                return False

            if wp["action"] not in WP_ACTIONS:
                messagebox.showerror("Validación", f"Acción inválida en WP {wp['idx']}: {wp['action']}")
                return False
            if wp["sensor"] not in SENSORS:
                messagebox.showerror("Validación", f"Sensor inválido en WP {wp['idx']}: {wp['sensor']}")
                return False
            if wp["wait_s"] < 0:
                messagebox.showerror("Validación", f"wait_s no puede ser negativo (WP {wp['idx']}).")
                return False

            if wp["action"] == "photo" and wp["mode"] not in PHOTO_MODES:
                messagebox.showerror(
                    "Validación",
                    f"Modo de foto inválido en WP {wp['idx']} (usa: {', '.join(PHOTO_MODES)})",
                )
                return False
            if wp["action"] == "video_start" and wp["mode"] not in VIDEO_QUALITIES:
                messagebox.showerror(
                    "Validación",
                    f"Calidad de video inválida en WP {wp['idx']} (usa: {', '.join(VIDEO_QUALITIES)})",
                )
                return False

        if show_ok:
            messagebox.showinfo("Validación", "✅ Misión válida")
        return True

    def _default_metadata_basename(self) -> str:

        mission = (self.var_name.get().strip() or "mission").replace(" ", "_")
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"genai_{mission}_{ts}"

    def _clear_metadata(self):
        self.meta_store.clear()
        self._set_status("Metadatos limpiados")

    def _export_metadata_dialog(self):
        if not self.meta_store.records:
            messagebox.showinfo("Metadatos", "Aún no hay fotos registradas para exportar.")
            return

        base = self._default_metadata_basename()
        path = filedialog.asksaveasfilename(
            title="Exportar metadatos de fotos",
            initialdir=self.meta_store.output_dir,

            initialfile=base + ".xlsx",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("CSV (Excel ;)", "*.csv")],
        )
        if not path:
            return
        try:
            self.meta_store.export(path)
            self._set_status(f"Metadatos exportados: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Metadatos", f"No se pudo exportar.\n\n{e}")

    def _prompt_export_after_mission(self):

        if not self.meta_store.records:
            return
        try:
            ok = messagebox.askyesno(
                "Metadatos",
                "La misión generó fotos. ¿Quieres exportar ahora un CSV/Excel con los metadatos?",
            )
            if ok:
                self._export_metadata_dialog()
        except Exception:

            return

    def _get_ros2_client(self):
        if not ROS2_MISSION_AVAILABLE:
            return None
        if self._ros2_client is None:
            try:
                self._ros2_client = Ros2MissionClient(namespace="/anafi")
            except Exception:
                self._ros2_client = None
        return self._ros2_client

    def _ros2_tick(self):
        try:
            client = self._get_ros2_client()
            if client is not None:
                try:
                    client.start()
                    client.spin_once(0.0)
                except Exception:
                    pass
                status = client.get_last_status()
                state = str(status.get("state", "") or "")
                summary = str(status.get("summary", "") or "")
                cur = int(status.get("current_waypoint", 0) or 0)
                total = int(status.get("total_waypoints", 0) or 0)

                if self._ros2_managed or state in {"starting", "running", "stopping"}:
                    if total > 0:
                        msg = f"ROS2 {state}: WP {cur}/{total} - {summary}"
                    else:
                        msg = f"ROS2 {state}: {summary}"
                    self._set_status(msg)

                if state in {"starting", "running", "stopping"}:
                    self.btn_run.configure(state="disabled")
                    self.btn_stop.configure(state="normal")
                elif self._ros2_managed and state in {"completed", "cancelled", "error", "idle"}:
                    self._ros2_managed = False
                    self.btn_run.configure(state="normal")
                    self.btn_stop.configure(state="disabled")
                    if summary:
                        self._set_status(f"ROS2 {state}: {summary}")
        finally:
            self.after(300, self._ros2_tick)

    def _release_gui_drone_ownership(self) -> None:
        try:
            root = self.winfo_toplevel()
        except Exception:
            root = None

        try:
            if root is not None and hasattr(root, "current_page") and getattr(root, "current_page", None) is not None:
                page = getattr(root, "current_page", None)
                if hasattr(page, "on_hide"):
                    page.on_hide()
        except Exception:
            pass

        try:
            if root is not None:
                for page in getattr(root, "pages", {}).values():
                    if hasattr(page, "on_hide"):
                        try:
                            page.on_hide()
                        except Exception:
                            pass
        except Exception:
            pass

        try:
            ctrl = getattr(root, "ros2", None) or self._controller
            if ctrl is not None:
                try:
                    ctrl.stop_ros2_bridge()
                except Exception:
                    pass
                try:
                    ctrl.stop_sensors()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            from sensores import drone_client as _dc
            d = getattr(_dc, "_drone_singleton", None)
            if d is not None:
                try:
                    d.disconnect()
                except Exception:
                    pass
            _dc._drone_singleton = None
        except Exception:
            pass

        try:
            if root is not None:
                d = getattr(root, "drone", None)
                if d is not None:
                    try:
                        d.disconnect()
                    except Exception:
                        pass
                root.drone = None
        except Exception:
            pass

        self._drone = None
        time.sleep(3.0)

    def _try_run_via_ros2_manager(self) -> bool:
        client = self._get_ros2_client()
        if client is None:
            return False
        try:
            client.start()
            if not client.manager_available(timeout_sec=0.6):
                return False
        except Exception:
            return False

        self._set_status("Liberando conexión GUI…")
        self._release_gui_drone_ownership()

        mission = self._collect_mission_dict()
        ok, msg, mission_file = client.start_mission(mission)
        if not ok:
            self._set_status(f"Mission manager no disponible: {msg}")
            return False

        self._ros2_managed = True
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._set_status(f"Misión enviada al manager: {os.path.basename(mission_file)}")
        return True

    def _run_async(self):
        if self._runner_thread and self._runner_thread.is_alive():
            return
        if not self._validate_ui(show_ok=False):
            return
        if self._try_run_via_ros2_manager():
            return
        self._cancel.clear()
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._set_status("Ejecutando localmente…")
        self._runner_thread = threading.Thread(target=self._run_mission, daemon=True)
        self._runner_thread.start()

    def _stop_run(self):
        if self._ros2_managed:
            client = self._get_ros2_client()
            if client is not None:
                ok, msg = client.stop_mission()
                self._set_status(msg if ok else f"No se pudo detener: {msg}")
                return
        self._cancel.set()
        self._set_status("Deteniendo…")

    def _finish_run_ui(self, msg: str):
        def _ui():
            self.btn_run.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self._set_status(msg)
        self.after(0, _ui)

    def _ensure_drone_for_control(self):

        if self._drone is not None:
            return self._drone

        try:
            root = self.winfo_toplevel()
            d = getattr(root, "drone", None)
            if d is not None:
                self._drone = d
                return d
        except Exception:
            pass

        try:
            root = self.winfo_toplevel()
            sp = getattr(root, "pages", {}).get("sensores")
            if sp is not None and hasattr(sp, "sensor_stream"):
                ss = sp.sensor_stream
                client = getattr(ss, "client", None)
                if client is not None and getattr(client, "connected", False):
                    d = getattr(client, "drone", None) or getattr(client, "_drone", None)
                    if d is not None:
                        self._drone = d
                        return d
        except Exception:
            pass

        try:
            from sensores.drone_client import get_connected
            d = get_connected(DRONE_IP)
            self._drone = d
            return d
        except Exception:
            return None

    def _get_drone(self):
        return self._ensure_drone_for_control()

    def _set_stream_mode(self, drone, sensor: str):
        try:
            from olympe.messages.thermal import set_mode
            if sensor == "rgb":
                drone(set_mode("standard")).wait(2)
            else:
                drone(set_mode("blended")).wait(2)
        except Exception:
            pass

    def _capture_rgb_snapshot(self) -> str:
        drone = self._ensure_drone_for_control()
        if drone is None:
            raise RuntimeError("No hay conexión Olympe con el dron")

        from sensores.rgb_capture import take_rgb_photo
        return take_rgb_photo(drone=drone, capture_root=_MEDIA_ROOT)

    def _video_start(self, sensor: str, quality: str) -> str:
        if self._video_proc is not None:
            return "(ya grabando)"

        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = _RGB_VIDEOS_DIR if sensor == "rgb" else os.path.join(_MEDIA_ROOT, "thermal", "videos")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{sensor}_{ts}.mp4")

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            RTSP_TRANSPORT,
            "-i",
            DRONE_RTSP_URL,
            "-c:v",
            "copy",
            "-an",
            out_path,
        ]

        _ = quality

        self._video_proc = subprocess.Popen(cmd, preexec_fn=os.setsid if hasattr(os, "setsid") else None)
        return out_path

    def _video_stop(self):
        if self._video_proc is None:
            return
        try:
            if hasattr(os, "killpg") and hasattr(os, "getpgid"):
                os.killpg(os.getpgid(self._video_proc.pid), signal.SIGTERM)
            else:
                self._video_proc.terminate()
            self._video_proc.wait(timeout=5)
        except Exception:
            pass
        finally:
            self._video_proc = None

    def _resolve_speed_cmd(self):
        if self._speed_cmd_checked:
            return
        self._speed_cmd_checked = True

        import importlib

        candidates = [
            ("olympe.messages.ardrone3.SpeedSettings", "MaxHorizontalSpeed"),
            ("olympe.messages.ardrone3.PilotingSettings", "MaxHorizontalSpeed"),
        ]

        for mod_name, cls_name in candidates:
            try:
                mod = importlib.import_module(mod_name)
                self._speed_cmd_cls = getattr(mod, cls_name)
                return
            except Exception:
                continue

    def _try_set_gimbal_pitch(self, drone, pitch_deg: float):
        try:
            from olympe.messages.gimbal import set_target
            from olympe.enums.gimbal import control_mode, frame_of_reference

            exp = drone(
                set_target(
                    gimbal_id=0,
                    control_mode=control_mode.position,
                    yaw_frame_of_reference=frame_of_reference.absolute,
                    yaw=0.0,
                    pitch_frame_of_reference=frame_of_reference.absolute,
                    pitch=float(pitch_deg),
                    roll_frame_of_reference=frame_of_reference.absolute,
                    roll=0.0,
                )
            )
            exp.wait(5)
        except Exception:

            return

    def _move_by(self, drone, dx: float, dy: float, dz: float, dyaw_rad: float, speed_mps: float | None):

        if speed_mps is not None:
            try:
                from olympe.messages.move import extended_move_by

                max_h = float(speed_mps)

                max_v = max(0.1, min(2.0, float(speed_mps)))

                max_yaw = 60.0

                return drone(
                    extended_move_by(
                        float(dx),
                        float(dy),
                        float(dz),
                        float(dyaw_rad),
                        max_h,
                        max_v,
                        max_yaw,
                    )
                )
            except Exception:

                pass

        from olympe.messages.ardrone3.Piloting import moveBy
        return drone(moveBy(float(dx), float(dy), float(dz), float(dyaw_rad)))

    def _run_mission(self):
        m = self._collect_mission_dict()
        try:
            from anafi_suite_core.mission_executor import MissionExecutor
        except Exception as e:
            self._finish_run_ui("Error")
            self.after(0, lambda: messagebox.showerror("Misión", f"No se pudo cargar el ejecutor compartido.\n\n{e}"))
            return

        executor = MissionExecutor(drone_ip=DRONE_IP, media_root=_MEDIA_ROOT, meta_store=self.meta_store)

        def ui(msg: str):
            self.after(0, lambda m=msg: self._set_status(m))

        result = executor.run(m, cancel_event=self._cancel, on_status=ui)

        if self.meta_store.records:
            self.after(0, self._prompt_export_after_mission)

        if result.cancelled:
            self._finish_run_ui("Cancelado")
            return
        if result.ok:
            self._finish_run_ui("Completado")
            return

        err = result.error or "Error desconocido"
        self._finish_run_ui("Error")
        self.after(0, lambda: messagebox.showerror("Misión", "Fallo ejecutando misión:\n\n" + err))

