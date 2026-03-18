
import os
import tkinter as tk

def asset(*parts: str) -> str:
    """Construye la ruta a un recurso dentro de interfaz/assets."""
    base = os.path.join(os.path.dirname(__file__), "assets")
    return os.path.join(base, *parts)

def center_window(win: tk.Tk, width: int = None, height: int = None):
    win.update_idletasks()
    w = width or win.winfo_width()
    h = height or win.winfo_height()
    x = (win.winfo_screenwidth() // 2) - (w // 2)
    y = (win.winfo_screenheight() // 2) - (h // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")
