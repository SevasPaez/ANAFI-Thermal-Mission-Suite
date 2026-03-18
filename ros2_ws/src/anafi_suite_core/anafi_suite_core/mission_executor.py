from __future__ import annotations

import datetime as _dt
import json
import math
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .runtime_paths import get_app_dir

_APP_DIR = get_app_dir()
if _APP_DIR and _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from config import DRONE_IP, DRONE_RTSP_URL, MEDIA_ROOT, RTSP_TRANSPORT  # type: ignore
from sensores.photo_metadata import PhotoMetadataStore  # type: ignore

StatusCb = Optional[Callable[[str], None]]
ProgressCb = Optional[Callable[[dict[str, Any]], None]]
EventCb = Optional[Callable[[dict[str, Any]], None]]


@dataclass
class MissionResult:
    ok: bool
    cancelled: bool = False
    error: str = ""
    metadata_count: int = 0


class MissionExecutor:
    """Reusable mission executor shared by the GUI and the ROS2 mission manager."""

    def __init__(
        self,
        *,
        drone_ip: str = DRONE_IP,
        media_root: str = MEDIA_ROOT,
        meta_store: Optional[PhotoMetadataStore] = None,
    ) -> None:
        self.drone_ip = drone_ip
        self.media_root = media_root
        self.meta_store = meta_store or PhotoMetadataStore(media_root=media_root)
        self._video_proc: Optional[subprocess.Popen[str]] = None
        self._drone = None

    def _emit_status(self, cb: StatusCb, msg: str) -> None:
        if cb is None:
            return
        try:
            cb(str(msg))
        except Exception:
            pass

    def _emit_progress(self, cb: ProgressCb, **payload: Any) -> None:
        if cb is None:
            return
        try:
            cb(dict(payload))
        except Exception:
            pass

    def _emit_event(self, cb: EventCb, **payload: Any) -> None:
        if cb is None:
            return
        try:
            cb(dict(payload))
        except Exception:
            pass

    def _ensure_drone_for_control(self):
        if self._drone is not None:
            return self._drone

        import olympe  # type: ignore

        last_exc = None
        for attempt in range(1, 4):
            d = None
            try:
                d = olympe.Drone(self.drone_ip, media_port="80")
                ok = d.connect(retry=1)
                if ok:
                    self._drone = d
                    return self._drone
            except Exception as exc:
                last_exc = exc
            finally:
                if d is not None and self._drone is None:
                    try:
                        d.disconnect()
                    except Exception:
                        pass
            time.sleep(2.0 * attempt)

        raise RuntimeError(f"No se pudo abrir una conexión exclusiva con el dron: {last_exc or 'rechazada'}")

    def _release_drone(self) -> None:
        d = self._drone
        self._drone = None
        if d is None:
            return
        try:
            d.disconnect()
        except Exception:
            pass
        time.sleep(2.0)

    def _set_stream_mode(self, drone, sensor: str) -> None:
        try:
            from olympe.messages.thermal import set_mode  # type: ignore

            if sensor == "rgb":
                drone(set_mode("standard")).wait(2)
            else:
                drone(set_mode("blended")).wait(2)
        except Exception:
            pass

    def _capture_rgb_snapshot(self) -> str:
        from sensores.rgb_capture import take_rgb_photo  # type: ignore

        drone = self._ensure_drone_for_control()
        if drone is None:
            raise RuntimeError("No hay conexión Olympe con el dron")
        return take_rgb_photo(drone=drone, capture_root=self.media_root)

    def _video_start(self, sensor: str, quality: str) -> str:
        if self._video_proc is not None:
            return "(ya grabando)"

        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = (
            os.path.join(self.media_root, "rgb", "videos")
            if sensor == "rgb"
            else os.path.join(self.media_root, "thermal", "videos")
        )
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{sensor}_{ts}.mp4")
        _ = quality

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            RTSP_TRANSPORT,
            "-i",
            DRONE_RTSP_URL,
            "-c:v",
            "copy",
            "-an",
            out_path,
        ]
        self._video_proc = subprocess.Popen(
            cmd,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            text=True,
        )
        return out_path

    def _video_stop(self) -> None:
        if self._video_proc is None:
            return
        try:
            if hasattr(os, "killpg") and hasattr(os, "getpgid"):
                os.killpg(os.getpgid(self._video_proc.pid), signal.SIGTERM)
            else:
                self._video_proc.terminate()
            self._video_proc.wait(timeout=5)
        except Exception:
            pass
        finally:
            self._video_proc = None

    def _try_set_gimbal_pitch(self, drone, pitch_deg: float) -> None:
        try:
            from olympe.messages.gimbal import set_target  # type: ignore
            from olympe.enums.gimbal import control_mode, frame_of_reference  # type: ignore

            exp = drone(
                set_target(
                    gimbal_id=0,
                    control_mode=control_mode.position,
                    yaw_frame_of_reference=frame_of_reference.absolute,
                    yaw=0.0,
                    pitch_frame_of_reference=frame_of_reference.absolute,
                    pitch=float(pitch_deg),
                    roll_frame_of_reference=frame_of_reference.absolute,
                    roll=0.0,
                )
            )
            exp.wait(5)
        except Exception:
            return

    def _move_by(self, drone, dx: float, dy: float, dz: float, dyaw_rad: float, speed_mps: float | None):
        if speed_mps is not None:
            try:
                from olympe.messages.move import extended_move_by  # type: ignore

                max_h = float(speed_mps)
                max_v = max(0.1, min(2.0, float(speed_mps)))
                max_yaw = 60.0
                return drone(
                    extended_move_by(
                        float(dx),
                        float(dy),
                        float(dz),
                        float(dyaw_rad),
                        max_h,
                        max_v,
                        max_yaw,
                    )
                )
            except Exception:
                pass

        from olympe.messages.ardrone3.Piloting import moveBy  # type: ignore

        return drone(moveBy(float(dx), float(dy), float(dz), float(dyaw_rad)))

    def run(
        self,
        mission: dict[str, Any],
        *,
        cancel_event: Optional[threading.Event] = None,
        on_status: StatusCb = None,
        on_progress: ProgressCb = None,
        on_event: EventCb = None,
    ) -> MissionResult:
        cancel = cancel_event or threading.Event()
        mission_name = str(mission.get("name", "mission") or "mission")
        waypoints = mission.get("waypoints", []) if isinstance(mission.get("waypoints", []), list) else []
        total_waypoints = len(waypoints)

        try:
            self.meta_store.start_run(mission_name=mission_name)
        except Exception:
            try:
                self.meta_store.clear()
            except Exception:
                pass

        self._emit_progress(
            on_progress,
            state="starting",
            mission_name=mission_name,
            current_waypoint=0,
            total_waypoints=total_waypoints,
            detail="Preparando ejecución",
        )

        if mission.get("type") != "moveby_waypoints":
            self._emit_status(on_status, "Solo se ejecuta moveby_waypoints; continuaré con los waypoints definidos.")

        try:
            d = self._ensure_drone_for_control()
        except Exception as exc:
            return MissionResult(ok=False, error=f"No se pudo conectar al dron: {exc}")

        try:
            from olympe.messages.ardrone3.Piloting import Landing, TakeOff  # type: ignore
            from olympe.messages.ardrone3.PilotingState import FlyingStateChanged  # type: ignore
        except Exception as exc:
            return MissionResult(ok=False, error=f"No se pudieron importar mensajes Olympe: {exc}")

        try:
            params = mission.get("params", {}) if isinstance(mission.get("params", {}), dict) else {}
            try:
                speed_mps = float(params.get("speed_mps")) if params.get("speed_mps") is not None else None
            except Exception:
                speed_mps = None
            try:
                gimbal_pitch = float(params.get("gimbal_pitch_deg")) if params.get("gimbal_pitch_deg") is not None else None
            except Exception:
                gimbal_pitch = None

            auto = mission.get("auto", {}) if isinstance(mission.get("auto", {}), dict) else {}
            if auto.get("takeoff", True):
                self._emit_status(on_status, "Takeoff…")
                self._emit_progress(
                    on_progress,
                    state="takeoff",
                    mission_name=mission_name,
                    current_waypoint=0,
                    total_waypoints=total_waypoints,
                    detail="Despegando",
                )
                if not d(TakeOff()).wait(10).success():
                    raise RuntimeError("TakeOff no fue aceptado")
                d(FlyingStateChanged(state="hovering") | FlyingStateChanged(state="flying")).wait(15)

            if gimbal_pitch is not None:
                self._try_set_gimbal_pitch(d, gimbal_pitch)

            for i, wp in enumerate(waypoints, start=1):
                if cancel.is_set():
                    break

                dx = float(wp.get("dx", 0.0))
                dy = float(wp.get("dy", 0.0))
                dz = float(wp.get("dz", 0.0))
                dyaw_deg = float(wp.get("dyaw_deg", 0.0))
                dyaw = math.radians(dyaw_deg)
                wait_s = float(wp.get("wait_s", 0.0))
                action = wp.get("action", {}) if isinstance(wp.get("action", {}), dict) else {}
                a_type = str(action.get("type", "none"))
                a_sensor = str(action.get("sensor", "thermal"))
                a_mode = str(action.get("mode", "-"))

                self._emit_status(
                    on_status,
                    f"WP {i}: moveBy dx={dx}, dy={dy}, dz={dz}, dyaw={dyaw_deg}°"
                    + (f" @ {speed_mps:.2f} m/s" if speed_mps is not None else ""),
                )
                self._emit_progress(
                    on_progress,
                    state="waypoint",
                    mission_name=mission_name,
                    current_waypoint=i,
                    total_waypoints=total_waypoints,
                    detail=f"Moviendo al waypoint {i}",
                    waypoint=wp,
                )

                max_step = 8.0
                max_comp = max(abs(dx), abs(dy), abs(dz), 0.0)
                dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                n_seg = int(max(1, math.ceil(max_comp / max_step), math.ceil(dist / 10.0)))

                if speed_mps is None:
                    eff_speed = 0.45
                else:
                    try:
                        eff_speed = max(0.30, float(speed_mps) * 0.70)
                    except Exception:
                        eff_speed = 0.45

                for s in range(1, n_seg + 1):
                    if cancel.is_set():
                        break

                    sdx = dx / n_seg
                    sdy = dy / n_seg
                    sdz = dz / n_seg
                    sdyaw = dyaw / n_seg
                    seg_dist = math.sqrt(sdx * sdx + sdy * sdy + sdz * sdz)
                    timeout_s = max(25, int(seg_dist / eff_speed) + 15)

                    if n_seg > 1:
                        self._emit_status(
                            on_status,
                            (
                                f"WP {i} ({s}/{n_seg}): moveBy dx={sdx:.3f}, dy={sdy:.3f}, dz={sdz:.3f}, "
                                f"dyaw={math.degrees(sdyaw):.1f}°  (timeout {timeout_s}s)"
                            ),
                        )

                    exp = self._move_by(d, sdx, sdy, sdz, sdyaw, speed_mps)
                    if not exp.wait(timeout_s).success():
                        raise RuntimeError(f"moveBy falló en WP {i} (seg {s}/{n_seg})")

                d(FlyingStateChanged(state="hovering") | FlyingStateChanged(state="flying")).wait(15)

                if cancel.is_set():
                    break

                if wait_s > 0:
                    self._emit_status(on_status, f"WP {i}: wait {wait_s}s")
                    t0 = time.time()
                    while time.time() - t0 < wait_s and not cancel.is_set():
                        time.sleep(0.05)

                if cancel.is_set():
                    break

                if a_type == "photo":
                    self._emit_status(on_status, f"WP {i}: foto ({a_sensor}/{a_mode})…")
                    self._emit_progress(
                        on_progress,
                        state="action",
                        mission_name=mission_name,
                        current_waypoint=i,
                        total_waypoints=total_waypoints,
                        detail=f"Foto {a_sensor}/{a_mode}",
                    )
                    photo_path = None
                    mapped_path = None
                    matrix_raw_path = None
                    matrix_temp_path = None
                    matrix_meta_path = None
                    errors_res = None

                    if a_sensor == "thermal":
                        from config import MEDIA_ROOT as _MEDIA_ROOT_CFG  # type: ignore
                        from sensores.thermal_capture import take_thermal_photo  # type: ignore
                        from sensores.thermal_map import map_and_save  # type: ignore

                        photo_path = take_thermal_photo(drone=d, capture_root=self.media_root)
                        try:
                            mapped_path = map_and_save(photo_path)
                        except Exception:
                            mapped_path = None

                        try:
                            from sensores.thermal_matrix import get_or_create_thermal_matrices  # type: ignore

                            mats = get_or_create_thermal_matrices(photo_path)
                            matrix_raw_path = mats.raw_path
                            matrix_temp_path = mats.temp_path
                            matrix_meta_path = mats.meta_path
                        except Exception:
                            pass

                        try:
                            if matrix_temp_path and os.path.exists(matrix_temp_path):
                                from sensores.errors_pipeline import analyze_thermal_for_errors  # type: ignore

                                model_path = os.path.abspath(
                                    os.path.join(
                                        _APP_DIR,
                                        "interfaz",
                                        "assets",
                                        "models",
                                        "best.pt",
                                    )
                                )
                                if os.path.exists(model_path):
                                    errors_res = analyze_thermal_for_errors(
                                        thermal_jpg_path=photo_path,
                                        tempC_npy_path=matrix_temp_path,
                                        output_root=_MEDIA_ROOT_CFG,
                                        model_path=model_path,
                                    )
                        except Exception:
                            errors_res = None
                    else:
                        photo_path = self._capture_rgb_snapshot()

                    try:
                        if photo_path:
                            rec = self.meta_store.add_photo(
                                drone=d,
                                photo_path=photo_path,
                                sensor=a_sensor,
                                mode=a_mode,
                                mission_name=mission_name,
                                waypoint_index=i,
                                mapped_path=mapped_path,
                            )
                            if a_sensor == "thermal":
                                if matrix_raw_path:
                                    rec["matrix_raw_path"] = os.path.abspath(matrix_raw_path)
                                if matrix_temp_path:
                                    rec["matrix_tempC_path"] = os.path.abspath(matrix_temp_path)
                                if matrix_meta_path:
                                    rec["matrix_meta_path"] = os.path.abspath(matrix_meta_path)
                                try:
                                    if errors_res is not None and getattr(errors_res, "ok", False):
                                        rec["targets_detected"] = getattr(errors_res, "targets_detected", 0)
                                        rec["target_centroids_px"] = json.dumps(
                                            getattr(errors_res, "target_centroids_px", None),
                                            ensure_ascii=False,
                                        )
                                        rec["roi_warp_path"] = os.path.abspath(
                                            getattr(errors_res, "roi_warp_path", "") or ""
                                        )
                                        rec["roi_warp_tempC_path"] = os.path.abspath(
                                            getattr(errors_res, "roi_warp_tempC_path", "") or ""
                                        )
                                        rec["hotspots_count"] = getattr(errors_res, "hotspots_count", 0)
                                        rec["hotspots_centroids_px"] = json.dumps(
                                            getattr(errors_res, "hotspots_centroids_px", None),
                                            ensure_ascii=False,
                                        )
                                        rec["hotspots_mask_path"] = os.path.abspath(
                                            getattr(errors_res, "hotspots_mask_path", "") or ""
                                        )
                                        rec["hotspots_overlay_path"] = os.path.abspath(
                                            getattr(errors_res, "hotspots_overlay_path", "") or ""
                                        )
                                except Exception:
                                    pass

                            self._emit_event(
                                on_event,
                                type="photo",
                                mission_name=mission_name,
                                waypoint_index=i,
                                sensor=a_sensor,
                                mode=a_mode,
                                photo_path=photo_path,
                                mapped_path=mapped_path,
                                matrix_temp_path=matrix_temp_path,
                            )
                    except Exception:
                        pass

                elif a_type == "video_start":
                    self._emit_status(on_status, f"WP {i}: iniciar video ({a_sensor}/{a_mode})…")
                    self._set_stream_mode(d, a_sensor)
                    out_path = self._video_start(a_sensor, a_mode)
                    self._emit_event(
                        on_event,
                        type="video_start",
                        mission_name=mission_name,
                        waypoint_index=i,
                        sensor=a_sensor,
                        mode=a_mode,
                        output_path=out_path,
                    )

                elif a_type == "video_stop":
                    self._emit_status(on_status, f"WP {i}: detener video…")
                    self._video_stop()
                    self._emit_event(
                        on_event,
                        type="video_stop",
                        mission_name=mission_name,
                        waypoint_index=i,
                    )

            self._video_stop()

            if auto.get("land", True):
                self._emit_status(on_status, "Landing…")
                self._emit_progress(
                    on_progress,
                    state="landing",
                    mission_name=mission_name,
                    current_waypoint=total_waypoints,
                    total_waypoints=total_waypoints,
                    detail="Aterrizando",
                )
                d(Landing()).wait(10)
                d(FlyingStateChanged(state="landed")).wait(30)

            if cancel.is_set():
                self._emit_status(on_status, "Misión cancelada")
                return MissionResult(
                    ok=False,
                    cancelled=True,
                    metadata_count=len(self.meta_store.records),
                )

            self._emit_status(on_status, "Misión completada")
            return MissionResult(
                ok=True,
                metadata_count=len(self.meta_store.records),
            )
        except Exception as exc:
            self._video_stop()
            try:
                self._emit_status(on_status, "FAILSAFE: landing…")
                d(Landing()).wait(8)
            except Exception:
                pass
            return MissionResult(
                ok=False,
                error=str(exc),
                metadata_count=len(self.meta_store.records),
            )
        finally:
            self._video_stop()
            self._release_drone()
