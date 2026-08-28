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
