from __future__ import annotations

import os
from pathlib import Path


DRONE_IP = "192.168.53.1"   # Skycontroller; directo al dron: 192.168.42.1
REFRESH_MS = 500            # ms
PATH_MAX_POINTS = 2000
CUBE_SIZE = 0.35
DT_FALLBACK = REFRESH_MS / 1000.0

APP_TITLE = "ANAFI Thermal - Dashboard de Sensores (Modern GUI)"
WINDOW_GEOM = "1100x740"


def _looks_like_suite_root(path: Path) -> bool:
    return (path / "app" / "main.py").exists() and (path / "ros2_ws").exists()


def _discover_suite_root() -> str:
    env = os.environ.get("ANAFI_SUITE_ROOT", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if _looks_like_suite_root(p):
            return str(p)

    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if _looks_like_suite_root(parent):
            return str(parent)

    return str(here.parent)


SUITE_ROOT = _discover_suite_root()
APP_ROOT = str(Path(__file__).resolve().parent)
MEDIA_ROOT = os.path.join(APP_ROOT, "media")
RUNTIME_ROOT = os.path.join(SUITE_ROOT, "runtime")
CURRENT_MISSION_JSON = os.path.join(RUNTIME_ROOT, "current_mission.json")
LOCAL_ROS2_WS = os.path.join(SUITE_ROOT, "ros2_ws")
LOCAL_ROS2_INSTALL = os.path.join(LOCAL_ROS2_WS, "install")

VIDEO_URL = f"http://{DRONE_IP}:80/live"
THERMAL_URL = f"http://{DRONE_IP}:80/thermal"
THERMAL_HTTP_URL = THERMAL_URL

SENSOR_HZ = 20
CAMERA_FPS = 30

DRONE_RTSP_URL = f"rtsp://{DRONE_IP}/live"
DRONE_RTSP_URL_THERMAL = DRONE_RTSP_URL

RTSP_TRANSPORT = "udp"
RTSP_STIMEOUT_MS = 10000
RTSP_MAX_DELAY_US = 1000000
RTSP_NO_BUFFER = True
RTSP_FPS_HINT = 120

ROS2_SETUP_SCRIPTS = [
    "/opt/ros/humble/setup.bash",
    os.path.join(LOCAL_ROS2_INSTALL, "setup.bash"),
    os.path.join(LOCAL_ROS2_INSTALL, "local_setup.bash"),
    os.path.expanduser("~/ros2_ws/install/setup.bash"),
    os.path.expanduser("~/ros2_ws/install/local_setup.bash"),
    os.path.expanduser("~/anafi_ws/install/setup.bash"),
    os.path.expanduser("~/anafi_ws/install/local_setup.bash"),
    os.path.expanduser("~/Downloads/anafi_ws/install/setup.bash"),
    os.path.expanduser("~/Downloads/anafi_ws/install/local_setup.bash"),
    os.path.expanduser("~/Documents/anafi_ws/install/setup.bash"),
    os.path.expanduser("~/Documents/anafi_ws/install/local_setup.bash"),
]
