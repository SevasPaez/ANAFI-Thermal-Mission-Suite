import os
import cv2 as cv
import numpy as np

def map_and_save(input_path: str) -> str:
    if not os.path.exists(input_path):
        raise FileNotFoundError(input_path)

    gray8 = None
    try:
        from sensores.thermal_matrix import get_or_create_thermal_matrices

        mats = get_or_create_thermal_matrices(input_path)
        if mats.temp_c is not None and np.isfinite(mats.temp_c).any():
            temp = mats.temp_c.astype(np.float32)
            finite = np.isfinite(temp)
            vals = temp[finite]
            lo = float(np.percentile(vals, 2))
            hi = float(np.percentile(vals, 98))
            if hi <= lo:
                lo = float(np.nanmin(vals))
                hi = float(np.nanmax(vals))
            norm = np.clip((temp - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
            norm[~finite] = 0.0
            gray8 = (norm * 255.0).astype(np.uint8)
    except Exception:
        gray8 = None

    if gray8 is None:
        img = cv.imread(input_path)
        if img is None:
            raise RuntimeError(f"No se pudo leer: {input_path}")
        if len(img.shape) == 3 and img.shape[2] == 3:
            gray8 = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
        else:
            gray8 = img
        gray8 = cv.normalize(gray8, None, 0, 255, cv.NORM_MINMAX)

    colored = cv.applyColorMap(gray8, cv.COLORMAP_INFERNO)
    out_dir = os.path.join(os.path.dirname(input_path), "mapped")
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(input_path))[0]
    out_path = os.path.join(out_dir, base + "_mapped.png")
    cv.imwrite(out_path, colored)
    return out_path
