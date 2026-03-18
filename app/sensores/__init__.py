"""Paquete sensores.

Nota: evitamos importar módulos pesados (como olympe) en el import del paquete
para que utilidades ligeras (p.ej. exportación de metadatos) puedan usarse sin
requerir que el SDK esté disponible en ese momento.
"""

try:
    from .streams import SensorStream, FrameStream  # noqa: F401
except Exception:
    # Permitir que el paquete se importe aun si olympe no está instalado.
    SensorStream = None  # type: ignore
    FrameStream = None  # type: ignore
