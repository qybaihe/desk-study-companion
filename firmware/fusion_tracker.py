"""PIR + VL53L0X fusion state machine for stable desk presence."""


class FusionPresenceTracker:
    AWAY = "AWAY"
    ENTER_CONFIRM = "ENTER_CONFIRM"
    PRESENT = "PRESENT"
    EXIT_CONFIRM = "EXIT_CONFIRM"

    def __init__(
        self,
        enter_distance_mm=850,
        exit_distance_mm=1000,
        enter_confirm_ms=500,
        motion_event_window_ms=8000,
        exit_invalid_confirm_ms=3000,
        pir_fallback_ms=90000,
    ):
        self.enter_distance_mm = enter_distance_mm
        self.exit_distance_mm = exit_distance_mm
        self.enter_confirm_ms = enter_confirm_ms
        self.motion_event_window_ms = motion_event_window_ms
        self.exit_invalid_confirm_ms = exit_invalid_confirm_ms
        self.pir_fallback_ms = pir_fallback_ms

        self.state = self.AWAY
        self.previous_pir = False
        self.last_pir_event_at = None
        self.enter_started_at = None
        self.exit_event_at = None
        self.exit_started_at = None
        self.unconfirmed_absence_at = None
        self.session_started_at = None
        self.last_session_seconds = 0
        self.transition = None

    def _arrive(self, now_ms, ticks_diff):
        session_start = self.enter_started_at
        if session_start is None:
            session_start = now_ms
        self.state = self.PRESENT
        self.session_started_at = session_start
        self.enter_started_at = None
        self.exit_event_at = None
        self.exit_started_at = None
        self.unconfirmed_absence_at = None
        self.transition = "ARRIVED"

    def _leave(self, now_ms, ticks_diff):
        if self.session_started_at is not None:
            self.last_session_seconds = max(
                0, ticks_diff(now_ms, self.session_started_at) // 1000
            )
        self.state = self.AWAY
        self.session_started_at = None
        self.enter_started_at = None
        self.exit_event_at = None
        self.exit_started_at = None
        self.unconfirmed_absence_at = None
        self.transition = "LEFT"

    def update(self, pir_motion, distance_mm, tof_healthy, now_ms, ticks_diff):
        self.transition = None
        pir_motion = bool(pir_motion)
        pir_event = pir_motion and not self.previous_pir
        self.previous_pir = pir_motion
        if pir_event:
            self.last_pir_event_at = now_ms

        motion_event_recent = (
            self.last_pir_event_at is not None
            and ticks_diff(now_ms, self.last_pir_event_at)
            <= self.motion_event_window_ms
        )
        enter_target = (
            tof_healthy
            and distance_mm is not None
            and distance_mm <= self.enter_distance_mm
        )
        keep_target = (
            tof_healthy
            and distance_mm is not None
            and distance_mm <= self.exit_distance_mm
        )

        if self.state == self.AWAY:
            # Distance alone is not enough: an entry requires a PIR change
            # followed by a stable seated-range return.
            if motion_event_recent and enter_target:
                self.state = self.ENTER_CONFIRM
                self.enter_started_at = now_ms

        elif self.state == self.ENTER_CONFIRM:
            if not motion_event_recent:
                self.state = self.AWAY
                self.enter_started_at = None
            elif not enter_target:
                # Retain the PIR event window, but restart the 0.5 s distance
                # confirmation when a stable target returns.
                self.state = self.AWAY
                self.enter_started_at = None
            elif ticks_diff(now_ms, self.enter_started_at) >= self.enter_confirm_ms:
                self._arrive(now_ms, ticks_diff)

        elif self.state == self.PRESENT:
            if pir_event:
                # A new movement may be the child getting up. Do not declare
                # departure until the following distance is continuously empty.
                self.state = self.EXIT_CONFIRM
                self.exit_event_at = now_ms
                self.exit_started_at = None

            if keep_target:
                self.unconfirmed_absence_at = None
            else:
                if self.unconfirmed_absence_at is None:
                    self.unconfirmed_absence_at = now_ms
                elif ticks_diff(now_ms, self.unconfirmed_absence_at) >= self.pir_fallback_ms:
                    self._leave(now_ms, ticks_diff)

        elif self.state == self.EXIT_CONFIRM:
            if pir_event:
                self.exit_event_at = now_ms

            if keep_target:
                self.exit_started_at = None
                self.unconfirmed_absence_at = None
                if ticks_diff(now_ms, self.exit_event_at) > self.motion_event_window_ms:
                    # It was movement at the desk, not a departure.
                    self.state = self.PRESENT
                    self.exit_event_at = None
            else:
                if self.unconfirmed_absence_at is None:
                    self.unconfirmed_absence_at = now_ms

                # Only a functioning ToF sensor can support the fast exit rule.
                if tof_healthy:
                    if self.exit_started_at is None:
                        self.exit_started_at = now_ms
                    elif (
                        ticks_diff(now_ms, self.exit_started_at)
                        >= self.exit_invalid_confirm_ms
                    ):
                        self._leave(now_ms, ticks_diff)
                elif (
                    ticks_diff(now_ms, self.unconfirmed_absence_at)
                    >= self.pir_fallback_ms
                ):
                    self._leave(now_ms, ticks_diff)

        final_present = self.state in (self.PRESENT, self.EXIT_CONFIRM)
        if final_present and self.session_started_at is not None:
            study_seconds = max(
                0, ticks_diff(now_ms, self.session_started_at) // 1000
            )
        else:
            study_seconds = self.last_session_seconds

        return {
            "present": final_present,
            "internal_state": self.state,
            "study_seconds": study_seconds,
            "transition": self.transition,
            "tof_healthy": bool(tof_healthy),
            "pir_event": pir_event,
        }


class DistanceMedianFilter:
    """Require a stable majority before publishing a distance."""

    def __init__(
        self,
        size=5,
        minimum_mm=150,
        maximum_mm=2000,
        minimum_valid=3,
        maximum_spread_mm=250,
        stale_ms=None,
    ):
        self.size = size
        self.minimum_mm = minimum_mm
        self.maximum_mm = maximum_mm
        self.minimum_valid = minimum_valid
        self.maximum_spread_mm = maximum_spread_mm
        self.values = []

    @staticmethod
    def _median(values):
        ordered = sorted(values)
        count = len(ordered)
        middle = count // 2
        if count % 2:
            return ordered[middle]
        return (ordered[middle - 1] + ordered[middle]) // 2

    def update(self, raw_mm, now_ms, ticks_diff):
        if (
            raw_mm is not None
            and self.minimum_mm <= raw_mm <= self.maximum_mm
        ):
            sample = raw_mm
        else:
            sample = None

        self.values.append(sample)
        if len(self.values) > self.size:
            self.values.pop(0)

        valid = [value for value in self.values if value is not None]
        if len(valid) < self.minimum_valid:
            return None
        if max(valid) - min(valid) > self.maximum_spread_mm:
            return None
        return self._median(valid)
