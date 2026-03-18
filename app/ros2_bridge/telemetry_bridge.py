"""Publish Olympe telemetry into ROS2 topics.

Design goals:
- Do NOT depend on camera/video metadata (works even if RTSP fails).
- Publish to the *same* topic names used by `anafi_ros_nodes` so your existing
  ROS2 tools/nodes keep working (e.g. `/anafi/drone/altitude`).
- Keep QoS compatible with the original driver:
  - Sensor topics: BEST_EFFORT (qos_profile_sensor_data)
  - State/battery: RELIABLE (depth=1)

This module is used by the GUI page `ROS2 Bridge`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

ROS2_AVAILABLE = False

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
    from rclpy.qos import qos_profile_sensor_data

    from std_msgs.msg import Bool, Float32, String, UInt8
    from geometry_msgs.msg import QuaternionStamped, Vector3Stamped
    from sensor_msgs.msg import NavSatFix, NavSatStatus

    ROS2_AVAILABLE = True
except Exception:
    ROS2_AVAILABLE = False


@dataclass
class BridgeStats:
    published_msgs: int = 0
    last_state: str = ""



def _normalize_flight_state(state) -> str:
    """Map Olympe flying state to anafi_ros_nodes-style strings.

    anafi_autonomy expects: LANDED, TAKINGOFF, HOVERING, FLYING, LANDING, EMERGENCY, ...
    """
    if state is None:
        return ""
    s = str(state)
    # Olympe enums often look like 'FlyingStateChanged_State.landed'
    if "." in s:
        tail = s.split(".")[-1]
    else:
        tail = s
    tail = tail.strip().lower()
    mapping = {
        "landed": "LANDED",
        "takingoff": "TAKINGOFF",
        "hovering": "HOVERING",
        "flying": "FLYING",
        "landing": "LANDING",
        "emergency": "EMERGENCY",
        "user_takeoff": "USER_TAKEOFF",
        "motor_ramping": "MOTOR_RAMPING",
        "invalid": "INVALID",
    }
    return mapping.get(tail, tail.upper())


def _rpy_to_quaternion(roll: float, pitch: float, yaw: float):
    """Convert roll/pitch/yaw (rad) to quaternion (x,y,z,w)."""
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)

    qw = cr * cp * cy + sr * sp * sy
    qx = sr * cp * cy - cr * sp * sy
    qy = cr * sp * cy + sr * cp * sy
    qz = cr * cp * sy - sr * sp * cy
    return qx, qy, qz, qw


class Ros2TelemetryBridge:
    """Minimal ROS2 publisher that mirrors Olympe telemetry to ROS2 topics."""

    def __init__(
        self,
        namespace: str = "/anafi",
        node_name: str = "olympe_telemetry_bridge",
    ) -> None:
        self.namespace = namespace.rstrip("/")
        self.node_name = node_name

        self._node: Optional[Node] = None

        self._pub_altitude = None
        self._pub_state = None
        self._pub_steady = None
        self._pub_batt = None
        self._pub_attitude = None
        self._pub_rpy = None
        self._pub_speed = None
        self._pub_gps_fix = None
        self._pub_gps_sats = None
        self._pub_gps_location = None

        self.stats = BridgeStats()
        # Optional callback to handle /anafi/drone/action commands (UInt8)
        # Set from the GUI: bridge.on_action = lambda code: ...
        self.on_action = None
        self._sub_action = None

    @property
    def is_running(self) -> bool:
        return self._node is not None

    def start(self) -> None:
        if not ROS2_AVAILABLE:
            raise RuntimeError("ROS2 (rclpy) no está disponible. ¿Sourcaste ROS2?")

        if self._node is not None:
            return

        # It's OK to call init() once per process.
        if not rclpy.ok():
            rclpy.init(args=None)

        # QoS to match anafi_ros_nodes behavior.
        qos_reliable_1 = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        self._node = rclpy.create_node(self.node_name, namespace=self.namespace)

        # Publishers (topic names follow anafi_ros_nodes convention)
        self._pub_altitude = self._node.create_publisher(Float32, "drone/altitude", qos_profile_sensor_data)
        self._pub_state = self._node.create_publisher(String, "drone/state", qos_reliable_1)
        self._pub_steady = self._node.create_publisher(Bool, "drone/steady", qos_profile_sensor_data)
        self._pub_batt = self._node.create_publisher(UInt8, "battery/percentage", qos_reliable_1)

        self._pub_attitude = self._node.create_publisher(QuaternionStamped, "drone/attitude", qos_profile_sensor_data)
        self._pub_rpy = self._node.create_publisher(Vector3Stamped, "drone/rpy", qos_profile_sensor_data)
        self._pub_speed = self._node.create_publisher(Vector3Stamped, "drone/speed", qos_profile_sensor_data)

        self._pub_gps_fix = self._node.create_publisher(Bool, "drone/gps/fix", qos_reliable_1)
        self._pub_gps_sats = self._node.create_publisher(UInt8, "drone/gps/satellites", qos_reliable_1)
        self._pub_gps_location = self._node.create_publisher(NavSatFix, "drone/gps/location", qos_profile_sensor_data)

        # Subscriber for action commands (matches anafi_autonomy contract)
        # /anafi/drone/action: UInt8
        self._sub_action = self._node.create_subscription(
            UInt8,
            "drone/action",
            self._on_action_msg,
            qos_profile_sensor_data,
        )

    def _on_action_msg(self, msg: UInt8) -> None:
        """Handle incoming /anafi/drone/action codes.

        NOTE: This requires spinning the node. We call rclpy.spin_once()
        periodically from publish_snapshot() so this callback can fire even
        inside the Tkinter app.
        """
        try:
            code = int(msg.data)
        except Exception:
            return
        cb = getattr(self, "on_action", None)
        if cb is None:
            return
        try:
            cb(code)
        except Exception:
            # Never crash the ROS thread because of UI callback errors
            return


    def stop(self) -> None:
        if not ROS2_AVAILABLE:
            return
        if self._node is None:
            return

        try:
            self._node.destroy_node()
        except Exception:
            pass
        self._node = None

        # Do NOT shutdown rclpy globally: the GUI may create other ROS nodes later.
        # If you prefer full shutdown, call rclpy.shutdown() at app exit.

    def publish_snapshot(self, snap) -> None:
        """Publish telemetry.

        Expected `snap` fields are compatible with `sensores.drone_client.SensorSnapshot`:
        - flight_state (str)
        - battery_percent (float)
        - roll, pitch, yaw (rad)
        - alt_rel (m)
        - vx, vy, vz (m/s)
        - lat, lon, alt_gps
        - gps_fix (bool)
        - num_sats (int)
        """
        if self._node is None:
            return

        # Allow ROS2 to process subscriptions (e.g. /anafi/drone/action) even
        # though this bridge runs inside a Tkinter app.
        try:
            rclpy.spin_once(self._node, timeout_sec=0.0)
        except Exception:
            pass

        now = self._node.get_clock().now().to_msg()

        # --- State ---
        if snap.flight_state is not None:
            msg_state = String()
            msg_state.data = str(snap.flight_state)
            self._pub_state.publish(msg_state)
            self.stats.last_state = msg_state.data

        # --- Battery ---
        if snap.battery_percent is not None:
            msg_b = UInt8()
            v = int(round(float(snap.battery_percent)))
            msg_b.data = max(0, min(100, v))
            self._pub_batt.publish(msg_b)

        # --- Altitude ---
        if snap.alt_rel is not None:
            msg_alt = Float32()
            msg_alt.data = float(snap.alt_rel)
            self._pub_altitude.publish(msg_alt)

        # --- RPY + Attitude (Quaternion) ---
        if (snap.roll is not None) and (snap.pitch is not None) and (snap.yaw is not None):
            roll = float(snap.roll)
            pitch = float(snap.pitch)
            yaw = float(snap.yaw)

            msg_rpy = Vector3Stamped()
            msg_rpy.header.stamp = now
            msg_rpy.header.frame_id = "base_link"
            msg_rpy.vector.x = roll
            msg_rpy.vector.y = pitch
            msg_rpy.vector.z = yaw
            self._pub_rpy.publish(msg_rpy)

            qx, qy, qz, qw = _rpy_to_quaternion(roll, pitch, yaw)
            msg_q = QuaternionStamped()
            msg_q.header.stamp = now
            msg_q.header.frame_id = "base_link"
            msg_q.quaternion.x = float(qx)
            msg_q.quaternion.y = float(qy)
            msg_q.quaternion.z = float(qz)
            msg_q.quaternion.w = float(qw)
            self._pub_attitude.publish(msg_q)

        # --- Speed ---
        if (snap.vx is not None) and (snap.vy is not None) and (snap.vz is not None):
            msg_v = Vector3Stamped()
            msg_v.header.stamp = now
            msg_v.header.frame_id = "base_link"
            msg_v.vector.x = float(snap.vx)
            msg_v.vector.y = float(snap.vy)
            msg_v.vector.z = float(snap.vz)
            self._pub_speed.publish(msg_v)

        # --- GPS ---
        if snap.gps_fix is not None:
            msg_fix = Bool()
            msg_fix.data = bool(snap.gps_fix)
            self._pub_gps_fix.publish(msg_fix)

        if snap.num_sats is not None:
            msg_s = UInt8()
            msg_s.data = max(0, min(255, int(snap.num_sats)))
            self._pub_gps_sats.publish(msg_s)

        if (snap.lat is not None) and (snap.lon is not None):
            msg_gps = NavSatFix()
            msg_gps.header.stamp = now
            msg_gps.header.frame_id = "gps"
            msg_gps.status = NavSatStatus(
                status=NavSatStatus.STATUS_FIX if bool(snap.gps_fix) else NavSatStatus.STATUS_NO_FIX,
                service=NavSatStatus.SERVICE_GPS,
            )
            msg_gps.latitude = float(snap.lat)
            msg_gps.longitude = float(snap.lon)
            msg_gps.altitude = float(snap.alt_gps) if snap.alt_gps is not None else 0.0
            self._pub_gps_location.publish(msg_gps)

        # --- Steady (heurística simple) ---
        steady = False
        try:
            if snap.flight_state in ("hovering", "landed"):
                steady = True
            elif (snap.vx is not None) and (snap.vy is not None) and (snap.vz is not None):
                steady = (abs(float(snap.vx)) < 0.05 and abs(float(snap.vy)) < 0.05 and abs(float(snap.vz)) < 0.05)
        except Exception:
            steady = False

        msg_st = Bool()
        msg_st.data = bool(steady)
        self._pub_steady.publish(msg_st)

        self.stats.published_msgs += 1
