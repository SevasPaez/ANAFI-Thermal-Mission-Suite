from __future__ import annotations

import io
import math
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

@dataclass(frozen=True)
class FlirRecord:
    record_type: int
    subtype: int
    version: int
    index_id: int
    offset: int
    length: int

@dataclass(frozen=True)
class FlirCameraInfo:
    emissivity: float
    object_distance_m: float
    reflected_temp_c: float
    atmospheric_temp_c: float
    ir_window_temp_c: float
    ir_window_transmission: float
    relative_humidity_pct: float
    planck_r1: float
    planck_b: float
    planck_f: float
    atmospheric_trans_alpha1: float
    atmospheric_trans_alpha2: float
    atmospheric_trans_beta1: float
    atmospheric_trans_beta2: float
    atmospheric_trans_x: float
    camera_temp_range_max_c: float
    camera_temp_range_min_c: float
    planck_o: int
    planck_r2: float
    raw_value_median: int
    raw_value_range: int
    raw_width: int
    raw_height: int
    byte_order: str

    def to_meta(self) -> Dict[str, Any]:
        data = asdict(self)
        data["byte_order"] = "little" if self.byte_order == "<" else "big"
        return data

@dataclass(frozen=True)
class FlirRadiometricPayload:
    raw_u16: np.ndarray
    temp_c: np.ndarray
    meta: Dict[str, Any]

class FlirParseError(RuntimeError):
    pass

def _iter_jpeg_segments(data: bytes) -> Iterator[Tuple[int, bytes]]:
    if not data.startswith(b"\xff\xd8"):
        raise FlirParseError("El archivo no es un JPEG válido")

    i = 2
    n = len(data)
    while i < n - 1:
        if data[i] != 0xFF:
            i += 1
            continue
        while i < n and data[i] == 0xFF:
            i += 1
        if i >= n:
            break

        marker = data[i]
        i += 1

        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            continue
        if i + 2 > n:
            break

        seg_len = int.from_bytes(data[i : i + 2], "big")
        start = i + 2
        end = start + seg_len - 2
        if end > n:
            break

        yield marker, data[start:end]

        if marker == 0xDA:
            break
        i = end

def extract_flir_blob(path: str) -> Optional[bytes]:
    data = Path(path).read_bytes()
    flir_segments = [seg for marker, seg in _iter_jpeg_segments(data) if marker == 0xE1 and seg.startswith(b"FLIR\x00\x01")]
    if not flir_segments:
        return None

    flir_segments.sort(key=lambda seg: seg[6])
    return b"".join(seg[8:] for seg in flir_segments)

def parse_flir_records(blob: bytes) -> List[FlirRecord]:
    if len(blob) < 0x40 or not blob.startswith(b"FFF\x00"):
        raise FlirParseError("Bloque FLIR/FFF inválido")

    directory_offset = int.from_bytes(blob[0x18:0x1C], "big")
    entry_count = int.from_bytes(blob[0x1C:0x20], "big")
    if directory_offset + entry_count * 0x20 > len(blob):
        raise FlirParseError("Directorio FFF truncado")

    out: List[FlirRecord] = []
    for index in range(entry_count):
        off = directory_offset + index * 0x20
        entry = blob[off : off + 0x20]
        record_type = int.from_bytes(entry[0:2], "big")
        if record_type == 0:
            continue
        out.append(
            FlirRecord(
                record_type=record_type,
                subtype=int.from_bytes(entry[2:4], "big"),
                version=int.from_bytes(entry[4:8], "big"),
                index_id=int.from_bytes(entry[8:12], "big"),
                offset=int.from_bytes(entry[12:16], "big"),
                length=int.from_bytes(entry[16:20], "big"),
            )
        )
    return out

def _record_bytes(blob: bytes, record: FlirRecord) -> bytes:
    end = record.offset + record.length
    if end > len(blob):
        raise FlirParseError("Registro FLIR truncado")
    return blob[record.offset:end]

def _camera_byte_order(camera_record: bytes) -> str:

    return "<" if int.from_bytes(camera_record[0:2], "big") >= 0x0100 else ">"

def _f32(buf: bytes, off: int, byte_order: str) -> float:
    return float(struct.unpack(byte_order + "f", buf[off : off + 4])[0])

def _i32(buf: bytes, off: int, byte_order: str) -> int:
    return int(struct.unpack(byte_order + "i", buf[off : off + 4])[0])

def _u16(buf: bytes, off: int, byte_order: str) -> int:
    return int(struct.unpack(byte_order + "H", buf[off : off + 2])[0])

def parse_flir_camera_info(blob: bytes) -> FlirCameraInfo:
    records = parse_flir_records(blob)
    camera_record = next((r for r in records if r.record_type == 0x20), None)
    if camera_record is None:
        raise FlirParseError("No se encontró CameraInfo en el bloque FLIR")

    buf = _record_bytes(blob, camera_record)
    byte_order = _camera_byte_order(buf)

    relative_humidity = _f32(buf, 0x3C, byte_order)
    if relative_humidity <= 2.0:
        relative_humidity *= 100.0

    return FlirCameraInfo(
        emissivity=_f32(buf, 0x20, byte_order),
        object_distance_m=_f32(buf, 0x24, byte_order),
        reflected_temp_c=_f32(buf, 0x28, byte_order) - 273.15,
        atmospheric_temp_c=_f32(buf, 0x2C, byte_order) - 273.15,
        ir_window_temp_c=_f32(buf, 0x30, byte_order) - 273.15,
        ir_window_transmission=_f32(buf, 0x34, byte_order),
        relative_humidity_pct=relative_humidity,
        planck_r1=_f32(buf, 0x58, byte_order),
        planck_b=_f32(buf, 0x5C, byte_order),
        planck_f=_f32(buf, 0x60, byte_order),
        atmospheric_trans_alpha1=_f32(buf, 0x70, byte_order),
        atmospheric_trans_alpha2=_f32(buf, 0x74, byte_order),
        atmospheric_trans_beta1=_f32(buf, 0x78, byte_order),
        atmospheric_trans_beta2=_f32(buf, 0x7C, byte_order),
        atmospheric_trans_x=_f32(buf, 0x80, byte_order),
        camera_temp_range_max_c=_f32(buf, 0x90, byte_order) - 273.15,
        camera_temp_range_min_c=_f32(buf, 0x94, byte_order) - 273.15,
        planck_o=_i32(buf, 0x308, byte_order),
        planck_r2=_f32(buf, 0x30C, byte_order),
        raw_value_median=_u16(buf, 0x338, byte_order),
        raw_value_range=_u16(buf, 0x33C, byte_order),
        raw_width=_u16(buf, 0x02, byte_order),
        raw_height=_u16(buf, 0x04, byte_order),
        byte_order=byte_order,
    )

def extract_flir_raw_png16(blob: bytes) -> Tuple[np.ndarray, Dict[str, Any]]:
    records = parse_flir_records(blob)
    raw_record = next((r for r in records if r.record_type == 0x01), None)
    if raw_record is None:
        raise FlirParseError("No se encontró RawData en el bloque FLIR")

    raw_payload = _record_bytes(blob, raw_record)
    if len(raw_payload) < 0x20:
        raise FlirParseError("Registro RawData truncado")

    byte_swap_required = int.from_bytes(raw_payload[0:2], "big") >= 0x0100
    raw_width = int.from_bytes(raw_payload[2:4], "little" if byte_swap_required else "big")
    raw_height = int.from_bytes(raw_payload[4:6], "little" if byte_swap_required else "big")
    image_bytes = raw_payload[0x20:]

    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.load()
    except Exception as exc:
        raise FlirParseError(f"No se pudo decodificar RawData PNG: {exc}") from exc

    raw_u16 = np.array(image, dtype=np.uint16)
    if raw_u16.ndim != 2:
        raise FlirParseError("La imagen térmica RAW no es monocanal")
    if byte_swap_required:
        raw_u16 = raw_u16.byteswap()

    meta = {
        "flir_raw_record_subtype": raw_record.subtype,
        "flir_raw_record_version": raw_record.version,
        "raw_byte_swap_applied": bool(byte_swap_required),
        "raw_record_width": int(raw_width),
        "raw_record_height": int(raw_height),
        "raw_png_mode": getattr(image, "mode", None),
    }
    return raw_u16, meta

def _temp_to_raw(temp_c: float, camera: FlirCameraInfo) -> float:
    return camera.planck_r1 / (
        camera.planck_r2 * (math.exp(camera.planck_b / (temp_c + 273.15)) - camera.planck_f)
    ) - camera.planck_o

def raw_to_temp_c(raw_u16: np.ndarray, camera: FlirCameraInfo) -> np.ndarray:
    raw = raw_u16.astype(np.float64)

    emissivity = max(float(camera.emissivity), 1e-6)
    distance_m = max(float(camera.object_distance_m), 0.0)
    reflected_c = float(camera.reflected_temp_c)
    atmospheric_c = float(camera.atmospheric_temp_c)
    ir_window_c = float(camera.ir_window_temp_c)
    ir_window_trans = max(float(camera.ir_window_transmission), 1e-6)
    humidity_pct = float(camera.relative_humidity_pct)

    ata1 = float(camera.atmospheric_trans_alpha1)
    ata2 = float(camera.atmospheric_trans_alpha2)
    atb1 = float(camera.atmospheric_trans_beta1)
    atb2 = float(camera.atmospheric_trans_beta2)
    atx = float(camera.atmospheric_trans_x)

    h2o = (humidity_pct / 100.0) * math.exp(
        1.5587
        + 0.06939 * atmospheric_c
        - 0.00027816 * atmospheric_c**2
        + 0.00000068455 * atmospheric_c**3
    )

    tau1 = atx * math.exp(-math.sqrt(distance_m / 2.0) * (ata1 + atb1 * math.sqrt(h2o))) + (
        1.0 - atx
    ) * math.exp(-math.sqrt(distance_m / 2.0) * (ata2 + atb2 * math.sqrt(h2o)))
    tau2 = tau1

    emiss_window = 1.0 - ir_window_trans
    refl_window = 0.0

    raw_refl1 = _temp_to_raw(reflected_c, camera)
    raw_refl1_attn = (1.0 - emissivity) / emissivity * raw_refl1

    raw_atm1 = _temp_to_raw(atmospheric_c, camera)
    raw_atm1_attn = (1.0 - tau1) / emissivity / tau1 * raw_atm1 if tau1 != 0.0 else 0.0

    raw_window = _temp_to_raw(ir_window_c, camera)
    raw_window_attn = (
        emiss_window / emissivity / tau1 / ir_window_trans * raw_window
        if tau1 != 0.0 and ir_window_trans != 0.0
        else 0.0
    )

    raw_refl2 = _temp_to_raw(reflected_c, camera)
    raw_refl2_attn = (
        refl_window / emissivity / tau1 / ir_window_trans * raw_refl2
        if tau1 != 0.0 and ir_window_trans != 0.0
        else 0.0
    )

    raw_atm2 = _temp_to_raw(atmospheric_c, camera)
    raw_atm2_attn = (
        (1.0 - tau2) / emissivity / tau1 / ir_window_trans / tau2 * raw_atm2
        if tau1 != 0.0 and tau2 != 0.0 and ir_window_trans != 0.0
        else 0.0
    )

    raw_object = (
        raw / emissivity / tau1 / ir_window_trans / tau2
        - raw_atm1_attn
        - raw_atm2_attn
        - raw_window_attn
        - raw_refl1_attn
        - raw_refl2_attn
    )

    with np.errstate(divide="ignore", invalid="ignore"):
        inside = camera.planck_r1 / (camera.planck_r2 * (raw_object + camera.planck_o)) + camera.planck_f
        temp_c = camera.planck_b / np.log(inside) - 273.15

    temp_c = temp_c.astype(np.float32)
    temp_c[~np.isfinite(temp_c)] = np.nan
    return temp_c

def extract_flir_radiometric(path: str) -> Optional[FlirRadiometricPayload]:
    try:
        blob = extract_flir_blob(path)
        if blob is None:
            return None
        camera = parse_flir_camera_info(blob)
        raw_u16, raw_meta = extract_flir_raw_png16(blob)
        temp_c = raw_to_temp_c(raw_u16, camera)

        finite = np.isfinite(temp_c)
        meta: Dict[str, Any] = {
            "method": "flir_raw_png",
            "radiometry_source": "flir_app1_rawdata",
            "temp_method": "flir_raw2temp",
            "source_path": str(Path(path).resolve()),
            "flir_record_count": len(parse_flir_records(blob)),
            "raw_dtype": str(raw_u16.dtype),
            "raw_shape": [int(raw_u16.shape[0]), int(raw_u16.shape[1])],
            "raw_min": int(raw_u16.min()),
            "raw_max": int(raw_u16.max()),
            "raw_mean": float(raw_u16.mean()),
            "temp_valid_ratio": float(finite.mean()),
            "flir_camera_info": camera.to_meta(),
        }
        meta.update(raw_meta)
        if finite.any():
            meta["temp_range_c"] = [float(np.nanmin(temp_c)), float(np.nanmax(temp_c))]
            meta["temp_median_c"] = float(np.nanmedian(temp_c))
        return FlirRadiometricPayload(raw_u16=raw_u16, temp_c=temp_c, meta=meta)
    except Exception:
        return None
