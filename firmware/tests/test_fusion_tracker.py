from fusion_tracker import DistanceMedianFilter, FusionPresenceTracker


def diff(new, old):
    return new - old


tracker = FusionPresenceTracker()

# Distance alone never declares that a child arrived.
assert not tracker.update(0, 600, True, 0, diff)["present"]
assert not tracker.update(0, 600, True, 3_000, diff)["present"]

# PIR rising edge plus stable seated distance for 0.5 seconds starts study.
assert not tracker.update(1, 600, True, 4_000, diff)["present"]
assert not tracker.update(1, 610, True, 4_499, diff)["present"]
state = tracker.update(1, 605, True, 4_500, diff)
assert state["present"] and state["transition"] == "ARRIVED"

# PIR may clear while distance keeps the child PRESENT.
state = tracker.update(0, 700, True, 10_000, diff)
assert state["present"] and state["internal_state"] == tracker.PRESENT

# Invalid distance without a new PIR event is treated as a transient dropout.
state = tracker.update(0, None, True, 11_000, diff)
assert state["present"] and state["internal_state"] == tracker.PRESENT

# A new PIR event starts departure observation.
state = tracker.update(1, 700, True, 12_000, diff)
assert state["present"] and state["internal_state"] == tracker.EXIT_CONFIRM

# If distance becomes invalid after that event for 3 seconds, child has left.
tracker.update(0, None, True, 12_500, diff)
assert tracker.update(0, None, True, 15_499, diff)["present"]
state = tracker.update(0, None, True, 15_500, diff)
assert not state["present"] and state["transition"] == "LEFT"

# Re-entry starts a new session.
tracker.update(1, 550, True, 20_000, diff)
state = tracker.update(1, 560, True, 20_500, diff)
assert state["present"] and state["transition"] == "ARRIVED"

# Moving at the desk does not cause departure when valid distance remains.
tracker.update(0, 560, True, 21_000, diff)
tracker.update(1, 580, True, 22_000, diff)
state = tracker.update(0, 570, True, 30_001, diff)
assert state["present"] and state["internal_state"] == tracker.PRESENT

# Median filtering rejects single jump values and requires a stable 3-of-5 majority.
filt = DistanceMedianFilter()
assert filt.update(500, 0, diff) is None
assert filt.update(None, 100, diff) is None
assert filt.update(520, 200, diff) is None
assert filt.update(510, 300, diff) == 510
assert filt.update(1500, 400, diff) is None  # excessive spread
assert filt.update(None, 500, diff) is None
assert filt.update(None, 600, diff) is None

print("fusion tracker tests: OK")
