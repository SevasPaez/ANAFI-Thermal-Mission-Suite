HAVE_OLYMPE = False
try:
    import olympe
    from olympe.messages.gimbal import set_target, reset_orientation as gimbal_reset
    HAVE_OLYMPE = True
except Exception:
    HAVE_OLYMPE = False


class GimbalControl:
    """
    Control del gimbal con pasos relativos y reset.
    """
    def __init__(self, drone=None, gimbal_id=0):
        self.drone = drone
        self.gimbal_id = gimbal_id

    def center(self):
        if not HAVE_OLYMPE or self.drone is None:
            return False
        return bool(self.drone(gimbal_reset(gimbal_id=self.gimbal_id)).wait())

    def set_angles(self, pitch=None, yaw=None, roll=None, absolute=True):
        if not HAVE_OLYMPE or self.drone is None:
            return False
        args = dict(
            gimbal_id=self.gimbal_id,
            control_mode="position",
            yaw_frame_of_reference="absolute" if absolute else "relative",
            pitch_frame_of_reference="absolute" if absolute else "relative",
            roll_frame_of_reference="absolute" if absolute else "relative",
        )
        if yaw is not None:
            args["yaw"] = float(yaw)
        if pitch is not None:
            args["pitch"] = float(pitch)
        if roll is not None:
            args["roll"] = float(roll)
        return bool(self.drone(set_target(**args)).wait())

    def nudge_pitch(self, delta_deg: float):
        """
        Paso relativo en pitch (±5° típico).
        """
        return self.set_angles(pitch=delta_deg, absolute=False)

