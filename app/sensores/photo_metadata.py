"""sensores/photo_metadata.py

Registro y exportación de metadatos por fotografía.

Objetivo: cuando la interfaz toma fotos (RGB o térmicas), guardar un log
con información útil para el postprocesado y trazabilidad de la misión.

Campos principales:
- id/foto (nombre de archivo)
- GPS (lat/lon/alt)
- Hora (local y UTC)
- Tipo de foto (sensor / modo)

Exporta a CSV o Excel (.xlsx).
"""

from __future__ import annotations

import csv
import datetime as _dt
import os
from typing import Any, Dict, List, Optional


DEFAULT_COLUMNS = [
    "record_id",
    "mission_name",
    "waypoint_index",
    "sensor",
    "mode",
    "photo_id",
    "file_name",
    "file_path",
    "mapped_path",
    "captured_local",
    "captured_utc",
    "lat",
    "lon",
    "alt_gps_m",
    "alt_rel_m",
    "roll_rad",
    "pitch_rad",
    "yaw_rad",
    "battery_percent",
    "gps_fix",
    "num_sats",

    # --- Extra: análisis "Errores" (targets + ROI + hotspots)
    "targets_detected",
    "target_centroids_px",
    "roi_warp_path",
    "roi_warp_tempC_path",
    "hotspots_count",
    "hotspots_centroids_px",
    "hotspots_mask_path",
    "hotspots_overlay_path",
]


def _now_local() -> _dt.datetime:
    return _dt.datetime.now().astimezone()


def _iso(dt: _dt.datetime) -> str:
    # ISO-8601 con zona horaria
    return dt.isoformat(timespec="seconds")


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


class PhotoMetadataStore:
    """Acumula registros en memoria y los exporta a CSV/XLSX."""

    def __init__(self, media_root: str = "."):
        self.media_root = media_root
        self.output_dir = os.path.join(media_root, "metadata")
        _ensure_dir(self.output_dir)

        self.records: List[Dict[str, Any]] = []
        self._record_seq = 0
        self.current_mission_name: str = ""
        self.run_started_local: Optional[_dt.datetime] = None

    def clear(self) -> None:
        self.records.clear()
        self._record_seq = 0
        self.current_mission_name = ""
        self.run_started_local = None

    def start_run(self, mission_name: str) -> None:
        self.clear()
        self.current_mission_name = mission_name
        self.run_started_local = _now_local()

    def _snapshot_from_drone(self, drone) -> Dict[str, Any]:
        """Extrae telemetría básica del dron (best-effort)."""
        snap: Dict[str, Any] = {
            "lat": None,
            "lon": None,
            "alt_gps_m": None,
            "alt_rel_m": None,
            "roll_rad": None,
            "pitch_rad": None,
            "yaw_rad": None,
            "battery_percent": None,
            "gps_fix": None,
            "num_sats": None,
        }

        try:
            from sensores.messages import (
                AttitudeChanged,
                AltitudeChanged,
                PositionChanged,
                BatteryStateChanged,
                GPSFixStateChanged,
                NumberOfSatelliteChanged,
            )

            try:
                pos = drone.get_state(PositionChanged) or {}
                snap["lat"] = _safe_float(pos.get("latitude"))
                snap["lon"] = _safe_float(pos.get("longitude"))
                snap["alt_gps_m"] = _safe_float(pos.get("altitude"))
            except Exception:
                pass

            try:
                alt = drone.get_state(AltitudeChanged) or {}
                snap["alt_rel_m"] = _safe_float(alt.get("altitude"))
            except Exception:
                pass

            try:
                att = drone.get_state(AttitudeChanged) or {}
                snap["roll_rad"] = _safe_float(att.get("roll"))
                snap["pitch_rad"] = _safe_float(att.get("pitch"))
                snap["yaw_rad"] = _safe_float(att.get("yaw"))
            except Exception:
                pass

            if BatteryStateChanged is not None:
                try:
                    batt = drone.get_state(BatteryStateChanged) or {}
                    snap["battery_percent"] = _safe_float(
                        batt.get("percent", batt.get("battery_percentage"))
                    )
                except Exception:
                    pass

            try:
                fix = drone.get_state(GPSFixStateChanged) or {}
                fixed = fix.get("fixed")
                if fixed is not None:
                    snap["gps_fix"] = bool(int(fixed) == 1)
            except Exception:
                pass

            try:
                sats = drone.get_state(NumberOfSatelliteChanged) or {}
                snap["num_sats"] = sats.get("numberOfSatellite")
            except Exception:
                pass

        except Exception:
            # Si no se pueden importar mensajes, no rompemos la ejecución.
            pass

        return snap

    def add_photo(
        self,
        *,
        drone=None,
        photo_path: str,
        sensor: str,
        mode: str,
        mission_name: Optional[str] = None,
        waypoint_index: Optional[int] = None,
        mapped_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._record_seq += 1

        now_local = _now_local()
        now_utc = now_local.astimezone(_dt.timezone.utc)

        snap = self._snapshot_from_drone(drone) if drone is not None else {}

        file_name = os.path.basename(photo_path)
        photo_id = os.path.splitext(file_name)[0]

        rec: Dict[str, Any] = {
            "record_id": self._record_seq,
            "mission_name": mission_name or self.current_mission_name or "",
            "waypoint_index": waypoint_index,
            "sensor": sensor,
            "mode": mode,
            "photo_id": photo_id,
            "file_name": file_name,
            "file_path": os.path.abspath(photo_path),
            "mapped_path": os.path.abspath(mapped_path) if mapped_path else "",
            "captured_local": _iso(now_local),
            "captured_utc": _iso(now_utc),
        }

        rec.update(snap)
        self.records.append(rec)
        return rec

    def _columns_for_export(self) -> List[str]:
        # Mantener orden estable; incluir columnas extra si existen.
        cols = list(DEFAULT_COLUMNS)
        extra = set()
        for r in self.records:
            extra.update(r.keys())
        for c in sorted(extra):
            if c not in cols:
                cols.append(c)
        return cols

    def export(self, path: str) -> str:
        """Exporta según extensión (.csv o .xlsx)."""
        ext = os.path.splitext(path)[1].lower()
        if ext == ".xlsx":
            return self.export_xlsx(path)
        return self.export_csv(path)

    def export_csv(self, path: str) -> str:
        """Exporta CSV.

        En configuraciones regionales comunes en español, Excel suele
        interpretar por defecto el separador de columnas como ';'.
        Para que cada metadato quede en su propia "casilla" al abrir el
        CSV en Excel, usamos ';' como delimiter.
        """

        cols = self._columns_for_export()
        _ensure_dir(os.path.dirname(path) or ".")
        # utf-8-sig agrega BOM para que Excel detecte UTF-8 sin problemas.
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(
                f,
                fieldnames=cols,
                delimiter=";",
                quoting=csv.QUOTE_MINIMAL,
            )
            w.writeheader()
            for r in self.records:
                w.writerow({c: r.get(c, "") for c in cols})
        return path

    def export_xlsx(self, path: str) -> str:
        cols = self._columns_for_export()
        _ensure_dir(os.path.dirname(path) or ".")

        try:
            from openpyxl import Workbook
        except Exception as e:
            raise RuntimeError(
                "openpyxl no está disponible. Instala con: pip install openpyxl"
            ) from e

        wb = Workbook()
        ws = wb.active
        ws.title = "photos"

        ws.append(cols)
        for r in self.records:
            ws.append([r.get(c, "") for c in cols])

        wb.save(path)
        return path
