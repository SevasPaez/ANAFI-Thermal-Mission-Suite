import os
import shutil

def _collect_files(root_dir: str):
    out = []
    for base, _, files in os.walk(root_dir):
        for fn in files:
            p = os.path.join(base, fn)
            try:
                sz = os.path.getsize(p)
            except OSError:
                sz = 0
            out.append((p, sz))
    return out

def pick_best_downloaded_file(download_dir: str, prefer_exts=(".jpg", ".jpeg", ".png", ".dng", ".mp4", ".mov")) -> str:
    files = _collect_files(download_dir)
    if not files:
        raise FileNotFoundError(f"No se encontraron archivos descargados en {download_dir}")

    by_ext = {}
    for p, sz in files:
        ext = os.path.splitext(p)[1].lower()
        by_ext.setdefault(ext, []).append((p, sz))

    for ext in prefer_exts:
        ext = ext.lower()
        if ext in by_ext and by_ext[ext]:
            return sorted(by_ext[ext], key=lambda t: t[1], reverse=True)[0][0]

    return sorted(files, key=lambda t: t[1], reverse=True)[0][0]

def copy_as(src: str, dst: str) -> str:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    return dst
