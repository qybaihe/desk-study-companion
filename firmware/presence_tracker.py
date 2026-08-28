"""Convert a changing PIR signal into stable PRESENT/AWAY state."""


class PresenceTracker:
    AWAY = 0
    PRESENT = 1

    def __init__(self, absence_timeout_ms=90_000, motion_confirm_ms=250):
        self.absence_timeout_ms = absence_timeout_ms
        self.motion_confirm_ms = motion_confirm_ms
        self.state = self.AWAY
        self.motion_high_since = None
        self.last_motion_at = None
        self.session_started_at = None
        self.last_session_seconds = 0
        self.transition = None

    def update(self, raw_motion, now_ms, ticks_diff):
        """Update state and return a display-ready snapshot.

        `ticks_diff` is passed in so the same state machine can be tested on a
        computer and use MicroPython's wrap-safe time.ticks_diff on the board.
        """
        self.transition = None

        if raw_motion:
            if self.motion_high_since is None:
                self.motion_high_since = now_ms

            if ticks_diff(now_ms, self.motion_high_since) >= self.motion_confirm_ms:
                self.last_motion_at = now_ms
                if self.state == self.AWAY:
                    self.state = self.PRESENT
                    self.session_started_at = self.motion_high_since
                    self.transition = "ARRIVED"
        else:
            self.motion_high_since = None

        if self.state == self.PRESENT:
            silence_ms = max(0, ticks_diff(now_ms, self.last_motion_at))
            if silence_ms >= self.absence_timeout_ms:
                self.last_session_seconds = max(
                    0, ticks_diff(now_ms, self.session_started_at) // 1000
                )
                self.state = self.AWAY
                self.session_started_at = None
                self.last_motion_at = None
                self.transition = "LEFT"

        if self.state == self.PRESENT:
            study_seconds = max(
                0, ticks_diff(now_ms, self.session_started_at) // 1000
            )
            silence_ms = max(0, ticks_diff(now_ms, self.last_motion_at))
            remaining_ms = max(0, self.absence_timeout_ms - silence_ms)
            away_in_seconds = (remaining_ms + 999) // 1000
        else:
            study_seconds = self.last_session_seconds
            away_in_seconds = 0

        return {
            "present": self.state == self.PRESENT,
            "study_seconds": study_seconds,
            "away_in_seconds": away_in_seconds,
            "transition": self.transition,
        }
