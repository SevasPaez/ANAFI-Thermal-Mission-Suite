
import os
import cv2 as cv
import threading
import time

class RstpThreaded:
    def __init__(self, url: str, transport: str = "udp", fps_hint: int = 30):
        self.url = url
        self.transport = transport.lower()
        self.fps_hint = int(fps_hint)

        self.cap = None
        self._running = False
        self._th = None

        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._latest = None
        self._seq = 0

        self._err_count = 0
        self._last_ok_ts = 0.0

    def _set_ffmpeg_env(self):

        transport = 'tcp' if self.transport == 'tcp' else 'udp'

        stimeout_us = 10_000_000
        max_delay_us = 1_000_000
        no_buffer = True
        try:
            from config import RTSP_STIMEOUT_MS, RTSP_MAX_DELAY_US, RTSP_NO_BUFFER

            stimeout_us = int(RTSP_STIMEOUT_MS) * 1000
            max_delay_us = int(RTSP_MAX_DELAY_US)
            no_buffer = bool(RTSP_NO_BUFFER)
        except Exception:
            pass

        opts = [
            f"rtsp_transport;{transport}",
            f"stimeout;{stimeout_us}",
            f"max_delay;{max_delay_us}",
        ]
        if no_buffer:

            opts += ["fflags;nobuffer", "flags;low_delay", "reorder_queue_size;0"]

        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "|".join(opts)

    def start(self):
        if self._running:
            return
        self._set_ffmpeg_env()
        self._running = True
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def _open_cap(self):
        cap = cv.VideoCapture(self.url, cv.CAP_FFMPEG)
        if cap is None or not cap.isOpened():
            return None
        cap.set(cv.CAP_PROP_BUFFERSIZE, 1)
        if self.fps_hint > 0:
            cap.set(cv.CAP_PROP_FPS, float(self.fps_hint))
        return cap

    def _loop(self):
        backoff = 0.5
        try:
            self.cap = self._open_cap()
            self._last_ok_ts = time.time()
            while self._running:
                if self.cap is None:
                    time.sleep(backoff)
                    backoff = min(4.0, backoff * 2.0)
                    if not self._running:
                        break
                    self.cap = self._open_cap()
                    continue

                ok, frame = self.cap.read()
                if ok and frame is not None:
                    with self._cond:
                        self._latest = frame
                        self._seq += 1
                        self._cond.notify_all()
                    self._last_ok_ts = time.time()
                    self._err_count = 0
                    backoff = 0.5
                else:
                    self._err_count += 1
                    time.sleep(0.001)

                if (time.time() - self._last_ok_ts) > 1.0 or self._err_count > 30:
                    try:
                        if self.cap is not None:
                            self.cap.release()
                    except Exception:
                        pass
                    self.cap = None

                if self.fps_hint > 0:
                    time.sleep(max(0.0, 1.0 / self.fps_hint))
        finally:

            try:
                if self.cap is not None:
                    self.cap.release()
            except Exception:
                pass
            self.cap = None

    def read_latest(self):
        with self._lock:
            return None if self._latest is None else self._latest.copy()

    def wait_next(self, last_seq: int, timeout_ms: int = 50):
        deadline = time.time() + (timeout_ms / 1000.0)
        with self._cond:
            while self._running and self._seq <= last_seq and time.time() < deadline:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self._cond.wait(timeout=remaining)
            if self._seq > last_seq and self._latest is not None:
                return self._latest.copy(), self._seq
            return None, last_seq

    def stop(self):
        if not self._running and self._th is None:
            return

        self._running = False

        with self._cond:
            self._cond.notify_all()

        th = self._th

        if th is not None and th.is_alive() and threading.current_thread() is not th:
            th.join(timeout=2.0)

        if self.cap is not None and (th is None or not th.is_alive()):
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

        self._th = None
