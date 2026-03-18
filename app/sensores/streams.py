
import threading
import time
from typing import Optional
import cv2 as cv

from .drone_client import DroneClient, SensorSnapshot
from config import DRONE_IP, SENSOR_HZ

class SensorStream:
    def __init__(self, ip: str = DRONE_IP):
        self.client = DroneClient(ip)
        self._lock = threading.Lock()
        self._latest: Optional[SensorSnapshot] = None
        self._running = False
        self._th: Optional[threading.Thread] = None

    @property
    def latest(self) -> Optional[SensorSnapshot]:
        with self._lock:
            return self._latest

    def start(self):
        if self._running:
            return
        self.client.connect()
        self._running = True
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def _loop(self):
        period = 1.0 / max(1, SENSOR_HZ)
        while self._running:
            try:
                snap = self.client.snapshot()
                with self._lock:
                    self._latest = snap
            except Exception:

                pass
            time.sleep(period)

    def stop(self):
        self._running = False
        try:
            self.client.disconnect()
        except Exception:
            pass

class FrameStream:
    def __init__(self, url: str, fps: int = 30):
        self.url = url
        self.fps = fps
        self.cap: Optional[cv.VideoCapture] = None
        self._lock = threading.Lock()
        self._latest = None
        self._running = False
        self._th: Optional[threading.Thread] = None
        self._use_mjpeg = False

    def start(self):
        if self._running:
            return
        self._running = True

        try:
            self.cap = cv.VideoCapture(self.url, cv.CAP_FFMPEG)
            if self.cap is not None and self.cap.isOpened():
                self.cap.set(cv.CAP_PROP_BUFFERSIZE, 1)
                self._th = threading.Thread(target=self._loop_cv, daemon=True)
                self._th.start()
                return
        except Exception:
            pass

        try:
            self.cap = cv.VideoCapture(self.url)
            if self.cap is not None and self.cap.isOpened():
                self.cap.set(cv.CAP_PROP_BUFFERSIZE, 1)
                self._th = threading.Thread(target=self._loop_cv, daemon=True)
                self._th.start()
                return
        except Exception:
            pass

        if self.url.startswith("http"):
            self._use_mjpeg = True
            self._th = threading.Thread(target=self._loop_mjpeg, daemon=True)
            self._th.start()
            return

        self._running = False
        raise RuntimeError(f"No se pudo abrir el stream: {self.url}")

    def _loop_cv(self):
        import time as _time
        period = 1.0 / max(1, self.fps)
        while self._running:
            if self.cap is None:
                break
            ok, frame = self.cap.read()
            if ok and frame is not None:
                with self._lock:
                    self._latest = frame
            else:
                _time.sleep(0.05)
            _time.sleep(period)

    def _loop_mjpeg(self):
        import time as _time
        import urllib.request
        import numpy as np
        period = 1.0 / max(1, self.fps)
        req = urllib.request.Request(self.url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                buf = b""
                while self._running:
                    chunk = resp.read(4096)
                    if not chunk:
                        _time.sleep(0.01)
                        continue
                    buf += chunk

                    while True:
                        start = buf.find(b"\xff\xd8")
                        end = buf.find(b"\xff\xd9")
                        if start != -1 and end != -1 and end > start:
                            jpg = buf[start:end+2]
                            buf = buf[end+2:]
                            arr = np.frombuffer(jpg, dtype=np.uint8)
                            frame = cv.imdecode(arr, cv.IMREAD_COLOR)
                            if frame is not None:
                                with self._lock:
                                    self._latest = frame

                        else:
                            break
                    _time.sleep(period)
        except Exception:
            self._running = False

    def read_latest(self):
        with self._lock:
            return None if self._latest is None else self._latest.copy()

    def stop(self):
        self._running = False
        try:
            if self.cap is not None:
                self.cap.release()
        except Exception:
            pass
        self.cap = None
