from presence_tracker import PresenceTracker


def diff(new, old):
    return new - old


tracker = PresenceTracker(absence_timeout_ms=90_000, motion_confirm_ms=250)

# A short electrical pulse is rejected.
assert not tracker.update(1, 0, diff)["present"]
assert not tracker.update(0, 100, diff)["present"]

# Confirmed movement changes AWAY -> PRESENT immediately after debounce.
assert not tracker.update(1, 1_000, diff)["present"]
state = tracker.update(1, 1_300, diff)
assert state["present"] and state["transition"] == "ARRIVED"

# PIR may return CLEAR while a still child remains inferred as present.
state = tracker.update(0, 6_000, diff)
assert state["present"] and state["away_in_seconds"] == 86

# A later movement refreshes the 90-second absence window.
tracker.update(1, 80_000, diff)
tracker.update(1, 80_300, diff)
tracker.update(0, 81_000, diff)
assert tracker.update(0, 169_999, diff)["present"]

# Only 90 seconds of uninterrupted silence changes PRESENT -> AWAY.
state = tracker.update(0, 170_300, diff)
assert not state["present"] and state["transition"] == "LEFT"
assert state["study_seconds"] == 169

# A new confirmed movement starts a fresh study session.
tracker.update(1, 200_000, diff)
state = tracker.update(1, 200_300, diff)
assert state["present"] and state["transition"] == "ARRIVED"
assert state["study_seconds"] == 0

print("presence tracker tests: OK")
