
import time
from dataclasses import dataclass
from typing import Optional
import olympe

from .messages import (
    AttitudeChanged, AltitudeChanged, SpeedChanged, FlyingStateChanged, PositionChanged,
    GPSFixStateChanged, NumberOfSatelliteChanged, BatteryStateChanged
)
from .navigation import enu_from_llh, body_vel_to_world

@dataclass
class SensorSnapshot:
    flight_state: Optional[str]
    battery_percent: Optional[float]
    roll: Optional[float]
    pitch: Optional[float]
    yaw: Optional[float]
    alt_rel: Optional[float]
    vx: Optional[float]
    vy: Optional[float]
    vz: Optional[float]
    lat: Optional[float]
    lon: Optional[float]
    alt_gps: Optional[float]
    gps_fix: Optional[bool]
    num_sats: Optional[int]

class DroneClient:
    def __init__(self, ip: str):
        self._drone = olympe.Drone(ip)
        self.connected = False
        self.origin_llh = None
        self.last_update_time = None
        self.last_enu = (0.0, 0.0, 0.0)

    @property
    def drone(self):
        """Expose the underlying olympe.Drone instance.

        The GUI/ROS2 bridge should reuse the *same* Olympe connection used for
        telemetry polling. Creating a second Olympe connection can lead to link
        instability (e.g., ping failures/disconnects).
        """
        return self._drone

    def connect(self):
        self._drone.connect()
        self.connected = True
        self.origin_llh = None
        self.last_update_time = time.time()
        self.last_enu = (0.0, 0.0, 0.0)

    def disconnect(self):
        try:
            self._drone.disconnect()
        finally:
            self.connected = False

    def _get(self, msg, default=None):
        if not self.connected:
            return default
        try:
            st = self._drone.get_state(msg)
            return st if st is not None else default
        except Exception:
            return default

    def snapshot(self) -> SensorSnapshot:
        fs = self._get(FlyingStateChanged, {})
        batt = {}
        if BatteryStateChanged:
            batt = self._get(BatteryStateChanged, {})
        att = self._get(AttitudeChanged, {})
        alt = self._get(AltitudeChanged, {})
        spd = self._get(SpeedChanged, {})
        pos = self._get(PositionChanged, {})
        fix = self._get(GPSFixStateChanged, {})
        sats = self._get(NumberOfSatelliteChanged, {})

        return SensorSnapshot(
            flight_state=fs.get("state"),
            battery_percent=batt.get("percent", batt.get("battery_percentage")),
            roll=att.get("roll"), pitch=att.get("pitch"), yaw=att.get("yaw"),
            alt_rel=alt.get("altitude"),
            vx=spd.get("speedX"), vy=spd.get("speedY"), vz=spd.get("speedZ"),
            lat=pos.get("latitude"), lon=pos.get("longitude"), alt_gps=pos.get("altitude"),
            gps_fix=(fix.get("fixed") is not None and int(fix.get("fixed")) == 1),
            num_sats=sats.get("numberOfSatellite"),
        )

    def compute_enu(self, snap: SensorSnapshot, dt_fallback: float):
        now = time.time()
        dt = dt_fallback if self.last_update_time is None else max(0.05, now - self.last_update_time)
        self.last_update_time = now

        pos_enu = None
        if snap.gps_fix and (snap.lat is not None) and (snap.lon is not None) and (snap.alt_gps is not None):
            if self.origin_llh is None:
                self.origin_llh = (snap.lat, snap.lon, snap.alt_gps)
            lat0, lon0, alt0 = self.origin_llh
            pos_enu = enu_from_llh(snap.lat, snap.lon, snap.alt_gps, lat0, lon0, alt0)

        if pos_enu is None:
            vx = snap.vx or 0.0
            vy = snap.vy or 0.0
            vz = snap.vz or 0.0
            yaw = snap.yaw or 0.0
            vE, vN, vU = body_vel_to_world(vx, vy, vz, yaw)
            E0, N0, U0 = self.last_enu
            pos_enu = (E0 + vE * dt, N0 + vN * dt, U0 + vU * dt)

        self.last_enu = pos_enu
        return pos_enu


# Singleton helper compatible con integración de captura térmica
_drone_singleton = None
def get_connected(ip: str = None):
    global _drone_singleton
    if _drone_singleton is None:
        from config import DRONE_IP
        _drone_singleton = olympe.Drone(ip or DRONE_IP, media_port="80")
    if not _drone_singleton.connected:
        _drone_singleton.connect()
    return _drone_singleton
