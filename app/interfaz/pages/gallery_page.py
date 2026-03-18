
import os
import sys
import platform
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import cv2

THUMB_W, THUMB_H = 200, 120
IMG_EXTS = (".jpg", ".jpeg", ".png")
VID_EXTS = (".mp4", ".mov", ".avi", ".mkv")

try:
    from config import MEDIA_ROOT
    _MEDIA_ROOT = MEDIA_ROOT
except Exception:
    _MEDIA_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media")

_GALLERY_ROOT = os.path.join(_MEDIA_ROOT, "rgb")
_PHOTOS_DIR = os.path.join(_GALLERY_ROOT, "photos")
_VIDEOS_DIR = os.path.join(_GALLERY_ROOT, "videos")
os.makedirs(_PHOTOS_DIR, exist_ok=True)
os.makedirs(_VIDEOS_DIR, exist_ok=True)

def _is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMG_EXTS

def _is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VID_EXTS

def _list_media_recursive(media_dir: str):
    files = []
    for root, dirs, names in os.walk(media_dir):

        dirs[:] = [d for d in dirs if d.lower() not in ("mapped", "matrices")]
        for name in names:
            p = os.path.join(root, name)
            if not os.path.isfile(p):
                continue
            if p.endswith('.part'):
                continue
            try:
                if os.path.getsize(p) == 0:
                    continue
            except Exception:
                continue
            ext = os.path.splitext(p)[1].lower()
            if ext in IMG_EXTS or ext in VID_EXTS:
                files.append(p)
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return files

class GalleryPage(ttk.Frame):
    def __init__(self, parent, media_dir=None):
        super().__init__(parent)
        self.media_dir = media_dir or _GALLERY_ROOT
        os.makedirs(self.media_dir, exist_ok=True)

        toolbar = ttk.Frame(self)
        toolbar.pack(side='top', fill='x')
        ttk.Button(toolbar, text='Refrescar', command=self.refresh).pack(side='left', padx=4, pady=6)
        ttk.Button(toolbar, text='Abrir carpeta', command=self._open_folder).pack(side='left', padx=4, pady=6)

        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scroll = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.create_window((0, 0), window=self.inner, anchor='nw')
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.scroll.pack(side='right', fill='y')

        self._thumb_cache = {}
        self.refresh()

    def _open_folder(self):
        path = os.path.abspath(self.media_dir)
        try:
            sysname = platform.system().lower()
            if sysname.startswith('win'):
                os.startfile(path)
            elif sysname == 'darwin':
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except Exception:
            messagebox.showinfo('Carpeta', path)

    def refresh(self):

        for w in self.inner.winfo_children():
            w.destroy()

        files = _list_media_recursive(self.media_dir)

        if not files:
            ttk.Label(self.inner, text=f'No hay archivos en la galería ({self.media_dir})').pack(pady=12)
            return

        cols = 3
        r = c = 0
        for p in files:
            card = ttk.Frame(self.inner, padding=6)
            card.grid(row=r, column=c, sticky='nsew', padx=6, pady=6)

            thumb = self._get_thumb(p)
            lbl = ttk.Label(card, image=thumb)
            lbl.image = thumb
            lbl.pack()

            ttk.Label(card, text=os.path.basename(p), justify='center').pack(pady=4)
            ttk.Button(card, text='Abrir', command=lambda path=p: self._open_media(path)).pack()

            c += 1
            if c >= cols:
                c = 0
                r += 1

    def _open_media(self, path: str):
        try:
            if _is_image(path):
                self._open_image(path)
            elif _is_video(path):
                self._open_video(path)
            else:
                messagebox.showwarning('Archivo', f'No reconocido: {os.path.basename(path)}')
        except Exception as e:
            messagebox.showerror('Abrir media', f'No se pudo abrir:\n{os.path.basename(path)}\n{e}')

    def _open_image(self, path: str):
        img = Image.open(path)
        img.load()
        top = tk.Toplevel(self)
        top.title(os.path.basename(path))
        imtk = ImageTk.PhotoImage(img)
        lbl = ttk.Label(top, image=imtk)
        lbl.image = imtk
        lbl.pack()

    def _open_video(self, path: str):
        abspath = os.path.abspath(path)
        try:
            sysname = platform.system().lower()
            if sysname.startswith('win'):
                os.startfile(abspath)
            elif sysname == 'darwin':
                os.system(f'open "{abspath}"')
            else:
                os.system(f'xdg-open "{abspath}"')
        except Exception:
            messagebox.showinfo('Video', abspath)

    def _get_thumb(self, path: str):
        if path in self._thumb_cache:
            return self._thumb_cache[path]
        try:
            if _is_image(path):
                img = Image.open(path)
                img.load()
            else:
                cap = cv2.VideoCapture(path)
                ok, frame = cap.read()
                cap.release()
                if not ok or frame is None:
                    raise RuntimeError('No se pudo leer primer frame del video')
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame)

            img.thumbnail((THUMB_W, THUMB_H))
            imtk = ImageTk.PhotoImage(img)
        except Exception:
            from PIL import Image as PILImage
            img = PILImage.new('RGB', (THUMB_W, THUMB_H), 'gray')
            imtk = ImageTk.PhotoImage(img)
        self._thumb_cache[path] = imtk
        return imtk
