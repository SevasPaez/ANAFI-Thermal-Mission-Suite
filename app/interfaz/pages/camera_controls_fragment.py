import tkinter as tk
from tkinter import ttk, messagebox

class CameraControlsFragment(ttk.Frame):
    def __init__(self, parent, camera_ctrl=None, gimbal_ctrl=None):
        super().__init__(parent)
        self.camera = camera_ctrl
        self.gimbal = gimbal_ctrl

        bar = ttk.Frame(self)
        bar.pack(side="top", fill="x", pady=(0,6))

        ttk.Button(bar, text="Foto", command=self._take_photo).pack(side="left", padx=3)
        ttk.Button(bar, text="Iniciar video", command=self._start_rec).pack(side="left", padx=3)
        ttk.Button(bar, text="Detener video", command=self._stop_rec).pack(side="left", padx=3)

        g = ttk.Labelframe(self, text="Gimbal (grados)")
        g.pack(side="top", fill="x", pady=6)

        self.pitch = tk.DoubleVar(value=0.0)
        self.yaw = tk.DoubleVar(value=0.0)
        self.roll = tk.DoubleVar(value=0.0)

        row = ttk.Frame(g); row.pack(fill="x", pady=3)
        ttk.Label(row, text="Pitch").pack(side="left"); ttk.Entry(row, textvariable=self.pitch, width=8).pack(side="left", padx=4)
        row = ttk.Frame(g); row.pack(fill="x", pady=3)
        ttk.Label(row, text="Yaw").pack(side="left"); ttk.Entry(row, textvariable=self.yaw, width=8).pack(side="left", padx=28)
        row = ttk.Frame(g); row.pack(fill="x", pady=3)
        ttk.Label(row, text="Roll").pack(side="left"); ttk.Entry(row, textvariable=self.roll, width=8).pack(side="left", padx=28)

        row = ttk.Frame(g); row.pack(fill="x", pady=6)
        ttk.Button(row, text="Mover", command=self._apply_gimbal).pack(side="left", padx=3)
        ttk.Button(row, text="Centrar", command=self._center_gimbal).pack(side="left", padx=3)

    def _take_photo(self):
        if self.camera is None:
            messagebox.showerror("Cámara", "CameraControl no configurado")
            return
        self.camera.take_photo_async(lambda path: messagebox.showinfo("Foto", f"Foto: {path}" if path else "No se pudo tomar la foto"))

    def _start_rec(self):
        if self.camera is None:
            messagebox.showerror("Cámara", "CameraControl no configurado")
            return
        self.camera.start_recording_async(lambda ok: messagebox.showinfo("Video", "Grabando..." if ok else "No se pudo iniciar la grabación"))

    def _stop_rec(self):
        if self.camera is None:
            messagebox.showerror("Cámara", "CameraControl no configurado")
            return
        self.camera.stop_recording_async(lambda ok: messagebox.showinfo("Video", "Grabación detenida" if ok else "No se pudo detener"))

    def _apply_gimbal(self):
        if self.gimbal is None:
            messagebox.showerror("Gimbal", "GimbalControl no configurado")
            return
        self.gimbal.set_angles(pitch=self.pitch.get(), yaw=self.yaw.get(), roll=self.roll.get(), absolute=True)

    def _center_gimbal(self):
        if self.gimbal is None:
            messagebox.showerror("Gimbal", "GimbalControl no configurado")
            return
        self.gimbal.center()
