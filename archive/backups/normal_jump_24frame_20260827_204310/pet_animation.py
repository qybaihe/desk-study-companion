"""Small allocation-free animation state machines for MicroPython."""


class OneShotFrameAnimator:
    """Play every frame once after an idle interval, without frame skipping."""

    def __init__(self, frame_durations_ms, idle_interval_ms, now_ms=0):
        if not frame_durations_ms:
            raise ValueError("at least one frame duration is required")
        self.frame_durations_ms = tuple(int(value) for value in frame_durations_ms)
        if any(value <= 0 for value in self.frame_durations_ms):
            raise ValueError("frame durations must be positive")
        self.idle_interval_ms = int(idle_interval_ms)
        if self.idle_interval_ms <= 0:
            raise ValueError("idle interval must be positive")

        self.active = False
        self.frame = -1
        self.frame_started_at = None
        self.last_idle_at = now_ms
        self.play_count = 0

    def cancel(self, now_ms):
        """Return to idle and require a complete interval before replaying."""
        self.active = False
        self.frame = -1
        self.frame_started_at = None
        self.last_idle_at = now_ms

    def update(self, now_ms, enabled, ticks_diff):
        """Advance by no more than one frame; return True on a new playback."""
        if not enabled:
            self.cancel(now_ms)
            return False

        if not self.active:
            if ticks_diff(now_ms, self.last_idle_at) < self.idle_interval_ms:
                return False
            self.active = True
            self.frame = 0
            self.frame_started_at = now_ms
            self.play_count += 1
            return True

        elapsed = ticks_diff(now_ms, self.frame_started_at)
        if elapsed < self.frame_durations_ms[self.frame]:
            return False

        if self.frame + 1 < len(self.frame_durations_ms):
            # Deliberately advance only once.  Even a slow sensor/display cycle
            # must render every pose instead of jumping directly to a later one.
            self.frame += 1
            self.frame_started_at = now_ms
        else:
            self.active = False
            self.frame = -1
            self.frame_started_at = None
            self.last_idle_at = now_ms
        return False
