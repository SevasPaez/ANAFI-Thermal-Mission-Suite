import os
import time
import threading
from datetime import datetime
from urllib.parse import urljoin, urlparse

HAVE_OLYMPE = False
try:
    import olympe
    from olympe.messages.camera import (
        set_camera_mode, set_photo_mode, take_photo,
        start_recording, stop_recording
    )
    HAVE_OLYMPE = True
except Exception:
    HAVE_OLYMPE = False

try:
    import requests
except Exception:
    requests = None

class CameraControl:
    def __init__(self, drone=None, media_dir="./media", http_base=None):
        self.drone = drone
        self.media_dir = media_dir
        os.makedirs(self.media_dir, exist_ok=True)
        self.http_base = http_base
        self._sess = requests.Session() if requests else None

    def _run_async(self, fn, *args, **kwargs):
        threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()

    def _now_ts(self):
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def _ensure_media_server(self):
        if not self._sess:
            return False
        candidates = []
        if self.http_base:
            candidates.append(self.http_base)

        for b in ("http://192.168.53.1", "http://192.168.53.1"):
            if b not in candidates:
                candidates.append(b)
        for base in candidates:
            try:
                url = urljoin(base, "/api/v1/media/medias")
                r = self._sess.get(url, timeout=3)
                if r.ok:
                    self.http_base = base
                    return True
            except Exception:
                pass
        return False

    def _list_medias(self):
        if not self._sess:
            return []
        if not self.http_base and not self._ensure_media_server():
            return []
        url = urljoin(self.http_base, "/api/v1/media/medias")
        r = self._sess.get(url, timeout=5)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _media_type_str(m):
        t = (m.get("type") or "").lower()
        if t in ("image", "photo"):
            return "IMAGE"
        return "VIDEO" if t == "video" else t.upper()

    def _latest_since(self, medias_before, kind, t_start):
        before_ids = {mb.get("media_id") or mb.get("id") for mb in (medias_before or [])}
        medias = self._list_medias()
        cands = []
        for m in medias:
            if self._media_type_str(m) != kind:
                continue
            mid = m.get("media_id") or m.get("id")
            if mid and mid not in before_ids:
                cands.append(m)
            else:
                when = m.get("datetime") or m.get("creation_date") or m.get("date") or ""
                if when and when > t_start:
                    cands.append(m)
        def _when(m):
            return m.get("datetime") or m.get("creation_date") or m.get("date") or ""
        cands.sort(key=_when, reverse=True)
        return cands[0] if cands else None

    def _pick_resource(self, media, prefer_ext=None):
        resources = media.get("resources") or []
        if not resources:
            return None
        if prefer_ext:
            pref = prefer_ext.lower().lstrip(".")
            for r in resources:
                fmt = (r.get("format") or "").lower()
                ext = os.path.splitext(urlparse(r.get("url", "")).path)[1].lower().lstrip(".")
                if fmt == pref or ext == pref:
                    return r
        return resources[0]

    def _download_resource_atomic(self, res_url, out_stem, ext_guess):
        if not self._sess:
            return None
        if not self.http_base and not self._ensure_media_server():
            return None
        full = urljoin(self.http_base, res_url)
        parsed = urlparse(full)
        ext = os.path.splitext(parsed.path)[1] or ext_guess
        out_final = os.path.join(self.media_dir, f"{out_stem}{ext}")
        out_part = out_final + ".part"
        with self._sess.get(full, stream=True, timeout=30) as resp:
            resp.raise_for_status()
            with open(out_part, "wb") as f:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
        os.replace(out_part, out_final)
        return out_final

    def _download_after_index(self, kind, timeout_s=12.0, poll_every=0.35):

        t_start_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        medias_before = self._list_medias()
        t0

