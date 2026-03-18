from __future__ import annotations

import os
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import numpy as np
from PIL import Image, ImageTk
import cv2 as cv

BG_ROOT = "#13263a"
BG_PANEL = "#17324c"
BG_CARD = "#0f2234"
FG = "#f3f7fb"
ACCENT = "#4cc9f0"
ACCENT_2 = "#8bd3ff"
WARN = "#ffb703"
DANGER = "#ff6b6b"
MUTED = "#b8c7d9"

class ErrorsPage(tk.Frame):
    def __init__(self, parent, model_path: str | None = None):
        super().__init__(parent, bg=BG_ROOT)

        try:
            from config import MEDIA_ROOT
            self._media_root = MEDIA_ROOT
        except Exception:
            self._media_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media")

        self._thermal_photos = os.path.join(self._media_root, "thermal", "photos")
        self._missions_root = os.path.join(self._thermal_photos, "missions")
        os.makedirs(self._thermal_photos, exist_ok=True)
        os.makedirs(self._missions_root, exist_ok=True)

        self.model_path = tk.StringVar(value=model_path or self._default_model_path())
        self.selected_path = tk.StringVar(value="")
        self.current_mission = tk.StringVar(value="General")
        self.new_mission_name = tk.StringVar(value="")

        self.min_area = tk.StringVar(value="25")
        self.max_area = tk.StringVar(value="0")
        self.blur_ksize = tk.IntVar(value=1)
        self.morph_close = tk.IntVar(value=0)
        self.conf = tk.StringVar(value="0.25")
        self.out_size = tk.StringVar(value="512")

        self.color_space = tk.StringVar(value="RGB")
        self.c1_min = tk.IntVar(value=0)
        self.c2_min = tk.IntVar(value=0)
        self.c3_min = tk.IntVar(value=0)
        self.c1_max = tk.IntVar(value=255)
        self.c2_max = tk.IntVar(value=255)
        self.c3_max = tk.IntVar(value=255)
        self.erode_iter = tk.IntVar(value=0)
        self.dilate_iter = tk.IntVar(value=0)

        self._imgtk = None
        self._preview_base_pil: Image.Image | None = None
        self._preview_visual_pil: Image.Image | None = None
        self._preview_scale = 1.0
        self._preview_offset = (0, 0)
        self._raw_arr: np.ndarray | None = None
        self._temp_arr: np.ndarray | None = None
        self._display_shape: tuple[int, int] | None = None
        self._last_output_dir: str = ""
        self._last_analyzed_source_path: str = ""

        self._build_ui()
        self._refresh_missions()
        self._refresh_list()

    def _default_model_path(self) -> str:
        cand = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models", "obb", "best.pt")
        return cand

    def _build_ui(self):
        header = tk.Frame(self, bg=BG_ROOT)
        header.pack(side="top", fill="x", padx=12, pady=12)
        tk.Label(
            header,
            text="Errores · Detección manual por umbrales RAW",
            bg=BG_ROOT,
            fg=FG,
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Ajusta umbrales RAW y máscara manual sobre la visual térmica para encontrar zonas de interés.",
            bg=BG_ROOT,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(4, 0))

        body = tk.Frame(self, bg=BG_ROOT)
        body.pack(side="top", fill="both", expand=True, padx=12, pady=(0, 12))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=BG_PANEL, bd=1, relief="solid", highlightbackground="#2d4b68", highlightthickness=1)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))

        right = tk.Frame(body, bg=BG_PANEL, bd=1, relief="solid", highlightbackground="#2d4b68", highlightthickness=1)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        self._build_left(left)
        self._build_right(right)

    def _section_title(self, parent, text):
        tk.Label(parent, text=text, bg=BG_PANEL, fg=ACCENT_2, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 6))

    def _build_left(self, parent):
        self._section_title(parent, "Misiones")

        mission_box = tk.Frame(parent, bg=BG_PANEL)
        mission_box.pack(fill="x", padx=10)
        tk.Label(mission_box, text="Misión:", bg=BG_PANEL, fg=FG).pack(side="left")
        self.mission_combo = ttk.Combobox(mission_box, textvariable=self.current_mission, state="readonly", width=24)
        self.mission_combo.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.mission_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_list())

        new_mission = tk.Frame(parent, bg=BG_PANEL)
        new_mission.pack(fill="x", padx=10, pady=(8, 0))
        tk.Entry(new_mission, textvariable=self.new_mission_name, bg=BG_CARD, fg=FG, insertbackground=FG, relief="flat").pack(side="left", fill="x", expand=True)
        tk.Button(new_mission, text="Crear", command=self._create_mission, bg=ACCENT, fg="#082032", relief="flat", padx=10).pack(side="left", padx=(6, 0))

        mission_btns = tk.Frame(parent, bg=BG_PANEL)
        mission_btns.pack(fill="x", padx=10, pady=(8, 0))
        tk.Button(mission_btns, text="Agregar imágenes", command=self._add_images_to_mission, bg="#244b6b", fg=FG, relief="flat").pack(side="left")
        tk.Button(mission_btns, text="Eliminar imagen", command=self._delete_selected_image, bg="#5a2330", fg=FG, relief="flat").pack(side="left", padx=6)

        self._section_title(parent, "Imágenes")
        self.listbox = tk.Listbox(
            parent,
            width=42,
            height=18,
            bg=BG_CARD,
            fg=FG,
            selectbackground="#295b82",
            selectforeground=FG,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#2d4b68",
        )
        self.listbox.pack(fill="both", expand=True, padx=10)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        btns = tk.Frame(parent, bg=BG_PANEL)
        btns.pack(fill="x", padx=10, pady=(8, 0))
        tk.Button(btns, text="Actualizar", command=self._refresh_list, bg="#244b6b", fg=FG, relief="flat").pack(side="left")
        tk.Button(btns, text="Abrir archivo…", command=self._browse_file, bg="#244b6b", fg=FG, relief="flat").pack(side="left", padx=6)
        tk.Button(btns, text="Abrir carpeta", command=self._open_current_folder, bg="#244b6b", fg=FG, relief="flat").pack(side="left")

        self._section_title(parent, "Parámetros del análisis")
        cfg = tk.Frame(parent, bg=BG_PANEL)
        cfg.pack(fill="x", padx=10, pady=(0, 10))

        def row(label, var):
            r = tk.Frame(cfg, bg=BG_PANEL)
            r.pack(fill="x", pady=3)
            tk.Label(r, text=label, width=14, anchor="w", bg=BG_PANEL, fg=FG).pack(side="left")
            tk.Entry(r, textvariable=var, bg=BG_CARD, fg=FG, insertbackground=FG, relief="flat").pack(side="left", fill="x", expand=True)

        row("conf", self.conf)
        row("out_size", self.out_size)
        row("min_area", self.min_area)
        row("max_area", self.max_area)

        mp = tk.Frame(cfg, bg=BG_PANEL)
        mp.pack(fill="x", pady=(6, 0))
        tk.Label(mp, text="model", width=14, anchor="w", bg=BG_PANEL, fg=FG).pack(side="left")
        tk.Entry(mp, textvariable=self.model_path, bg=BG_CARD, fg=FG, insertbackground=FG, relief="flat").pack(side="left", fill="x", expand=True)
        tk.Button(mp, text="…", width=3, command=self._browse_model, bg="#244b6b", fg=FG, relief="flat").pack(side="left", padx=4)

        act = tk.Frame(parent, bg=BG_PANEL)
        act.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(act, text="Analizar", command=self._analyze, bg=ACCENT, fg="#082032", relief="flat", padx=14).pack(side="left")
        tk.Button(act, text="Abrir salida", command=self._open_output, bg="#244b6b", fg=FG, relief="flat").pack(side="left", padx=6)

        self.status = tk.Label(parent, text="Selecciona una imagen térmica .JPG/.PNG", bg=BG_PANEL, fg=MUTED, anchor="w", justify="left")
        self.status.pack(fill="x", padx=10, pady=(0, 10))

    def _build_right(self, parent):
        top = tk.Frame(parent, bg=BG_PANEL)
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        top.grid_columnconfigure(0, weight=1)

        self.preview_title = tk.Label(top, text="Preview", bg=BG_PANEL, fg=FG, font=("Segoe UI", 11, "bold"))
        self.preview_title.grid(row=0, column=0, sticky="w")
        self.preview_hint = tk.Label(top, text="Preview térmica + máscara manual por canales sobre la visual térmica", bg=BG_PANEL, fg=MUTED)
        self.preview_hint.grid(row=1, column=0, sticky="w", pady=(2, 0))

        sliders = tk.Frame(top, bg=BG_CARD, bd=1, relief="solid", highlightbackground="#2d4b68", highlightthickness=1)
        sliders.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        for c in range(3):
            sliders.grid_columnconfigure(c, weight=1)

        head = tk.Frame(sliders, bg=BG_CARD)
        head.grid(row=0, column=0, columnspan=3, sticky="ew", padx=8, pady=(8, 4))
        tk.Label(head, text="Espacio de color", bg=BG_CARD, fg=FG).pack(side="left")
        self.space_combo = ttk.Combobox(head, textvariable=self.color_space, values=("RGB", "HSV", "LAB", "GRAY"), state="readonly", width=8)
        self.space_combo.pack(side="left", padx=(8, 10))
        self.space_combo.bind("<<ComboboxSelected>>", lambda _e: self._redraw_preview())
        self.threshold_info = tk.Label(head, text="0 px · 0 blobs", bg=BG_CARD, fg=ACCENT_2)
        self.threshold_info.pack(side="right")

        self.channel_labels = []
        for i, (label, vmin, vmax) in enumerate((("Canal 1", self.c1_min, self.c1_max), ("Canal 2", self.c2_min, self.c2_max), ("Canal 3", self.c3_min, self.c3_max)), start=1):
            row = tk.Frame(sliders, bg=BG_CARD)
            row.grid(row=i, column=0, columnspan=3, sticky="ew", padx=8, pady=4)
            row.grid_columnconfigure(1, weight=1)
            lab = tk.Label(row, text=label, width=9, anchor="w", bg=BG_CARD, fg=FG)
            lab.grid(row=0, column=0, sticky="w")
            self.channel_labels.append(lab)
            tk.Scale(row, from_=0, to=255, orient="horizontal", variable=vmin, command=lambda _v: self._redraw_preview(), bg=BG_CARD, fg=FG, highlightthickness=0, troughcolor="#274765", length=280).grid(row=0, column=1, sticky="ew", padx=(6,8))
            tk.Scale(row, from_=0, to=255, orient="horizontal", variable=vmax, command=lambda _v: self._redraw_preview(), bg=BG_CARD, fg=FG, highlightthickness=0, troughcolor="#274765", length=280).grid(row=0, column=2, sticky="ew")

        adv = tk.Frame(top, bg=BG_PANEL)
        adv.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        for i in range(8):
            adv.grid_columnconfigure(i, weight=1 if i in (1,3,5,7) else 0)

        tk.Label(adv, text="Blur", bg=BG_PANEL, fg=FG).grid(row=0, column=0, sticky="w")
        tk.Scale(adv, from_=1, to=31, resolution=2, orient="horizontal", variable=self.blur_ksize, command=lambda _v: self._redraw_preview(), bg=BG_PANEL, fg=FG, highlightthickness=0, troughcolor="#274765", length=140).grid(row=0, column=1, sticky="ew", padx=(6,12))

        tk.Label(adv, text="Erosión", bg=BG_PANEL, fg=FG).grid(row=0, column=2, sticky="w")
        tk.Scale(adv, from_=0, to=8, orient="horizontal", variable=self.erode_iter, command=lambda _v: self._redraw_preview(), bg=BG_PANEL, fg=FG, highlightthickness=0, troughcolor="#274765", length=140).grid(row=0, column=3, sticky="ew", padx=(6,12))

        tk.Label(adv, text="Dilatar", bg=BG_PANEL, fg=FG).grid(row=0, column=4, sticky="w")
        tk.Scale(adv, from_=0, to=8, orient="horizontal", variable=self.dilate_iter, command=lambda _v: self._redraw_preview(), bg=BG_PANEL, fg=FG, highlightthickness=0, troughcolor="#274765", length=140).grid(row=0, column=5, sticky="ew", padx=(6,12))

        tk.Label(adv, text="Cierre", bg=BG_PANEL, fg=FG).grid(row=0, column=6, sticky="w")
        tk.Scale(adv, from_=0, to=8, orient="horizontal", variable=self.morph_close, command=lambda _v: self._redraw_preview(), bg=BG_PANEL, fg=FG, highlightthickness=0, troughcolor="#274765", length=140).grid(row=0, column=7, sticky="ew")

        tk.Label(adv, text="Área min", bg=BG_PANEL, fg=FG).grid(row=1, column=0, sticky="w", pady=(8,0))
        e_min = tk.Entry(adv, textvariable=self.min_area, width=8, bg=BG_CARD, fg=FG, insertbackground=FG, relief="flat")
        e_min.grid(row=1, column=1, sticky="w", pady=(8,0))
        e_min.bind("<Return>", lambda _e: self._redraw_preview())
        e_min.bind("<FocusOut>", lambda _e: self._redraw_preview())

        tk.Label(adv, text="Área max", bg=BG_PANEL, fg=FG).grid(row=1, column=2, sticky="w", pady=(8,0))
        e_max = tk.Entry(adv, textvariable=self.max_area, width=8, bg=BG_CARD, fg=FG, insertbackground=FG, relief="flat")
        e_max.grid(row=1, column=3, sticky="w", pady=(8,0))
        e_max.bind("<Return>", lambda _e: self._redraw_preview())
        e_max.bind("<FocusOut>", lambda _e: self._redraw_preview())

        self.preview = tk.Label(parent, bg=BG_CARD, bd=1, relief="solid", highlightbackground="#2d4b68", highlightthickness=1)
        self.preview.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.preview.bind("<Configure>", lambda _e: self._redraw_preview())
        self.preview.bind("<Motion>", self._on_preview_motion)

        bottom = tk.Frame(parent, bg=BG_PANEL)
        bottom.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.hover_info = tk.Label(bottom, text="x=—  y=—  RAW=—", bg=BG_PANEL, fg=FG, anchor="w")
        self.hover_info.pack(fill="x")
        self.metrics = tk.Label(bottom, text="", bg=BG_PANEL, fg=MUTED, justify="left", anchor="w")
        self.metrics.pack(fill="x", pady=(6, 0))

    def _refresh_missions(self):
        names = ["General"]
        try:
            for entry in os.listdir(self._missions_root):
                full = os.path.join(self._missions_root, entry)
                if os.path.isdir(full):
                    names.append(entry)
        except Exception:
            pass
        names = sorted(set(names), key=lambda s: s.lower())
        self.mission_combo["values"] = names
        if self.current_mission.get() not in names:
            self.current_mission.set(names[0])

    def _current_mission_dir(self) -> str:
        mission = self.current_mission.get().strip() or "General"
        if mission == "General":
            return self._thermal_photos
        p = os.path.join(self._missions_root, mission)
        os.makedirs(p, exist_ok=True)
        return p

    def _display_name(self, path: str) -> str:
        try:
            rel = os.path.relpath(path, self._thermal_photos)
            return rel.replace("\\", "/")
        except Exception:
            return os.path.basename(path)

    def _refresh_list(self):
        self._refresh_missions()
        self.listbox.delete(0, tk.END)
        folder = self._current_mission_dir()
        if not os.path.isdir(folder):
            self.status.config(text=f"No existe carpeta: {folder}")
            return
        exts = (".jpg", ".jpeg", ".png")
        files = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(exts)]
        files.sort(key=lambda p: os.path.basename(p).lower())
        self._list_paths = files
        for p in files:
            self.listbox.insert(tk.END, self._display_name(p))
        self.status.config(text=f"{len(files)} archivos en misión '{self.current_mission.get()}'")

    def _on_select(self, _evt=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        try:
            path = self._list_paths[idx]
        except Exception:
            return
        self.selected_path.set(path)
        self._load_preview_data(path)

    def _browse_file(self):
        p = filedialog.askopenfilename(title="Selecciona una imagen térmica", filetypes=[("Images", "*.jpg *.jpeg *.png"), ("All", "*")])
        if p:
            self.selected_path.set(p)
            self._load_preview_data(p)

    def _browse_model(self):
        p = filedialog.askopenfilename(title="Selecciona best.pt", filetypes=[("PyTorch weights", "*.pt"), ("All", "*")])
        if p:
            self.model_path.set(p)

    def _create_mission(self):
        name = self.new_mission_name.get().strip()
        if not name:
            messagebox.showwarning("Errores", "Escribe un nombre para la misión")
            return
        bad = set('\\/:*?"<>|')
        name = "".join("_" if c in bad else c for c in name)
        path = os.path.join(self._missions_root, name)
        os.makedirs(path, exist_ok=True)
        self.current_mission.set(name)
        self.new_mission_name.set("")
        self._refresh_list()

    def _add_images_to_mission(self):
        paths = filedialog.askopenfilenames(title="Agregar imágenes a la misión", filetypes=[("Images", "*.jpg *.jpeg *.png"), ("All", "*")])
        if not paths:
            return
        dest_dir = self._current_mission_dir()
        copied = 0
        for src in paths:
            try:
                base = os.path.basename(src)
                dst = os.path.join(dest_dir, base)
                if os.path.abspath(src) != os.path.abspath(dst):
                    root, ext = os.path.splitext(dst)
                    n = 1
                    while os.path.exists(dst):
                        dst = f"{root}_{n}{ext}"
                        n += 1
                    shutil.copy2(src, dst)
                copied += 1
            except Exception:
                pass
        self._refresh_list()
        self.status.config(text=f"{copied} imagen(es) agregadas a '{self.current_mission.get()}'")

    def _delete_selected_image(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("Errores", "Selecciona una imagen para eliminar")
            return
        idx = sel[0]
        path = self._list_paths[idx]
        if not messagebox.askyesno("Eliminar imagen", f"¿Eliminar esta imagen?\n\n{os.path.basename(path)}"):
            return
        try:
            os.remove(path)
            self.selected_path.set("")
            self.preview.configure(image="")
            self.preview_title.configure(text="Preview")
            self.hover_info.configure(text="x=—  y=—  RAW=—")
        except Exception as e:
            messagebox.showerror("Errores", f"No se pudo eliminar:\n{e}")
            return
        self._refresh_list()

    def _open_current_folder(self):
        folder = self._current_mission_dir()
        try:
            import subprocess, sys
            if sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", folder])
            elif sys.platform.startswith("win"):
                os.startfile(folder)
            elif sys.platform.startswith("darwin"):
                subprocess.Popen(["open", folder])
        except Exception:
            messagebox.showinfo("Carpeta", folder)

    def _load_preview_data(self, path: str):
        try:
            img = Image.open(path).convert("RGB")
            self._preview_base_pil = img
            self._preview_visual_pil = img
            self.preview_title.configure(text=os.path.basename(path))
        except Exception as e:
            self._preview_base_pil = None
            self._preview_visual_pil = None
            self.preview.configure(image="")
            self.preview_title.configure(text="Preview")
            self.status.configure(text=f"No se pudo abrir preview: {e}")
            return

        self._raw_arr = None
        self._temp_arr = None
        details = []
        try:
            from sensores.thermal_matrix import get_or_create_thermal_matrices
            mats = get_or_create_thermal_matrices(path)
            try:
                from sensores.thermal_map import map_and_save
                mapped_path = map_and_save(path)
                if mapped_path and os.path.exists(mapped_path):
                    self._preview_visual_pil = Image.open(mapped_path).convert("RGB")
            except Exception:
                self._preview_visual_pil = self._preview_base_pil
            raw_path = getattr(mats, "raw_path", None) or getattr(mats, "paths", {}).get("raw")
            temp_path = getattr(mats, "temp_path", None) or getattr(mats, "paths", {}).get("tempC")
            if raw_path and os.path.exists(raw_path):
                self._raw_arr = np.load(raw_path)
            if temp_path and os.path.exists(temp_path):
                self._temp_arr = np.load(temp_path)
            if self._raw_arr is not None:
                details.append(f"RAW shape={self._raw_arr.shape}")
                details.append(f"RAW min/max={int(np.nanmin(self._raw_arr))}/{int(np.nanmax(self._raw_arr))}")
            if self._temp_arr is not None:
                finite = np.isfinite(self._temp_arr)
                details.append(f"Temp válidos={float(finite.mean())*100:.1f}%")
                details.append("Visual=colorspace térmico (inferno)")
        except Exception as e:
            details.append(f"Sin matriz térmica: {e}")

        self.metrics.configure(text="\n".join(details))
        self._redraw_preview()

    def _mask_params(self):
        try:
            min_area = max(0, int(float((self.min_area.get() or "0").strip())))
        except Exception:
            min_area = 0
        try:
            max_area = max(0, int(float((self.max_area.get() or "0").strip())))
        except Exception:
            max_area = 0
        blur = int(self.blur_ksize.get())
        blur = max(1, blur if blur % 2 == 1 else blur + 1)
        erode_it = max(0, int(self.erode_iter.get()))
        dilate_it = max(0, int(self.dilate_iter.get()))
        close_it = max(0, int(self.morph_close.get()))
        return blur, erode_it, dilate_it, close_it, min_area, max_area

    def _update_channel_labels(self):
        space = self.color_space.get()
        labels = {
            "RGB": ("R min/max", "G min/max", "B min/max"),
            "HSV": ("H min/max", "S min/max", "V min/max"),
            "LAB": ("L min/max", "A min/max", "B min/max"),
            "GRAY": ("Gray min/max", "Canal 2", "Canal 3"),
        }.get(space, ("Canal 1", "Canal 2", "Canal 3"))
        for lab_widget, txt in zip(self.channel_labels, labels):
            lab_widget.configure(text=txt)

    def _converted_visual_array(self):
        base = (self._preview_visual_pil or self._preview_base_pil)
        if base is None:
            return None
        arr_rgb = np.array(base.convert("RGB"))
        space = self.color_space.get()
        if space == "RGB":
            return arr_rgb
        arr_bgr = cv.cvtColor(arr_rgb, cv.COLOR_RGB2BGR)
        if space == "HSV":
            return cv.cvtColor(arr_bgr, cv.COLOR_BGR2HSV)
        if space == "LAB":
            return cv.cvtColor(arr_bgr, cv.COLOR_BGR2LAB)
        if space == "GRAY":
            gray = cv.cvtColor(arr_bgr, cv.COLOR_BGR2GRAY)
            return cv.merge([gray, gray, gray])
        return arr_rgb

    def _compute_mask(self):
        conv = self._converted_visual_array()
        if conv is None:
            return None, 0, 0
        blur, erode_it, dilate_it, close_it, min_area, max_area = self._mask_params()
        work = conv.copy()
        if blur > 1:
            work = cv.GaussianBlur(work, (blur, blur), 0)
        lo = np.array([min(self.c1_min.get(), self.c1_max.get()), min(self.c2_min.get(), self.c2_max.get()), min(self.c3_min.get(), self.c3_max.get())], dtype=np.uint8)
        hi = np.array([max(self.c1_min.get(), self.c1_max.get()), max(self.c2_min.get(), self.c2_max.get()), max(self.c3_min.get(), self.c3_max.get())], dtype=np.uint8)
        mask = cv.inRange(work, lo, hi)
        kernel = np.ones((3, 3), np.uint8)
        if erode_it > 0:
            mask = cv.erode(mask, kernel, iterations=erode_it)
        if dilate_it > 0:
            mask = cv.dilate(mask, kernel, iterations=dilate_it)
        if close_it > 0:
            mask = cv.morphologyEx(mask, cv.MORPH_CLOSE, kernel, iterations=close_it)
        num_labels, labels, stats, _cent = cv.connectedComponentsWithStats(mask, 8)
        filtered = np.zeros_like(mask)
        kept = 0
        for i in range(1, num_labels):
            area = int(stats[i, cv.CC_STAT_AREA])
            if area < min_area:
                continue
            if max_area > 0 and area > max_area:
                continue
            filtered[labels == i] = 255
            kept += 1
        return filtered, int(np.count_nonzero(filtered)), kept

    def _make_overlay_image(self) -> Image.Image | None:
        base = (self._preview_visual_pil or self._preview_base_pil)
        if base is None:
            return None
        img = np.array(base.convert("RGB"))
        mask, total, blobs = self._compute_mask()
        if mask is None:
            self.threshold_info.configure(text="sin máscara")
            return Image.fromarray(img)

        self.threshold_info.configure(text=f"{total} px · {blobs} blobs")
        if mask.shape[1] != img.shape[1] or mask.shape[0] != img.shape[0]:
            mask = cv.resize(mask, (img.shape[1], img.shape[0]), interpolation=cv.INTER_NEAREST)

        overlay = img.copy()
        fill = np.zeros_like(overlay)
        fill[:, :] = (255, 232, 64)
        hit = mask > 0
        if np.any(hit):
            blended = (
                overlay[hit].astype(np.float32) * 0.45 +
                fill[hit].astype(np.float32) * 0.55
            ).astype(np.uint8)
            overlay[hit] = blended

        contours, _ = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
        cv.drawContours(overlay, contours, -1, (255, 80, 20), 2)
        return Image.fromarray(overlay)

    def _redraw_preview(self):
        self._update_channel_labels()
        out = self._make_overlay_image()
        if out is None:
            return
        label_w = max(self.preview.winfo_width(), 300)
        label_h = max(self.preview.winfo_height(), 250)
        src_w, src_h = out.size
        scale = min(label_w / src_w, label_h / src_h)
        scale = max(scale, 0.01)
        draw_w = max(1, int(src_w * scale))
        draw_h = max(1, int(src_h * scale))
        self._preview_scale = scale
        self._preview_offset = ((label_w - draw_w) // 2, (label_h - draw_h) // 2)
        self._display_shape = (draw_h, draw_w)

        canvas = Image.new("RGB", (label_w, label_h), BG_CARD)
        resized = out.resize((draw_w, draw_h), Image.Resampling.LANCZOS)
        canvas.paste(resized, self._preview_offset)
        self._imgtk = ImageTk.PhotoImage(canvas)
        self.preview.configure(image=self._imgtk)

    def _on_preview_motion(self, event):
        if self._preview_base_pil is None or self._raw_arr is None:
            return
        ox, oy = self._preview_offset
        x = event.x - ox
        y = event.y - oy
        if x < 0 or y < 0:
            self.hover_info.configure(text="x=—  y=—  RAW=—")
            return
        if not self._display_shape:
            return
        draw_h, draw_w = self._display_shape
        if x >= draw_w or y >= draw_h:
            self.hover_info.configure(text="x=—  y=—  RAW=—")
            return
        src_img = (self._preview_visual_pil or self._preview_base_pil)
        src_w, src_h = src_img.size
        mx = min(src_w - 1, max(0, int(x / max(self._preview_scale, 1e-6))))
        my = min(src_h - 1, max(0, int(y / max(self._preview_scale, 1e-6))))

        raw = self._raw_arr
        if raw.shape[1] != src_w or raw.shape[0] != src_h:
            mx_raw = min(raw.shape[1] - 1, max(0, int(mx * raw.shape[1] / max(src_w, 1))))
            my_raw = min(raw.shape[0] - 1, max(0, int(my * raw.shape[0] / max(src_h, 1))))
        else:
            mx_raw, my_raw = mx, my
        raw_v = int(raw[my_raw, mx_raw])
        txt = f"x={mx_raw}  y={my_raw}  RAW={raw_v}"
        conv = self._converted_visual_array()
        if conv is not None and conv.shape[:2] == raw.shape[:2]:
            cvals = conv[my_raw, mx_raw]
            space = self.color_space.get()
            txt += f"  · {space}=({int(cvals[0])},{int(cvals[1])},{int(cvals[2])})"
            lo = [min(self.c1_min.get(), self.c1_max.get()), min(self.c2_min.get(), self.c2_max.get()), min(self.c3_min.get(), self.c3_max.get())]
            hi = [max(self.c1_min.get(), self.c1_max.get()), max(self.c2_min.get(), self.c2_max.get()), max(self.c3_min.get(), self.c3_max.get())]
            inside = all(lo[i] <= int(cvals[i]) <= hi[i] for i in range(3))
            txt += "  · dentro" if inside else "  · fuera"
        if self._temp_arr is not None and self._temp_arr.shape[:2] == raw.shape[:2]:
            try:
                tv = float(self._temp_arr[my_raw, mx_raw])
                txt += f"  · Temp={tv:.2f} °C" if np.isfinite(tv) else "  · Temp inválida"
            except Exception:
                pass
        self.hover_info.configure(text=txt)

    def _analyze(self):
        path = self.selected_path.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showwarning("Errores", "Selecciona una imagen válida")
            return
        model = self.model_path.get().strip()
        if not model or not os.path.exists(model):
            messagebox.showwarning("Errores", "No se encontró el modelo best.pt")
            return
        try:
            from sensores.thermal_matrix import get_or_create_thermal_matrices
            mats = get_or_create_thermal_matrices(path)
            tempC_path = getattr(mats, "temp_path", None) or getattr(mats, "paths", {}).get("tempC")
            if not tempC_path or not os.path.exists(tempC_path):
                raise RuntimeError("No se generó tempC.npy")
        except Exception as e:
            messagebox.showerror("Errores", f"No se pudo obtener matriz térmica real.\n\n{e}")
            return

        def f_or_none(s: str):
            s = (s or "").strip()
            return None if not s else float(s)

        try:
            conf = float(self.conf.get().strip() or "0.25")
            out_size = int(float(self.out_size.get().strip() or "512"))
            min_area = int(float(self.min_area.get().strip() or "25"))
        except Exception:
            messagebox.showwarning("Errores", "Parámetros inválidos")
            return

        try:
            max_area = int(float(self.max_area.get().strip() or "0"))
        except Exception:
            max_area = 0

        try:
            from sensores.errors_pipeline import analyze_thermal_for_errors
            res = analyze_thermal_for_errors(
                thermal_jpg_path=path,
                tempC_npy_path=tempC_path,
                output_root=self._media_root,
                model_path=model,
                conf=conf,
                out_size=out_size,
                tmin=None,
                tmax=None,
                min_area_px=min_area,
                max_area_px=max_area,
                color_space=self.color_space.get(),
                c1_min=int(self.c1_min.get()),
                c2_min=int(self.c2_min.get()),
                c3_min=int(self.c3_min.get()),
                c1_max=int(self.c1_max.get()),
                c2_max=int(self.c2_max.get()),
                c3_max=int(self.c3_max.get()),
                blur_ksize=int(self.blur_ksize.get()),
                erode_iter=int(self.erode_iter.get()),
                dilate_iter=int(self.dilate_iter.get()),
                close_iter=int(self.morph_close.get()),
            )
        except Exception as e:
            messagebox.showerror("Errores", f"Falló el análisis: {e}")
            return

        if not res.ok:
            self.metrics.configure(text=f"Targets: {res.targets_detected}\nError: {res.error}\nDebug: {os.path.basename(res.debug_json_path) if res.debug_json_path else ''}")
            self.status.configure(text="Análisis incompleto")
            return

        self.status.configure(text="OK")
        self.metrics.configure(text=(f"Targets detectados: {res.targets_detected}\nHotspots: {res.hotspots_count}\nSalida: {os.path.dirname(res.roi_warp_path)}"))
        if res.hotspots_overlay_path and os.path.exists(res.hotspots_overlay_path):
            self.selected_path.set(res.hotspots_overlay_path)
            self._load_preview_data(res.hotspots_overlay_path)

    def _open_output(self):
        candidate_dirs = []
        if self._last_output_dir:
            candidate_dirs.append(self._last_output_dir)
        path = self.selected_path.get().strip()
        if path:
            candidate_dirs.append(os.path.join(self._media_root, "thermal", "errors", os.path.splitext(os.path.basename(path))[0]))
        if self._last_analyzed_source_path:
            candidate_dirs.append(os.path.join(self._media_root, "thermal", "errors", os.path.splitext(os.path.basename(self._last_analyzed_source_path))[0]))

        out_dir = ""
        for cand in candidate_dirs:
            if cand and os.path.isdir(cand):
                out_dir = cand
                break
        if not out_dir:
            messagebox.showinfo("Errores", "Aún no hay salida para esta imagen")
            return
        try:
            import subprocess, sys
            if sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", out_dir])
            elif sys.platform.startswith("win"):
                os.startfile(out_dir)
            elif sys.platform.startswith("darwin"):
                subprocess.Popen(["open", out_dir])
        except Exception:
            messagebox.showinfo("Salida", out_dir)