from __future__ import annotations

import argparse
import signal
import sys
import time

from sensores.streams import SensorStream

from .telemetry_bridge import ROS2_AVAILABLE, Ros2TelemetryBridge


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ip", default=None, help="Drone IP (default: config.DRONE_IP)")
    p.add_argument("--hz", type=float, default=10.0, help="Publish rate (Hz)")
    p.add_argument("--namespace", default="/anafi", help="ROS2 namespace (default: /anafi)")
    args = p.parse_args()

    if not ROS2_AVAILABLE:
        print("ROS2 (rclpy) no está disponible. ¿Sourcaste ROS2?", file=sys.stderr)
        return 2

    stream = SensorStream(args.ip) if args.ip else SensorStream()
    bridge = Ros2TelemetryBridge(namespace=args.namespace)

    running = True

    def _sigint(_sig, _frm):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _sigint)

    print("[bridge] Conectando sensores (Olympe)…")
    stream.start()

    print("[bridge] Iniciando ROS2 publishers…")
    bridge.start()

    period = 1.0 / max(1e-3, float(args.hz))
    print(f"[bridge] Publicando a {args.hz} Hz. Ctrl+C para salir.")

    try:
        while running:
            snap = stream.latest
            if snap is not None:
                bridge.publish_snapshot(snap)
            time.sleep(period)
    finally:
        print("[bridge] Deteniendo…")
        bridge.stop()
        stream.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
