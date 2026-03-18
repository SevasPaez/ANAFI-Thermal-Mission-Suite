# interfaz/pages/gallery_thermal_page.py
"""Página de Galería para media térmica.

Además de mostrar miniaturas, al abrir una imagen térmica (.JPG) intenta
extraer la matriz radiométrica 16-bit embebida y permite leer el valor por
píxel con el mouse (hover).

Matrices guardadas automáticamente en: MEDIA_ROOT/thermal/matrices
  - <foto>_raw.npy
  - <foto>_tempC.npy (si se logra convertir)
  - <foto>_meta.json
"""

from __future__ import annotations

import os
import platform
import sys
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np
from PIL import Image, ImageTk

from .gallery_page import GalleryPage


class ThermalGalleryPage(GalleryPage):
    def __init__(self, parent, media_dir=None):
        # Import lazy para evitar ciclos al importar config
        try:
            from config import MEDIA_ROOT  # type: ignore

            base = MEDIA_ROOT
        except Exception:
            base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media")

        thermal_dir = media_dir or os.path.join(base, "thermal")
        super().__init__(parent, media_dir=thermal_dir)

    # -------- Override: abrir imagen con viewer térmico --------
    def _open_image(self, path: str):
        """Abre un visor térmico con lectura por píxel."""
        # --- Resolver archivos "mapeados" ---
        # En esta UI generamos archivos *_mapped.png (RGB) para visualización.
        # Esos NO contienen radiometría. Si el usuario abre uno, intentamos
        # localizar el JPG original correspondiente automáticamente.
        src_path = path  # archivo real para extraer radiometría
        disp_path = path  # archivo a mostrar (si existe uno mapeado, lo preferimos)

        norm = path.replace("\\", os.sep)
        base_name = os.path.basename(norm).lower()
        if base_name.endswith("_mapped.png") or f"{os.sep}mapped{os.sep}" in norm:
            guess = norm
            guess = guess.replace(f"{os.sep}mapped{os.sep}", os.sep)
            if guess.lower().endswith("_mapped.png"):
                guess = guess[: -len("_mapped.png")]
            # probar extensiones típicas
            for ext in (".JPG", ".jpg", ".JPEG", ".jpeg"):
                cand = guess + ext
                if os.path.exists(cand):
                    src_path = cand
                    break

        # Si abrimos el JPG original, pero existe un *_mapped.png, úsalo para mostrar.
        if src_path.lower().endswith((".jpg", ".jpeg")):
            stem = os.path.splitext(os.path.basename(src_path))[0]
            mapped = os.path.join(os.path.dirname(src_path), "mapped", f"{stem}_mapped.png")
            if os.path.exists(mapped):
                disp_path = mapped

        # Detectar sidecar (a veces la radiometría viene en un archivo .DNG que en realidad es un JPEG contenedor)
        sidecar_path = None
        if src_path.lower().endswith((".jpg", ".jpeg")):
            stem = os.path.splitext(src_path)[0]
            for ext in (".DNG", ".dng"):
                cand = stem + ext
                if os.path.exists(cand):
                    sidecar_path = cand
                    break

        try:
            from sensores.thermal_matrix import get_or_create_thermal_matrices
            from sensores.thermal_map import map_and_save

            mats = get_or_create_thermal_matrices(src_path)
            try:
                disp_path = map_and_save(src_path)
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror(
                "Matriz térmica",
                "No se pudo extraer la matriz radiométrica.\n\n"
                "Sugerencias:\n"
                "- Abre el .JPG original descargado del dron (no un PNG mapeado).\n"
                "- Asegúrate de que el archivo no esté corrupto.\n\n"
                f"Archivo seleccionado: {os.path.basename(path)}\n"
                f"Fuente radiométrica (intentada): {os.path.basename(src_path)}\n"
                f"Sidecar (.DNG) detectado: {os.path.basename(sidecar_path) if sidecar_path else 'No'}\n\n"
                f"Detalle: {e}",
            )
            # Fallback: abrir imagen normal
            return super()._open_image(path)

        # Imagen visual (para mostrar al usuario): usamos el JPG
        img = Image.open(disp_path)
        img.load()

        top = tk.Toplevel(self)
        top.title(os.path.basename(path))
        top.geometry("980x760")

        header = ttk.Frame(top)
        header.pack(side="top", fill="x", padx=10, pady=8)

        title = ttk.Label(
            header,
            text=(
                f"Visual: {os.path.basename(disp_path)}   |   "
                f"Radiometría: {os.path.basename(mats.meta.get('source_path', src_path))}   |   "
                f"Matriz: {mats.raw.shape[1]}×{mats.raw.shape[0]} ({mats.raw.dtype})"
            ),
        )
        title.pack(side="left")

        method_txt = mats.method
        tmethod = mats.meta.get('temp_method', 'n/a')
        valid_ratio = mats.meta.get('temp_valid_ratio')
        if mats.temp_c is not None:
            method_txt += f"  |  temp={tmethod}"
            if valid_ratio is not None:
                method_txt += f"  |  válidos={100.0*float(valid_ratio):.1f}%"
        else:
            method_txt += "  (TempC no disponible; mostrando RAW)"

        ttk.Label(header, text=method_txt).pack(side="right")

        # Info de pixel
        info = ttk.Label(top, text="Mueve el mouse sobre la imagen…")
        info.pack(side="top", anchor="w", padx=10)

        # Botones
        btns = ttk.Frame(top)
        btns.pack(side="top", fill="x", padx=10, pady=(6, 0))

        def _open_matrices_folder():
            folder = os.path.dirname(mats.raw_path)
            try:
                sysname = platform.system().lower()
                if sysname.startswith("win"):
                    os.startfile(folder)  # type: ignore
                elif sysname == "darwin":
                    os.system(f'open "{folder}"')
                else:
                    os.system(f'xdg-open "{folder}"')
            except Exception:
                messagebox.showinfo("Carpeta matrices", folder)

        ttk.Button(btns, text="Abrir carpeta matrices", command=_open_matrices_folder).pack(
            side="left", padx=(0, 8)
        )
        ttk.Label(btns, text=f"RAW: {os.path.basename(mats.raw_path)}").pack(side="left")
        if mats.temp_path:
            ttk.Label(btns, text=f" | TempC: {os.path.basename(mats.temp_path)}").pack(side="left")

        # Canvas de imagen (scrollable)
        wrap = ttk.Frame(top)
        wrap.pack(fill="both", expand=True, padx=10, pady=10)

        canvas = tk.Canvas(wrap, highlightthickness=0)
        vs = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        hs = ttk.Scrollbar(wrap, orient="horizontal", command=canvas.xview)
        canvas.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        # Reescalar imagen visual para que quepa razonablemente
        max_w, max_h = 920, 640
        disp = img.copy()
        disp.thumbnail((max_w, max_h))
        disp_w, disp_h = disp.size

        imtk = ImageTk.PhotoImage(disp)
        img_id = canvas.create_image(0, 0, anchor="nw", image=imtk)
        canvas.image = imtk
        canvas.config(scrollregion=(0, 0, disp_w, disp_h))

        raw = mats.raw
        temp = mats.temp_c
        h_raw, w_raw = raw.shape

        def _on_move(ev):
            # Coordenadas dentro del canvas
            cx = int(canvas.canvasx(ev.x))
            cy = int(canvas.canvasy(ev.y))
            if cx < 0 or cy < 0 or cx >= disp_w or cy >= disp_h:
                return
            # Mapear a coordenadas de la matriz térmica
            x = int(cx * w_raw / disp_w)
            y = int(cy * h_raw / disp_h)
            if x < 0 or y < 0 or x >= w_raw or y >= h_raw:
                return

            v_raw = int(raw[y, x])
            if temp is not None:
                v_c = float(temp[y, x])
                if np.isfinite(v_c):
                    info.configure(text=f"x={x}  y={y}   RAW={v_raw}   Temp≈{v_c:.2f} °C")
                else:
                    info.configure(text=f"x={x}  y={y}   RAW={v_raw}   Temp: inválida")
            else:
                info.configure(text=f"x={x}  y={y}   RAW={v_raw}   Temp: N/A")

        canvas.bind("<Motion>", _on_move)

        # Atajo: doble click abre el archivo original con el sistema
        def _open_external(_ev=None):
            abspath = os.path.abspath(path)
            try:
                sysname = platform.system().lower()
                if sysname.startswith("win"):
                    os.startfile(abspath)  # type: ignore
                elif sysname == "darwin":
                    os.system(f'open "{abspath}"')
                else:
                    os.system(f'xdg-open "{abspath}"')
            except Exception:
                messagebox.showinfo("Archivo", abspath)

        canvas.bind("<Double-Button-1>", _open_external)
