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
        self.last_started_at = now_ms
        self.play_count = 0
        self.play_started_at = None
        self.last_duration_ms = 0
        self.just_completed = False

    def cancel(self, now_ms):
        """Return to idle and require a complete interval before replaying."""
        self.active = False
        self.frame = -1
        self.frame_started_at = None
        self.play_started_at = None
        # While disabled this is refreshed on every update, so recovery must
        # remain normal for a complete interval before another jump can start.
        self.last_started_at = now_ms

    def update(self, now_ms, enabled, ticks_diff, ticks_add=None):
        """Advance by no more than one frame; return True on a new playback."""
        self.just_completed = False
        if not enabled:
            self.cancel(now_ms)
            return False

        if not self.active:
            if ticks_diff(now_ms, self.last_started_at) < self.idle_interval_ms:
                return False
            self.active = True
            self.frame = 0
            self.frame_started_at = now_ms
            self.play_started_at = now_ms
            self.last_started_at = now_ms
            self.play_count += 1
            return True

        elapsed = ticks_diff(now_ms, self.frame_started_at)
        if elapsed < self.frame_durations_ms[self.frame]:
            return False

        if self.frame + 1 < len(self.frame_durations_ms):
            # Deliberately advance only once.  Even a slow sensor/display cycle
            # must render every pose instead of jumping directly to a later one.
            self.frame += 1
            # Preserve the scheduled timeline instead of accumulating the
            # sensor/LCD loop's small delays on every one of the 48 frames.
            if ticks_add is None:
                self.frame_started_at += self.frame_durations_ms[self.frame - 1]
            else:
                self.frame_started_at = ticks_add(
                    self.frame_started_at,
                    self.frame_durations_ms[self.frame - 1],
                )
        else:
            self.last_duration_ms = ticks_diff(now_ms, self.play_started_at)
            self.just_completed = True
            self.active = False
            self.frame = -1
            self.frame_started_at = None
            self.play_started_at = None
        return False


class LoopingFrameAnimator:
    """Loop while enabled and deliberately render every frame at least once."""

    def __init__(self, frame_count, frame_duration_ms):
        self.frame_count = int(frame_count)
        self.frame_duration_ms = int(frame_duration_ms)
        if self.frame_count <= 0:
            raise ValueError("frame_count must be positive")
        if self.frame_duration_ms <= 0:
            raise ValueError("frame_duration_ms must be positive")
        self.active = False
        self.frame = -1
        self.frame_started_at = None
        self.play_count = 0

    def reset(self):
        self.active = False
        self.frame = -1
        self.frame_started_at = None

    def update(self, now_ms, enabled, ticks_diff, ticks_add=None):
        """Return True only when a newly enabled animation starts."""
        if not enabled:
            self.reset()
            return False
        if not self.active:
            self.active = True
            self.frame = 0
            self.frame_started_at = now_ms
            self.play_count += 1
            return True
        if ticks_diff(now_ms, self.frame_started_at) < self.frame_duration_ms:
            return False

        # Advance only one step after a slow LCD/I2S cycle. This keeps the
        # eight designed poses visible instead of skipping half the loop.
        self.frame = (self.frame + 1) % self.frame_count
        if ticks_add is None:
            self.frame_started_at += self.frame_duration_ms
        else:
            self.frame_started_at = ticks_add(
                self.frame_started_at, self.frame_duration_ms
            )
        return False
