
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np


@dataclass
class ErrorsResult:
    ok: bool
    targets_detected: int = 0
    target_centroids_px: Optional[List[Tuple[float, float]]] = None

    roi_warp_path: str = ""
    roi_warp_tempC_path: str = ""

    hotspots_count: int = 0
    hotspots_centroids_px: Optional[List[Tuple[float, float]]] = None
    hotspots_mask_path: str = ""
    hotspots_overlay_path: str = ""
    regions_summary_path: str = ""

    debug_json_path: str = ""
    error: str = ""


def _ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _order_four_points(pts: List[Tuple[float, float]]) -> np.ndarray:
    """Ordena 4 puntos como TL, TR, BR, BL (convención clásica)."""
    arr = np.array(pts, dtype=np.float32)
    if arr.shape != (4, 2):
        raise ValueError("Se requieren exactamente 4 puntos para ordenar")
    s = arr.sum(axis=1)
    diff = np.diff(arr, axis=1).reshape(-1)
    tl = arr[np.argmin(s)]
    br = arr[np.argmax(s)]
    tr = arr[np.argmin(diff)]
    bl = arr[np.argmax(diff)]
    return np.stack([tl, tr, br, bl], axis=0)


def _detect_targets_obb(image_path: str, model_path: str, conf: float = 0.25) -> List[List[Tuple[float, float]]]:
    """Devuelve lista de cajas OBB como 4 puntos (x,y) por caja."""
    from ultralytics import YOLO  # lazy import

    model = YOLO(model_path)
    res = model.predict(image_path, conf=conf, verbose=False)
    if not res:
        return []

    r0 = res[0]
    if getattr(r0, "obb", None) is None or r0.obb is None:
        return []

    boxes: List[List[Tuple[float, float]]] = []
    # Ultralytics OBB: r0.obb.xyxyxyxy -> (N, 4, 2)
    xyxyxyxy = getattr(r0.obb, "xyxyxyxy", None)
    if xyxyxyxy is None:
        return []
    arr = xyxyxyxy.cpu().numpy() if hasattr(xyxyxyxy, "cpu") else np.array(xyxyxyxy)
    for row in arr:
        row = np.array(row).reshape(4, 2)
        boxes.append([(float(row[i, 0]), float(row[i, 1])) for i in range(4)])
    return boxes


def _centroid_from_quad(quad: List[Tuple[float, float]]) -> Tuple[float, float]:
    arr = np.array(quad, dtype=np.float32)
    return (float(arr[:, 0].mean()), float(arr[:, 1].mean()))


def _warp_perspective(
    img_bgr: np.ndarray,
    tempC: np.ndarray,
    src_pts: np.ndarray,
    out_size: int = 512,
) -> Tuple[np.ndarray, np.ndarray]:
    import cv2

    dst_pts = np.array(
        [[0, 0], [out_size - 1, 0], [out_size - 1, out_size - 1], [0, out_size - 1]], dtype=np.float32
    )
    M = cv2.getPerspectiveTransform(src_pts.astype(np.float32), dst_pts)
    warp_img = cv2.warpPerspective(img_bgr, M, (out_size, out_size), flags=cv2.INTER_LINEAR)
    warp_temp = cv2.warpPerspective(tempC.astype(np.float32), M, (out_size, out_size), flags=cv2.INTER_LINEAR)
    return warp_img, warp_temp



def _apply_visual_mask(
    img_bgr: np.ndarray,
    color_space: str = "RGB",
    c1_min: int = 0,
    c2_min: int = 0,
    c3_min: int = 0,
    c1_max: int = 255,
    c2_max: int = 255,
    c3_max: int = 255,
    blur_ksize: int = 1,
    erode_iter: int = 0,
    dilate_iter: int = 0,
    close_iter: int = 0,
    min_area_px: int = 25,
    max_area_px: int = 0,
) -> Tuple[np.ndarray, List[Dict[str, object]], Dict[str, object]]:
    import cv2

    color_space = (color_space or "RGB").upper()
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    if color_space == "RGB":
        work = rgb
    elif color_space == "HSV":
        work = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    elif color_space == "LAB":
        work = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    elif color_space == "GRAY":
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        work = cv2.merge([gray, gray, gray])
    else:
        work = rgb
        color_space = "RGB"

    blur_ksize = int(blur_ksize)
    if blur_ksize < 1:
        blur_ksize = 1
    if blur_ksize % 2 == 0:
        blur_ksize += 1
    if blur_ksize > 1:
        work = cv2.GaussianBlur(work, (blur_ksize, blur_ksize), 0)

    lo = np.array([min(c1_min, c1_max), min(c2_min, c2_max), min(c3_min, c3_max)], dtype=np.uint8)
    hi = np.array([max(c1_min, c1_max), max(c2_min, c2_max), max(c3_min, c3_max)], dtype=np.uint8)
    mask = cv2.inRange(work, lo, hi)

    kernel = np.ones((3, 3), np.uint8)
    if erode_iter > 0:
        mask = cv2.erode(mask, kernel, iterations=int(erode_iter))
    if dilate_iter > 0:
        mask = cv2.dilate(mask, kernel, iterations=int(dilate_iter))
    if close_iter > 0:
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=int(close_iter))

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    filtered = np.zeros_like(mask)
    regions: List[Dict[str, object]] = []
    for i in range(1, num_labels):
        area_px = int(stats[i, cv2.CC_STAT_AREA])
        if area_px < int(min_area_px):
            continue
        if int(max_area_px) > 0 and area_px > int(max_area_px):
            continue
        filtered[labels == i] = 255
        x = int(stats[i, cv2.CC_STAT_LEFT])
        y = int(stats[i, cv2.CC_STAT_TOP])
        w = int(stats[i, cv2.CC_STAT_WIDTH])
        h = int(stats[i, cv2.CC_STAT_HEIGHT])
        cx, cy = centroids[i]
        regions.append({
            "label": int(i),
            "area_px": area_px,
            "bbox": [x, y, w, h],
            "centroid_px": [float(cx), float(cy)],
        })

    meta = {
        "color_space": color_space,
        "channels_min": lo.tolist(),
        "channels_max": hi.tolist(),
        "blur_ksize": int(blur_ksize),
        "erode_iter": int(erode_iter),
        "dilate_iter": int(dilate_iter),
        "close_iter": int(close_iter),
        "min_area_px": int(min_area_px),
        "max_area_px": int(max_area_px),
        "pixels_selected": int(np.count_nonzero(filtered)),
        "regions_kept": len(regions),
    }
    return filtered, regions, meta


def _summarize_regions_temperature(mask: np.ndarray, labels_regions: List[Dict[str, object]], tempC_warp: np.ndarray) -> List[Dict[str, object]]:
    import cv2

    num_labels, labels, _stats, _centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    summaries: List[Dict[str, object]] = []
    for region in labels_regions:
        label_id = int(region.get("label", 0))
        if label_id <= 0 or label_id >= num_labels:
            continue
        hit = labels == label_id
        vals = tempC_warp[hit]
        vals = vals[np.isfinite(vals)]
        summary = dict(region)
        summary["valid_temp_px"] = int(vals.size)
        if vals.size > 0:
            summary["temp_mean_c"] = float(np.mean(vals))
            summary["temp_min_c"] = float(np.min(vals))
            summary["temp_max_c"] = float(np.max(vals))
            summary["temp_std_c"] = float(np.std(vals))
        else:
            summary["temp_mean_c"] = None
            summary["temp_min_c"] = None
            summary["temp_max_c"] = None
            summary["temp_std_c"] = None
        summaries.append(summary)
    return summaries

def _hotspots_mask(
    tempC_warp: np.ndarray,
    tmin: Optional[float] = None,
    tmax: Optional[float] = None,
    min_area_px: int = 25,
) -> Tuple[np.ndarray, List[Tuple[float, float]]]:
    """Máscara simple (estilo hot.py) pero sobre temperatura real (°C)."""
    import cv2

    t = tempC_warp.astype(np.float32)
    if tmin is None:
        tmin = float(np.nanpercentile(t, 95))
    if tmax is None:
        tmax = float(np.nanmax(t))

    mask = ((t >= tmin) & (t <= tmax)).astype(np.uint8) * 255
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)

    keep = np.zeros_like(mask)
    kept_centroids: List[Tuple[float, float]] = []
    for i in range(1, num_labels):
        area_px = int(stats[i, cv2.CC_STAT_AREA])
        if area_px < int(min_area_px):
            continue
        keep[labels == i] = 255
        cx, cy = centroids[i]
        kept_centroids.append((float(cx), float(cy)))

    return keep, kept_centroids


def analyze_thermal_for_errors(
    thermal_jpg_path: str,
    tempC_npy_path: str,
    output_root: str,
    model_path: str,
    conf: float = 0.25,
    out_size: int = 512,
    tmin: Optional[float] = None,
    tmax: Optional[float] = None,
    min_area_px: int = 25,
    max_area_px: int = 0,
    color_space: str = "RGB",
    c1_min: int = 0,
    c2_min: int = 0,
    c3_min: int = 0,
    c1_max: int = 255,
    c2_max: int = 255,
    c3_max: int = 255,
    blur_ksize: int = 1,
    erode_iter: int = 0,
    dilate_iter: int = 0,
    close_iter: int = 0,
) -> ErrorsResult:
    """Analiza una foto térmica y devuelve métricas + artefactos guardados."""
    try:
        import cv2

        base = os.path.splitext(os.path.basename(thermal_jpg_path))[0]
        out_dir = _ensure_dir(os.path.join(output_root, "thermal", "errors", base))

        tempC = np.load(tempC_npy_path)
        img = cv2.imread(thermal_jpg_path, cv2.IMREAD_COLOR)
        if img is None:
            return ErrorsResult(ok=False, error=f"No se pudo leer imagen: {thermal_jpg_path}")

        boxes = _detect_targets_obb(thermal_jpg_path, model_path=model_path, conf=conf)
        centroids = [_centroid_from_quad(b) for b in boxes]

        if len(centroids) < 4:
            dbg = {
                "thermal_jpg_path": os.path.abspath(thermal_jpg_path),
                "tempC_npy_path": os.path.abspath(tempC_npy_path),
                "model_path": os.path.abspath(model_path),
                "targets_detected": len(centroids),
                "note": "Se requieren 4 targets para warp.",
            }
            dbg_path = os.path.join(out_dir, "debug.json")
            with open(dbg_path, "w", encoding="utf-8") as f:
                json.dump(dbg, f, ensure_ascii=False, indent=2)
            return ErrorsResult(
                ok=False,
                targets_detected=len(centroids),
                target_centroids_px=centroids,
                debug_json_path=dbg_path,
                error="Menos de 4 targets detectados.",
            )

        h, w = img.shape[:2]
        cx0, cy0 = w / 2.0, h / 2.0
        centroids_sorted = sorted(centroids, key=lambda p: (p[0] - cx0) ** 2 + (p[1] - cy0) ** 2)
        cent4 = centroids_sorted[:4]
        src_pts = _order_four_points(cent4)

        warp_img, warp_temp = _warp_perspective(img, tempC, src_pts, out_size=out_size)

        roi_warp_path = os.path.join(out_dir, "ROI_warp.jpg")
        cv2.imwrite(roi_warp_path, warp_img)

        roi_warp_temp_path = os.path.join(out_dir, "ROI_warp_tempC.npy")
        np.save(roi_warp_temp_path, warp_temp.astype(np.float32))

        mask, regions, mask_meta = _apply_visual_mask(
            warp_img,
            color_space=color_space,
            c1_min=c1_min,
            c2_min=c2_min,
            c3_min=c3_min,
            c1_max=c1_max,
            c2_max=c2_max,
            c3_max=c3_max,
            blur_ksize=blur_ksize,
            erode_iter=erode_iter,
            dilate_iter=dilate_iter,
            close_iter=close_iter,
            min_area_px=min_area_px,
            max_area_px=max_area_px,
        )
        region_summaries = _summarize_regions_temperature(mask, regions, warp_temp)
        hot_centroids = [tuple(r["centroid_px"]) for r in region_summaries]
        mask_path = os.path.join(out_dir, "hotspots_mask.png")
        cv2.imwrite(mask_path, mask)

        overlay = warp_img.copy()
        hit = mask > 0
        overlay[hit] = (overlay[hit].astype(np.float32) * 0.45 + np.array([0, 0, 255], dtype=np.float32) * 0.55).astype(np.uint8)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay, contours, -1, (0, 165, 255), 2)
        for idx, region in enumerate(region_summaries, start=1):
            hx, hy = region["centroid_px"]
            cv2.circle(overlay, (int(hx), int(hy)), 4, (0, 255, 0), -1)
            mean_txt = region.get("temp_mean_c")
            label = f"{idx}: {mean_txt:.2f}C" if isinstance(mean_txt, float) else f"{idx}: n/a"
            cv2.putText(overlay, label, (int(hx) + 6, int(hy) - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        overlay_path = os.path.join(out_dir, "hotspots_overlay.jpg")
        cv2.imwrite(overlay_path, overlay)

        regions_summary_path = os.path.join(out_dir, "regions_summary.json")
        with open(regions_summary_path, "w", encoding="utf-8") as f:
            json.dump(region_summaries, f, ensure_ascii=False, indent=2)

        dbg = {
            "thermal_jpg_path": os.path.abspath(thermal_jpg_path),
            "tempC_npy_path": os.path.abspath(tempC_npy_path),
            "model_path": os.path.abspath(model_path),
            "targets_detected": 4,
            "target_centroids_px": cent4,
            "ordered_src_pts": src_pts.tolist(),
            "out_size": out_size,
            "hotspots_count": len(region_summaries),
            "analysis_mode": "visual_mask_after_warp_with_temp_mean",
            "mask_params": mask_meta,
            "regions_summary_path": os.path.abspath(regions_summary_path),
            "tmin": tmin,
            "tmax": tmax,
            "min_area_px": min_area_px,
            "max_area_px": max_area_px,
        }
        dbg_path = os.path.join(out_dir, "debug.json")
        with open(dbg_path, "w", encoding="utf-8") as f:
            json.dump(dbg, f, ensure_ascii=False, indent=2)

        return ErrorsResult(
            ok=True,
            targets_detected=4,
            target_centroids_px=cent4,
            roi_warp_path=roi_warp_path,
            roi_warp_tempC_path=roi_warp_temp_path,
            hotspots_count=len(region_summaries),
            hotspots_centroids_px=hot_centroids,
            hotspots_mask_path=mask_path,
            hotspots_overlay_path=overlay_path,
            regions_summary_path=regions_summary_path,
            debug_json_path=dbg_path,
        )
    except Exception as e:
        return ErrorsResult(ok=False, error=str(e))