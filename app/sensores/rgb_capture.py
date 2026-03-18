import os
import time
import tempfile

try:
    import olympe
    from olympe.media import indexing_state, download_media
    from olympe.messages.camera import set_camera_mode, set_photo_mode, take_photo, photo_progress
except Exception:
    olympe = None  # type: ignore

from sensores.drone_client import get_connected
from sensores.media_utils import pick_best_downloaded_file, copy_as

def take_rgb_photo(drone=None, capture_root=".") -> str:
    '''
    Toma una foto RGB (cam_id=0) SIN depender de RTSP.
    Descarga el archivo vía Olympe media.download_media y lo copia a:
      <capture_root>/rgb/photos/rgb_<timestamp>.jpg
    '''
    if drone is None:
        drone = get_connected()
    if olympe is None:
        raise RuntimeError("Olympe no está disponible")

    assert drone.media(indexing_state(state="indexed")).wait(_timeout=60).success()

    drone(set_camera_mode(cam_id=0, value="photo")).wait()
    drone(set_photo_mode(
        cam_id=0,
        mode="single",
        format="rectilinear",
        file_format="jpeg",
        burst="burst_14_over_1s",
        bracketing="preset_1ev",
        capture_interval=0.0,
    )).wait()

    photo_saved = drone(photo_progress(result="photo_saved", _policy="wait"))
    drone(take_photo(cam_id=0)).wait()
    if not photo_saved.wait(_timeout=30).success():
        raise RuntimeError("photo_saved timeout")
    media_id = photo_saved.received_events().last().args["media_id"]

    drone.media.download_dir = tempfile.mkdtemp(prefix="pupi_rgb_")
    media_download = drone(download_media(media_id, integrity_check=True))
    if not media_download.wait(_timeout=60).success():
        raise RuntimeError("download_media timeout")

    best = pick_best_downloaded_file(drone.media.download_dir, prefer_exts=(".jpg", ".jpeg", ".png"))
    ts = time.strftime("%Y%m%d_%H%M%S")
    photos_dir = os.path.join(capture_root, "rgb", "photos")
    out_path = os.path.join(photos_dir, f"rgb_{ts}.jpg")
    copy_as(best, out_path)
    return out_path
