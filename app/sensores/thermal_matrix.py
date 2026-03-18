
from __future__ import annotations

import io
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
from PIL import Image

from sensores.thermal_flir import extract_flir_radiometric

PNG_SIG = b"\x89PNG\r\n\x1a\n"
PARSER_VERSION = "apk-flir-v3"

@dataclass
class ThermalMatrices:
    raw: np.ndarray
    temp_c: Optional[np.ndarray]
    method: str
    meta: Dict[str, Any]
    raw_path: str
    temp_path: Optional[str]
    meta_path: str

def _find_sidecar_dng(photo_path: str) -> Optional[str]:
    base = os.path.splitext(photo_path)[0]
    for ext in (".DNG", ".dng", ".TIFF", ".tiff", ".TIF", ".tif"):
        cand = base + ext
        if os.path.exists(cand):
            return cand

    folder = os.path.dirname(photo_path)
    stem = os.path.splitext(os.path.basename(photo_path))[0]
    for sub in ("dng", "DNG", "raw", "RAW", "resources"):
        for ext in (".DNG", ".dng", ".tiff", ".tif"):
            cand = os.path.join(folder, sub, stem + ext)
            if os.path.exists(cand):
                return cand
    return None

def _extract_png_at(data: bytes, start: int) -> Optional[bytes]:
    if data[start : start + 8] != PNG_SIG:
        return None

    i = start + 8
    while i + 12 <= len(data):
        length = int.from_bytes(data[i : i + 4], "big")
        ctype = data[i + 4 : i + 8]
        i2 = i + 8 + length + 4
        if i2 > len(data):
            break
        if ctype == b"IEND":
            return data[start:i2]
        i = i2

    trailer = b"IEND\xaeB`\x82"
    end = data.find(trailer, start + 8)
    if end != -1:
        return data[start : end + len(trailer)]
    return None

def _decode_png_to_uint16(png_bytes: bytes) -> Optional[np.ndarray]:
    try:
        image = Image.open(io.BytesIO(png_bytes))
        image.load()
        arr = np.array(image)
    except Exception:
        return None

    if getattr(arr, "ndim", 0) != 2:
        return None
    if arr.dtype == np.uint16:
        return arr
    try:
        mn = int(arr.min())
        mx = int(arr.max())
    except Exception:
        return None
    if mn < 0 or mx > 65535:
        return None
    return arr.astype(np.uint16)

def extract_embedded_png16(path: str) -> Optional[Tuple[np.ndarray, Dict[str, Any]]]:
    data = Path(path).read_bytes()

    if data.startswith(PNG_SIG):
        raw = _decode_png_to_uint16(data)
        if raw is None:
            return None
        return raw, {
            "method": "png16_file",
            "radiometry_source": "png_file",
            "source_path": str(Path(path).resolve()),
            "raw_dtype": str(raw.dtype),
            "raw_shape": [int(raw.shape[0]), int(raw.shape[1])],
        }

    candidates = []
    pos = 0
    while True:
        pos = data.find(PNG_SIG, pos)
        if pos == -1:
            break
        png_bytes = _extract_png_at(data, pos)
        if png_bytes:
            raw = _decode_png_to_uint16(png_bytes)
            if raw is not None:
                candidates.append((raw, pos))
        pos += 8

    if not candidates:
        return None

    raw, offset = max(candidates, key=lambda item: item[0].size)
    return raw, {
        "method": "embedded_png16",
        "radiometry_source": "embedded_png16",
        "source_path": str(Path(path).resolve()),
        "embedded_png_offset": int(offset),
        "raw_dtype": str(raw.dtype),
        "raw_shape": [int(raw.shape[0]), int(raw.shape[1])],
    }

def extract_parrot_part_tiff(path: str) -> Optional[Tuple[np.ndarray, Dict[str, Any]]]:
    data = Path(path).read_bytes()
    marker = b"PART\x00\x01\x00\x00II*\x00"
    idx = data.find(marker)
    if idx == -1:
        return None

    try:
        import tifffile
    except Exception:
        return None

    try:
        with tifffile.TiffFile(io.BytesIO(data[idx + 8 :])) as tif:
            arr = tif.pages[0].asarray()
    except Exception:
        return None

    if getattr(arr, "ndim", 0) != 2:
        return None
    if arr.dtype != np.uint16:
        try:
            if int(arr.min()) < 0 or int(arr.max()) > 65535:
                return None
        except Exception:
            return None
        arr = arr.astype(np.uint16)

    return arr, {
        "method": "part_tiff",
        "radiometry_source": "jpg_part_tiff",
        "source_path": str(Path(path).resolve()),
        "part_temperature_unit": "centi_celsius",
        "raw_dtype": str(arr.dtype),
        "raw_shape": [int(arr.shape[0]), int(arr.shape[1])],
    }

def _part_to_temp_c(raw_u16: np.ndarray) -> np.ndarray:
    temp_c = raw_u16.astype(np.float32) / 100.0
    invalid = (raw_u16 == 0) | (raw_u16 == 65535)
    if invalid.any():
        temp_c = temp_c.copy()
        temp_c[invalid] = np.nan
    return temp_c

def _load_cached(raw_path: str, temp_path: str, meta_path: str) -> Optional[ThermalMatrices]:
    if not (os.path.exists(raw_path) and os.path.exists(meta_path)):
        return None

    try:
        with open(meta_path, "r", encoding="utf-8") as fh:
            meta = json.load(fh)
    except Exception:
        return None

    if meta.get("parser_version") != PARSER_VERSION:
        return None

    try:
        raw = np.load(raw_path)
        temp_c = np.load(temp_path).astype(np.float32) if os.path.exists(temp_path) else None
    except Exception:
        return None

    return ThermalMatrices(
        raw=raw,
        temp_c=temp_c,
        method=meta.get("method", "disk"),
        meta=meta,
        raw_path=raw_path,
        temp_path=temp_path if temp_c is not None else None,
        meta_path=meta_path,
    )

def _compute_matrices(jpg_path: str) -> Tuple[np.ndarray, Optional[np.ndarray], Dict[str, Any]]:
    candidates = [jpg_path]
    sidecar = _find_sidecar_dng(jpg_path)
    if sidecar and sidecar not in candidates:
        candidates.append(sidecar)

    for cand in candidates:
        payload = extract_flir_radiometric(cand)
        if payload is not None:
            meta = dict(payload.meta)
            meta["visual_path"] = str(Path(jpg_path).resolve())
            meta.setdefault("source_path", str(Path(cand).resolve()))
            return payload.raw_u16, payload.temp_c.astype(np.float32), meta

    for cand in candidates:
        part = extract_parrot_part_tiff(cand)
        if part is not None:
            raw, meta = part
            temp_c = _part_to_temp_c(raw)
            finite = np.isfinite(temp_c)
            meta.update(
                {
                    "temp_method": "part_centi_celsius",
                    "temp_valid_ratio": float(finite.mean()),
                    "visual_path": str(Path(jpg_path).resolve()),
                    "parser_warning": "fallback_part_tiff",
                }
            )
            if finite.any():
                meta["temp_range_c"] = [float(np.nanmin(temp_c)), float(np.nanmax(temp_c))]
                meta["temp_median_c"] = float(np.nanmedian(temp_c))
            return raw, temp_c.astype(np.float32), meta

    for cand in candidates:
        emb = extract_embedded_png16(cand)
        if emb is not None:
            raw, meta = emb
            meta.update(
                {
                    "visual_path": str(Path(jpg_path).resolve()),
                    "parser_warning": "fallback_embedded_png16_without_camera_info",
                    "temp_method": "unavailable",
                    "temp_valid_ratio": 0.0,
                }
            )
            return raw, None, meta

    raise RuntimeError(
        "No se encontró una fuente radiométrica utilizable en la foto térmica. "
        "Esta versión busca primero APP1 FLIR/CameraInfo y luego PART/PNG embebido."
    )

def get_or_create_thermal_matrices(
    jpg_path: str,
    matrices_dir: Optional[str] = None,
) -> ThermalMatrices:
    if matrices_dir is None:
        try:
            from config import MEDIA_ROOT

            media_root = MEDIA_ROOT
        except Exception:
            media_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media")
        matrices_dir = os.path.join(media_root, "thermal", "matrices")

    os.makedirs(matrices_dir, exist_ok=True)

    stem = os.path.splitext(os.path.basename(jpg_path))[0]
    raw_path = os.path.join(matrices_dir, f"{stem}_raw.npy")
    temp_path = os.path.join(matrices_dir, f"{stem}_tempC.npy")
    meta_path = os.path.join(matrices_dir, f"{stem}_meta.json")

    cached = _load_cached(raw_path, temp_path, meta_path)
    if cached is not None:
        return cached

    raw, temp_c, meta = _compute_matrices(jpg_path)
    meta = dict(meta)
    meta.update(
        {
            "parser_version": PARSER_VERSION,
            "method": meta.get("method", "unknown"),
            "raw_min": int(raw.min()),
            "raw_max": int(raw.max()),
            "raw_mean": float(raw.mean()),
        }
    )
    if temp_c is not None:
        finite = np.isfinite(temp_c)
        meta["temp_valid_ratio"] = float(finite.mean())
        if finite.any():
            meta.setdefault("temp_range_c", [float(np.nanmin(temp_c)), float(np.nanmax(temp_c))])
            meta.setdefault("temp_median_c", float(np.nanmedian(temp_c)))

    np.save(raw_path, raw)
    if temp_c is not None:
        np.save(temp_path, temp_c.astype(np.float32))
    elif os.path.exists(temp_path):
        os.remove(temp_path)

    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)

    return ThermalMatrices(
        raw=raw,
        temp_c=temp_c.astype(np.float32) if temp_c is not None else None,
        method=meta.get("method", "unknown"),
        meta=meta,
        raw_path=raw_path,
        temp_path=temp_path if temp_c is not None else None,
        meta_path=meta_path,
    )
