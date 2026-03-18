# interfaz/pages/stream_page.py
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import cv2 as cv
from PIL import Image, ImageTk

from config import DRONE_RTSP_URL, RTSP_TRANSPORT, RTSP_FPS_HINT

from sensores.rstp_streaming import RstpThreaded
from sensores.drone_client import get_connected

# ROS2 (opcional)
from ros2_bridge import ROS2_AVAILABLE


# Paso base para el gimbal (grados)
_GIMBAL_STEP = 5
_GIMBAL_MIN = -90
_GIMBAL_MAX = 90


class StreamPage(tk.Frame):
    """Página Stream.

    Objetivo:
    - Mostrar el stream RTSP (RGB) para piloto / framing.
    - Permitir mover el gimbal (pitch).
    - Dar visibilidad a ROS2 (telemetría/autonomía) con un acceso directo.
    """

    def __init__(self, parent, drone=None):
        super().__init__(parent, bg="#161b22")

        self._running = False
        self._rtsp: RstpThreaded | None = None
        self._last_frame_bgr = None
        self._gimbal_pitch = 0.0
        self._drone = drone  # opcional

        # --- Header ---
        header = tk.Frame(self, bg="#161b22")
        header.pack(fill="x", padx=12, pady=(10, 0))

        tk.Label(
            header,
            text="Stream (RGB)",
            fg="white",
            bg="#161b22",
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left")

        # ROS2 badge + acceso directo
        ros2_text = "ROS2: Disponible" if ROS2_AVAILABLE else "ROS2: No disponible"
        self._ros2_lbl = tk.Label(header, text=ros2_text, fg="#9da7b3", bg="#161b22")
        self._ros2_lbl.pack(side="right")

        self._btn_ros2 = ttk.Button(header, text="Abrir Autonomía ROS2", command=self._open_ros2_page)
        self._btn_ros2.pack(side="right", padx=(0, 10))

        # --- Video ---
        self.video_panel = tk.Label(self, bg="#0d1117")
        self.video_panel.pack(padx=12, pady=10)

        # --- Controls ---
        controls = tk.Frame(self, bg="#161b22")
        controls.pack(padx=12, pady=(0, 10))

        # Fila 1: stream
        self.btn_start = ttk.Button(controls, text="▶ Iniciar stream", command=self._start_stream)
        self.btn_stop = ttk.Button(controls, text="■ Detener stream", command=self._stop_stream, state="disabled")
        self.btn_start.grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        self.btn_stop.grid(row=0, column=1, padx=4, pady=4, sticky="ew")

        # Fila 2: gimbal
        self.btn_gup = ttk.Button(controls, text="Gimbal ↑", command=lambda: self._nudge_gimbal(+_GIMBAL_STEP))
        self.btn_gdown = ttk.Button(controls, text="Gimbal ↓", command=lambda: self._nudge_gimbal(-_GIMBAL_STEP))
        self.lbl_g = ttk.Label(controls, text="Pitch: 0°")
        self.btn_gup.grid(row=1, column=0, padx=4, pady=4, sticky="ew")
        self.btn_gdown.grid(row=1, column=1, padx=4, pady=4, sticky="ew")
        self.lbl_g.grid(row=1, column=2, padx=6, pady=4, sticky="w")

        self.status = tk.Label(self, text="", fg="#9da7b3", bg="#161b22")
        self.status.pack(pady=(0, 10))

        # Ajuste de tamaño de columnas
        for c in range(3):
            controls.grid_columnconfigure(c, weight=1)

    # --------- AppShell helpers ---------

    def _open_ros2_page(self):
        root = self.winfo_toplevel()
        if hasattr(root, "show_autonomy"):
            try:
                root.show_autonomy()
            except Exception:
                pass

    def set_drone(self, drone):
        self._drone = drone

    def on_hide(self):
        # Al navegar fuera, apagamos el stream para liberar RTSP/CPU.
        self._stop_stream()

    # --------- Drone helpers ---------

    def _ensure_drone(self):
        if self._drone is not None:
            return self._drone
        self._drone = get_connected()
        return self._drone

    # --------- Stream ---------

    def _start_stream(self):
        if self._running:
            return
        self._rtsp = RstpThreaded(DRONE_RTSP_URL, transport=RTSP_TRANSPORT, fps_hint=RTSP_FPS_HINT)
        self._rtsp.start()
        self._running = True
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.status.configure(text="📡 Stream iniciado")
        self._loop_stream()

    def _loop_stream(self):
        if not self._running or self._rtsp is None:
            return
        frame = self._rtsp.read_latest()
        if frame is not None:
            self._last_frame_bgr = frame
            rgb = cv.cvtColor(frame, cv.COLOR_BGR2RGB)
            imgtk = ImageTk.PhotoImage(Image.fromarray(rgb))
            self.video_panel.configure(image=imgtk)
            self.video_panel.image = imgtk
        self.after(int(1000 / max(1, RTSP_FPS_HINT)), self._loop_stream)

    def _stop_stream(self):
        if not self._running and self._rtsp is None:
            return
        self._running = False
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        try:
            if self._rtsp is not None:
                self._rtsp.stop()
        finally:
            self._rtsp = None
            self.video_panel.configure(image=None)
            self.video_panel.image = None
            self.status.configure(text="")

    # --------- Gimbal ---------

    def _nudge_gimbal(self, delta_deg: float):
        new_pitch = max(_GIMBAL_MIN, min(_GIMBAL_MAX, self._gimbal_pitch + float(delta_deg)))
        self._set_gimbal_pitch(new_pitch)

    def _set_gimbal_pitch(self, pitch_deg: float):
        self._gimbal_pitch = float(pitch_deg)
        self.lbl_g.configure(text=f"Pitch: {int(round(self._gimbal_pitch))}°")
        try:
            d = self._ensure_drone()
            from olympe.messages.gimbal import set_target  # type: ignore

            d(
                set_target(
                    gimbal_id=0,
                    control_mode="position",
                    yaw_frame_of_reference="none",
                    yaw=0.0,
                    pitch_frame_of_reference="absolute",
                    pitch=self._gimbal_pitch,
                    roll_frame_of_reference="none",
                    roll=0.0,
                )
            ).wait(2)
        except Exception:
            # No bloquear la UI si falla por firmware / no hay dron conectado
            pass
