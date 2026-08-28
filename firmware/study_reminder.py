"""Session-scoped study reminders."""


class OneShotStudyReminder:
    """Trigger once when a continuous study session reaches a threshold."""

    def __init__(self, threshold_seconds=30):
        self.threshold_seconds = threshold_seconds
        self.played = False
        self.last_study_seconds = 0

    def update(self, present, study_seconds):
        study_seconds = max(0, int(study_seconds))

        # AWAY always arms the reminder for the next continuous session. The
        # fusion tracker intentionally keeps LAST duration while away, so the
        # presence boolean—not a zero timer—is the session boundary.
        if not present:
            self.played = False
            self.last_study_seconds = 0
            return False

        # Recover cleanly if a caller starts another session without first
        # publishing an AWAY sample.
        if study_seconds < self.last_study_seconds:
            self.played = False

        self.last_study_seconds = study_seconds
        if not self.played and study_seconds >= self.threshold_seconds:
            self.played = True
            return True
        return False


class LowLightReminder:
    """Confirm sustained darkness and re-arm only after clear recovery."""

    def __init__(
        self,
        low_threshold=1500,
        recovery_threshold=1700,
        low_confirm_ms=5000,
        recovery_confirm_ms=10000,
        cooldown_ms=30 * 60 * 1000,
    ):
        self.low_threshold = low_threshold
        self.recovery_threshold = recovery_threshold
        self.low_confirm_ms = low_confirm_ms
        self.recovery_confirm_ms = recovery_confirm_ms
        self.cooldown_ms = cooldown_ms
        self.armed = True
        self.low_started_at = None
        self.recovery_started_at = None
        self.last_played_at = None
        self.play_count = 0

    def reset(self):
        self.armed = True
        self.low_started_at = None
        self.recovery_started_at = None

    def update(self, present, light_value, now_ms, ticks_diff):
        # There is no need to warn an empty desk. A later seated session starts
        # with a freshly armed detector even if the room stayed dark.
        if not present:
            self.reset()
            return False

        if light_value < self.low_threshold:
            self.recovery_started_at = None
            if not self.armed:
                return False
            if self.low_started_at is None:
                self.low_started_at = now_ms
                return False
            if ticks_diff(now_ms, self.low_started_at) >= self.low_confirm_ms:
                if (
                    self.last_played_at is not None
                    and ticks_diff(now_ms, self.last_played_at)
                    < self.cooldown_ms
                ):
                    return False
                self.armed = False
                self.low_started_at = None
                self.last_played_at = now_ms
                self.play_count += 1
                return True
            return False

        self.low_started_at = None
        if self.armed:
            self.recovery_started_at = None
            return False

        # A 200-count hysteresis band and a recovery hold prevent repeated
        # warnings from shadows or readings hovering around the boundary.
        if light_value >= self.recovery_threshold:
            if self.recovery_started_at is None:
                self.recovery_started_at = now_ms
            elif (
                ticks_diff(now_ms, self.recovery_started_at)
                >= self.recovery_confirm_ms
            ):
                self.armed = True
                self.recovery_started_at = None
        else:
            self.recovery_started_at = None
        return False
