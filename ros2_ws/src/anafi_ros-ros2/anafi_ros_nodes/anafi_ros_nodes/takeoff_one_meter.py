#!/usr/bin/env python3
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy

from std_srvs.srv import Trigger
from std_msgs.msg import Bool, String, Float32
from anafi_ros_interfaces.msg import MoveByCommand


# QoS según `ros2 topic info -v`
# /anafi/drone/altitude  -> BEST_EFFORT
# /anafi/drone/steady    -> BEST_EFFORT
# /anafi/drone/state     -> RELIABLE
QOS_ALT = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

QOS_STEADY = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

QOS_STATE = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)


class TakeoffOneMeter(Node):
    def __init__(self):
        super().__init__("takeoff_one_meter")

        # Nombres relativos (si el launch usa namespace=/anafi, quedan como /anafi/drone/...)
        self.takeoff_cli = self.create_client(Trigger, "drone/takeoff")

        # Publicador de MoveBy (QoS por defecto: RELIABLE, depth=10)
        self.moveby_pub = self.create_publisher(MoveByCommand, "drone/moveby", 10)

        # Telemetría
        self.state = None         # str
        self.steady = None        # bool
        self.altitude = None      # float

        # Suscripciones con QoS correcto (para evitar el warning de QoS incompatible)
        self.create_subscription(String, "drone/state", self._state_cb, QOS_STATE)
        self.create_subscription(Bool, "drone/steady", self._steady_cb, QOS_STEADY)
        self.create_subscription(Float32, "drone/altitude", self._alt_cb, QOS_ALT)

    def _state_cb(self, msg: String):
        if msg.data != self.state:
            self.get_logger().info(f"[STATE] {self.state} -> {msg.data}")
        self.state = msg.data

    def _steady_cb(self, msg: Bool):
        new_val = bool(msg.data)
        if new_val != self.steady:
            self.get_logger().info(f"[STEADY] {self.steady} -> {new_val}")
        self.steady = new_val

    def _alt_cb(self, msg: Float32):
        self.altitude = float(msg.data)

    def fire_takeoff(self) -> bool:
        """Llama takeoff sin bloquearse si el servicio tarda en responder."""
        if not self.takeoff_cli.wait_for_service(timeout_sec=30.0):
            self.get_logger().error("Servicio takeoff no disponible: drone/takeoff")
            return False

        future = self.takeoff_cli.call_async(Trigger.Request())

        # Espera corta: si responde rápido, perfecto; si no, seguimos
        rclpy.spin_until_future_complete(self, future, timeout_sec=1.0)

        if future.result() is not None:
            res = future.result()
            self.get_logger().info(f"takeoff reply: success={res.success}, message='{res.message}'")
        else:
            self.get_logger().warn("takeoff enviado (sin respuesta rápida). Continuo...")

        return True

    @staticmethod
    def _looks_flying(state: str) -> bool:
        """Heurística de 'ya está volando/hover' basada en strings de state."""
        if not state:
            return False
        s = state.lower()
        keywords = ["takingoff", "takeoff", "hover", "flying", "airborne"]
        return any(k in s for k in keywords)

    def wait_after_takeoff(self, timeout_sec: float = 45.0) -> None:
        """
        Espera post-takeoff hasta detectar que ya está en aire/hover (por altitude/state/steady).
        Si no llega telemetría, continúa por tiempo.
        """
        start = time.time()
        last_print = 0.0

        while rclpy.ok() and (time.time() - start) < timeout_sec:
            rclpy.spin_once(self, timeout_sec=0.2)

            now = time.time()
            if now - last_print > 1.0:
                self.get_logger().info(
                    f"Post-takeoff... state='{self.state}', steady={self.steady}, alt={self.altitude}"
                )
                last_print = now

            # 1) condición más directa: altitud suficiente
            if self.altitude is not None and self.altitude >= 0.7:
                self.get_logger().info(f"Detectado en aire por altitud: {self.altitude:.2f} m")
                return

            # 2) por state
            if self._looks_flying(self.state):
                self.get_logger().info(f"Detectado en aire por state: '{self.state}'")
                return

            # 3) por steady (después de unos segundos)
            if self.steady is True and (time.time() - start) > 3.0:
                self.get_logger().info("Detectado estable (steady=True).")
                return

        self.get_logger().warn("No pude confirmar aire/hover por telemetría; continuaré por tiempo fijo.")

    def send_moveby_up_1m(self):
        msg = MoveByCommand()
        msg.dx = 0.0
        msg.dy = 0.0
        msg.dz = -1.0  # subir 1m (en Parrot Z+ es hacia abajo)
        msg.dyaw = 0.0
        self.get_logger().info("Enviando moveby: subir 1.0m (dz=-1.0)")
        self.moveby_pub.publish(msg)

    def run(self):
        # Espera “simple” para que anafi conecte y publique topics/servicios estables
        self.get_logger().info("Esperando 12s para que el nodo anafi conecte y estabilice...")
        time.sleep(12.0)

        # 1) Takeoff
        self.get_logger().info("Llamando takeoff...")
        if not self.fire_takeoff():
            return

        # 2) Espera post-takeoff (ya aquí deben aparecer state/steady/alt si todo está ok)
        self.get_logger().info("Esperando post-takeoff para detectar aire/hover...")
        self.wait_after_takeoff(timeout_sec=45.0)

        # 3) Subir 1m
        self.send_moveby_up_1m()

        # Mantener vivo un poquito para asegurar publicación
        time.sleep(3.0)


def main():
    rclpy.init()
    node = TakeoffOneMeter()
    try:
        node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
