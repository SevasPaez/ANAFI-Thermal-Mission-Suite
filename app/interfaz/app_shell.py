# interfaz/app_shell.py
from __future__ import annotations

from config import DRONE_IP, MEDIA_ROOT

import os
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Optional

# Páginas
from .pages.sensores_page import SensoresPage
from .pages.stream_page import StreamPage
from .pages.gallery_page import GalleryPage
from .pages.gallery_thermal_page import ThermalGalleryPage
from .pages.autonomy_page import AutonomyPage
from .pages.flight_mission_page import FlightMissionPage
from .pages.errors_page import ErrorsPage

from .ros2_controller import Ros2Controller

# Olympe (opcional)
HAVE_OLYMPE = False
try:
    import olympe  # type: ignore
    HAVE_OLYMPE = True
except Exception:
    HAVE_OLYMPE = False


class AppShell(tk.Tk):
    """Shell principal de la UI.

    Cambios principales (v4_stream_ros2_focus → v4_stream_ros2_focus_v2):
    - Widget de estado en la sidebar (Sensores / ROS2 Bridge / Autonomía runner).
    - Start/Stop de Sensores y ROS2 Bridge desde la sidebar.
    - Página central "Autonomía ROS2" (bridge + runner + logs).
    - Estado persistente al navegar.
    """

    def __init__(
        self,
        title: str,
        geom: str,
        connect_drone: bool = True,
        anafi_host: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.title(title)
        self.geometry(geom)
        self.minsize(1000, 650)

        # Controlador global ROS2 (estado persistente)
        self.ros2 = Ros2Controller(ip=DRONE_IP, namespace="/anafi", publish_hz=10.0)

        # Estado drone (si decides conectar desde AppShell)
        self.drone = None
        self._connect_thread: Optional[threading.Thread] = None
        self._anafi_host = anafi_host or DRONE_IP

        # Layout principal
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar y contenido
        self.sidebar = tk.Frame(self, bg="#101418")
        self.sidebar.grid(row=0, column=0, sticky="ns")

        # Sidebar scrollable (por si la ventana es baja y no caben todos los botones)
        self.sidebar_canvas = tk.Canvas(self.sidebar, bg="#101418", highlightthickness=0, bd=0)
        self.sidebar_scroll = ttk.Scrollbar(self.sidebar, orient="vertical", command=self.sidebar_canvas.yview)
        self.sidebar_canvas.configure(yscrollcommand=self.sidebar_scroll.set)
        self.sidebar_scroll.pack(side="right", fill="y")
        self.sidebar_canvas.pack(side="left", fill="both", expand=True)

        self.sidebar_body = tk.Frame(self.sidebar_canvas, bg="#101418")
        self._sidebar_window = self.sidebar_canvas.create_window((0, 0), window=self.sidebar_body, anchor="nw")

        def _sidebar_sync(_event=None):
            try:
                self.sidebar_canvas.configure(scrollregion=self.sidebar_canvas.bbox("all"))
                self.sidebar_canvas.itemconfigure(self._sidebar_window, width=self.sidebar_canvas.winfo_width())
            except Exception:
                pass

        self.sidebar_body.bind("<Configure>", _sidebar_sync)
        self.sidebar_canvas.bind("<Configure>", _sidebar_sync)

        # Mousewheel solo cuando el cursor está dentro de la sidebar
        def _on_wheel(event):
            try:
                if getattr(event, "num", None) == 5:
                    self.sidebar_canvas.yview_scroll(1, "units")
                elif getattr(event, "num", None) == 4:
                    self.sidebar_canvas.yview_scroll(-1, "units")
                else:
                    delta = int(-1 * (event.delta / 120))
                    self.sidebar_canvas.yview_scroll(delta, "units")
            except Exception:
                pass

        def _bind_wheel(_e):
            self.sidebar_canvas.bind_all("<MouseWheel>", _on_wheel)
            self.sidebar_canvas.bind_all("<Button-4>", _on_wheel)
            self.sidebar_canvas.bind_all("<Button-5>", _on_wheel)

        def _unbind_wheel(_e):
            self.sidebar_canvas.unbind_all("<MouseWheel>")
            self.sidebar_canvas.unbind_all("<Button-4>")
            self.sidebar_canvas.unbind_all("<Button-5>")

        self.sidebar_canvas.bind("<Enter>", _bind_wheel)
        self.sidebar_canvas.bind("<Leave>", _unbind_wheel)

        sb = self.sidebar_body
        self.content = tk.Frame(self, bg="#161b22")
        self.content.grid(row=0, column=1, sticky="nsew")

        tk.Label(
            sb,
            text="  Anafi UI",
            fg="white",
            bg="#101418",
            font=("Segoe UI", 14, "bold"),
            pady=16,
        ).pack(fill="x")

        btn_style = {
            "fg": "white",
            "bg": "#101418",
            "activebackground": "#22303c",
            "bd": 0,
            "highlightthickness": 0,
            "anchor": "w",
            "padx": 16,
        }

        # ---- Widget de estado (sidebar) ----
        status_box = tk.LabelFrame(sb, text="Estado", bg="#101418", fg="#c9d1d9")
        status_box.pack(fill="x", padx=10, pady=(0, 10))

        self._sb_var_sensors = tk.StringVar(value="Sensores: —")
        self._sb_var_bridge = tk.StringVar(value="ROS2 Bridge: —")
        self._sb_var_runner = tk.StringVar(value="Runner: —")
        self._sb_var_state = tk.StringVar(value="Dron: —")
        self._sb_var_msgs = tk.StringVar(value="Msgs: 0")

        tk.Label(status_box, textvariable=self._sb_var_sensors, bg="#101418", fg="#c9d1d9", anchor="w").pack(fill="x", padx=8, pady=(6, 0))
        tk.Label(status_box, textvariable=self._sb_var_bridge, bg="#101418", fg="#c9d1d9", anchor="w").pack(fill="x", padx=8)
        tk.Label(status_box, textvariable=self._sb_var_runner, bg="#101418", fg="#c9d1d9", anchor="w").pack(fill="x", padx=8)
        tk.Label(status_box, textvariable=self._sb_var_state, bg="#101418", fg="#c9d1d9", anchor="w").pack(fill="x", padx=8)
        tk.Label(status_box, textvariable=self._sb_var_msgs, bg="#101418", fg="#c9d1d9", anchor="w").pack(fill="x", padx=8, pady=(0, 6))

        btn_row = tk.Frame(status_box, bg="#101418")
        btn_row.pack(fill="x", padx=8, pady=(0, 8))

        self._sb_btn_sensors = tk.Button(btn_row, text="Sensores", command=self._toggle_sensors_sidebar, **btn_style)
        self._sb_btn_bridge = tk.Button(btn_row, text="ROS2 Bridge", command=self._toggle_bridge_sidebar, **btn_style)
        self._sb_btn_sensors.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._sb_btn_bridge.pack(side="left", fill="x", expand=True, padx=(4, 0))

        # ---- Navegación ----
        tk.Button(sb, text="Sensores", command=self.show_sensores, **btn_style).pack(fill="x", pady=4)
        tk.Button(sb, text="Stream", command=self.show_stream, **btn_style).pack(fill="x", pady=4)
        tk.Button(sb, text="Galería RGB", command=self.show_gallery_rgb, **btn_style).pack(fill="x", pady=4)
        tk.Button(sb, text="Galería Thermal", command=self.show_gallery_thermal, **btn_style).pack(fill="x", pady=4)
        tk.Button(sb, text="Errores", command=self.show_errors, **btn_style).pack(fill="x", pady=4)
        tk.Button(sb, text="Autonomía ROS2", command=self.show_autonomy, **btn_style).pack(fill="x", pady=4)
        tk.Button(sb, text="Misión de vuelo", command=self.show_mission, **btn_style).pack(fill="x", pady=4)

        # Barra de estado (pie de página)
        self.status_var = tk.StringVar(value="Listo")
        status_bar = ttk.Frame(self.content)
        status_bar.pack(side="bottom", fill="x")
        ttk.Label(status_bar, textvariable=self.status_var, anchor="w").pack(side="left", padx=8, pady=4)

        # Registro de páginas
        self.pages: Dict[str, tk.Frame] = {}
        self.current_page: Optional[tk.Frame] = None

        # Eventos
        self.bind("<<MediaUpdated>>", self._refresh_gallery_if_open)

        # Cierre limpio
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Conexión al dron (opcional) — por defecto main.py usa connect_drone=False
        if connect_drone and HAVE_OLYMPE:
            self._connect_drone_async()
        elif connect_drone and not HAVE_OLYMPE:
            self._set_status("Olympe no disponible. Inicia el entorno de Parrot/Olympe.")
        else:
            self._set_status("Modo sin conexión a dron (recomendado para ROS2).")

        # Refresh del widget sidebar
        self.after(300, self._sidebar_tick)

        # Página inicial
        self.show_sensores()

    # --------------------- Utilidades internas ---------------------

    def _set_status(self, text: str) -> None:
        try:
            self.status_var.set(text)
        except Exception:
            pass

    def _safe_call(self, obj: object, method: str) -> None:
        if hasattr(obj, method):
            try:
                getattr(obj, method)()
            except Exception:
                pass

    def _best_drone(self, d):
        if d is not None:
            return d
        sp = self.pages.get("sensores")
        if sp is not None and hasattr(sp, "_drone") and getattr(sp, "_drone") is not None:
            return getattr(sp, "_drone")
        return None

    # --------------------- Sidebar widget ---------------------

    def _toggle_sensors_sidebar(self) -> None:
        ok = self.ros2.toggle_sensors()
        if not ok:
            st = self.ros2.get_status()
            if st.last_error:
                self._set_status(st.last_error)

    def _toggle_bridge_sidebar(self) -> None:
        ok = self.ros2.toggle_ros2_bridge()
        if not ok:
            st = self.ros2.get_status()
            if st.last_error:
                self._set_status(st.last_error)

    def _sidebar_tick(self) -> None:
        st = self.ros2.get_status()
        self._sb_var_sensors.set(f"Sensores: {'ON' if st.sensors_connected else 'OFF'}")
        self._sb_var_bridge.set(f"ROS2 Bridge: {'ON' if st.ros2_bridge_running else 'OFF'}")
        self._sb_var_runner.set(f"Runner: {'ON' if st.autonomy_running else 'OFF'}")
        self._sb_var_state.set(f"Dron: {st.ros2_last_state or '—'}")
        self._sb_var_msgs.set(f"Msgs: {st.ros2_published_msgs}")

        # Textos de botones
        self._sb_btn_sensors.configure(text=("Desconectar" if st.sensors_connected else "Conectar"))
        self._sb_btn_bridge.configure(text=("Detener ROS2" if st.ros2_bridge_running else "Iniciar ROS2"))

        self.after(300, self._sidebar_tick)

    # --------------------- Conexión Olympe (opcional) ---------------------

    def _connect_drone_async(self) -> None:
        if self._connect_thread and self._connect_thread.is_alive():
            return

        self._set_status(f"Conectando a Anafi ({self._anafi_host})…")
        hosts = [self._anafi_host]
        for fallback in ("192.168.53.1", "192.168.42.1"):
            if fallback not in hosts:
                hosts.append(fallback)

        def _worker():
            d = None
            for host in hosts:
                try:
                    d = olympe.Drone(host)  # type: ignore
                    ok = d.connect()
                    if ok:
                        self.after(0, self._on_drone_connected, d, host)
                        return
                    else:
                        try:
                            d.disconnect()
                        except Exception:
                            pass
                except Exception:
                    d = None
            self.after(0, self._on_drone_failed)

        self._connect_thread = threading.Thread(target=_worker, daemon=True)
        self._connect_thread.start()

    def _on_drone_connected(self, d, host: str) -> None:
        self.drone = d
        self._set_status(f"Conectado a Anafi ({host})")

        for page in self.pages.values():
            if hasattr(page, "set_drone"):
                try:
                    page.set_drone(self.drone)
                except Exception:
                    pass
            self._safe_call(page, "on_drone_ready")

        try:
            self.event_generate("<<DroneReady>>", when="tail")
        except Exception:
            pass

    def _on_drone_failed(self) -> None:
        self.drone = None
        self._set_status("No se pudo conectar al dron. Revisa red / IP.")

    def _disconnect_drone(self) -> None:
        try:
            if self.drone is not None:
                self._set_status("Desconectando dron…")
                self.drone.disconnect()
        except Exception:
            pass
        finally:
            self.drone = None

    # --------------------- Navegación / ciclo de vida ---------------------

    def _show_page(self, name: str, cls_factory: Callable[[tk.Frame, Optional[object]], tk.Frame]) -> None:
        if self.current_page is not None:
            self._safe_call(self.current_page, "on_hide")
            self.current_page.pack_forget()

        if name not in self.pages:
            self.pages[name] = cls_factory(self.content, self.drone)

        self.current_page = self.pages[name]
        self.current_page.pack(fill="both", expand=True)
        self._safe_call(self.current_page, "on_show")

    def _refresh_gallery_if_open(self, *_):
        for key in ("gallery_rgb", "gallery_thermal"):
            gal = self.pages.get(key)
            if gal is not None and hasattr(gal, "refresh"):
                try:
                    gal.refresh()
                except Exception:
                    pass

    # --------------------- Handlers de navegación ---------------------

    def show_sensores(self) -> None:
        self._show_page("sensores", lambda parent, drone: SensoresPage(parent, controller=self.ros2))

    def show_stream(self) -> None:
        self._show_page("stream", lambda parent, drone: StreamPage(parent, drone=self._best_drone(drone)))

    def show_autonomy(self) -> None:
        self._show_page("autonomy", lambda parent, drone: AutonomyPage(parent, controller=self.ros2))

    def show_gallery_rgb(self) -> None:
        rgb_dir = os.path.join(MEDIA_ROOT, "rgb")
        self._show_page("gallery_rgb", lambda parent, drone: GalleryPage(parent, media_dir=rgb_dir))

    def show_gallery_thermal(self) -> None:
        thermal_dir = os.path.join(MEDIA_ROOT, "thermal")
        self._show_page("gallery_thermal", lambda parent, drone: ThermalGalleryPage(parent, media_dir=thermal_dir))

    def show_errors(self) -> None:
        model_path = os.path.join(os.path.dirname(__file__), "assets", "models", "best.pt")
        self._show_page("errors", lambda parent, drone: ErrorsPage(parent, model_path=model_path))

    def show_mission(self) -> None:
        self._show_page("mission", lambda parent, drone: FlightMissionPage(parent, drone=self._best_drone(drone), controller=self.ros2))

    # --------------------- Cierre ---------------------

    def _on_close(self) -> None:
        try:
            if self.current_page is not None:
                self._safe_call(self.current_page, "on_hide")
        except Exception:
            pass

        # Apagar ROS2 + procesos
        try:
            self.ros2.shutdown()
        except Exception:
            pass

        self._disconnect_drone()
        self.destroy()
