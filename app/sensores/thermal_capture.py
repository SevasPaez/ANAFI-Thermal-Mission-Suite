import os
import time
import tempfile

import olympe
from olympe.media import download_media, indexing_state
from olympe.messages.camera import photo_progress, set_camera_mode, set_photo_mode, take_photo
from olympe.messages.thermal import (
    set_emissivity,
    set_mode,
    set_palette_settings,
    set_rendering,
    set_sensitivity,
)

from sensores.drone_client import get_connected

PNG_SIG = b"\x89PNG\r\n\x1a\n"

def _is_radiometric_jpg(path: str) -> bool:

    try:
        with open(path, "rb") as f:
            b = f.read()
        return (b.find(PNG_SIG) != -1) and (b.find(b"PARROT") != -1)
    except Exception:
        return False

def _pick_radiometric_file(download_dir: str) -> str:

    candidates = []
    for root, _, files in os.walk(download_dir):
        for fn in files:
            p = os.path.join(root, fn)
            ext = os.path.splitext(p)[1].lower()
            if ext not in (".jpg", ".jpeg"):
                continue
            try:
                sz = os.path.getsize(p)
            except OSError:
                sz = 0
            if _is_radiometric_jpg(p):
                candidates.append((p, sz))

    if not candidates:
        raise FileNotFoundError("No se encontró un JPG radiométrico en la descarga")

    candidates.sort(key=lambda t: t[1], reverse=True)
    return candidates[0][0]

def _score_dng_candidate(path: str) -> float:

    try:
        sz = os.path.getsize(path)
    except OSError:
        sz = 0

    score = float(sz) / 1024.0

    try:

        with open(path, "rb") as f:
            head = f.read(512 * 1024)
            if sz > 512 * 1024:
                f.seek(max(0, sz - 512 * 1024))
                tail = f.read(512 * 1024)
            else:
                tail = b""
        blob = head + tail

        if PNG_SIG in blob:
            score += 100000.0
        if b"PARROT" in blob:
            score += 5000.0
        if blob.startswith(b"\xff\xd8"):
            score += 2000.0
        if blob.startswith(b"II*\x00") or blob.startswith(b"MM\x00*"):
            score += 1500.0
    except Exception:
        pass

    return score

def _pick_best_radiometric_dng(download_dir: str) -> str:

    candidates = []
    for root, _, files in os.walk(download_dir):
        for fn in files:
            p = os.path.join(root, fn)
            if os.path.splitext(p)[1].lower() != ".dng":
                continue
            candidates.append((p, _score_dng_candidate(p)))

    if not candidates:
        raise FileNotFoundError("No se encontró ningún .DNG en la descarga")

    candidates.sort(key=lambda t: t[1], reverse=True)
    return candidates[0][0]

def take_thermal_photo(drone=None, capture_root="."):
    if drone is None:
        drone = get_connected()

    try:
        from olympe.messages.thermal import mode as thermal_mode

        cur_mode = drone.get_state(thermal_mode).get("mode")
    except Exception:
        cur_mode = None

    assert drone.media(indexing_state(state="indexed")).wait(_timeout=60).success()

    drone(set_mode(mode="standard")).wait()
    drone(set_rendering(mode="thermal", blending_rate=0)).wait()
    drone(
        set_palette_settings(
            mode="absolute",
            lowest_temp=274,
            highest_temp=314,
            outside_colorization="limited",
            relative_range="locked",
            spot_type="hot",
            spot_threshold=290,
        )
    ).wait()
    drone(set_sensitivity(range="low")).wait()
    drone(set_emissivity(emissivity=1)).wait()

    drone(set_camera_mode(cam_id=1, value="photo")).wait()
    drone(
        set_photo_mode(
            cam_id=1,
            mode="single",
            format="rectilinear",
            file_format="dng_jpeg",
            burst="burst_14_over_1s",
            bracketing="preset_1ev",
            capture_interval=0.0,
        )
    ).wait().success()

    photo_saved = drone(photo_progress(result="photo_saved", _policy="wait"))
    drone(take_photo(cam_id=1)).wait()
    if not photo_saved.wait(_timeout=30).success():
        raise RuntimeError("take_photo timeout")
    media_id = photo_saved.received_events().last().args["media_id"]

    drone.media.download_dir = tempfile.mkdtemp(prefix="pupi_thermal_")

    media_download = drone(download_media(media_id, integrity_check=True))
    if not media_download.wait(_timeout=60).success():
        raise RuntimeError("download_media timeout")

    ts = time.strftime("%Y%m%d_%H%M%S")
    photos_dir = os.path.join(capture_root, "thermal", "photos")
    os.makedirs(photos_dir, exist_ok=True)
    fname = f"thermal_{ts}.JPG"
    out_path = os.path.join(photos_dir, fname)

    from sensores.media_utils import copy_as, pick_best_downloaded_file

    try:
        best = _pick_radiometric_file(drone.media.download_dir)
    except Exception:

        best = pick_best_downloaded_file(
            drone.media.download_dir,
            prefer_exts=(".jpg", ".jpeg", ".png"),
        )
    copy_as(best, out_path)

    try:
        best_dng = _pick_best_radiometric_dng(drone.media.download_dir)
    except Exception:
        try:
            best_dng = pick_best_downloaded_file(drone.media.download_dir, prefer_exts=(".dng",))
        except Exception:
            best_dng = None

    if best_dng:
        dng_out = os.path.splitext(out_path)[0] + ".DNG"
        copy_as(best_dng, dng_out)

    try:
        from sensores.thermal_matrix import get_or_create_thermal_matrices

        get_or_create_thermal_matrices(out_path)
    except Exception:
        pass

    try:
        if cur_mode is not None:
            drone(set_mode(cur_mode)).wait(2)
    except Exception:
        pass

    return out_path
