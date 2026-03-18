
# Mensajes Olympe + fallback batería según SDK
try:
    from olympe.messages.ardrone3.PilotingState import (
        AttitudeChanged, AltitudeChanged, SpeedChanged,
        FlyingStateChanged, PositionChanged,
    )
    from olympe.messages.ardrone3.GPSSettingsState import GPSFixStateChanged
    from olympe.messages.ardrone3.GPSState import NumberOfSatelliteChanged
except Exception as e:  # pragma: no cover
    raise RuntimeError(f"No se pudieron importar mensajes Olympe: {e}")

BatteryStateChanged = None
try:
    from olympe.messages.common.CommonState import BatteryStateChanged as _BSC
    BatteryStateChanged = _BSC
except Exception:
    try:
        from olympe.messages.battery import BatteryStateChanged as _BSC
        BatteryStateChanged = _BSC
    except Exception:
        BatteryStateChanged = None
