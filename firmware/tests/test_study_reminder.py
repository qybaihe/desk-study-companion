from study_reminder import LowLightReminder, OneShotStudyReminder


reminder = OneShotStudyReminder(threshold_seconds=30)

# A continuous session fires exactly once at 30 seconds.
for second in range(30):
    assert not reminder.update(True, second)
assert reminder.update(True, 30)
assert reminder.played
for second in range(31, 90):
    assert not reminder.update(True, second)

# LAST time while away must not immediately retrigger the prompt.
assert not reminder.update(False, 89)
assert not reminder.played

# A new session is independently armed.
for second in range(30):
    assert not reminder.update(True, second)
assert reminder.update(True, 30)

# A timer rollback while still marked present is treated as another session.
assert not reminder.update(True, 1)
assert not reminder.played
assert reminder.update(True, 30)

ticks_diff = lambda newer, older: newer - older
light = LowLightReminder(
    low_threshold=1500,
    recovery_threshold=1700,
    low_confirm_ms=5000,
    recovery_confirm_ms=10000,
    cooldown_ms=30 * 60 * 1000,
)

# An empty desk never talks, and brief shadows are filtered.
assert not light.update(False, 1000, 0, ticks_diff)
assert not light.update(True, 1000, 100, ticks_diff)
assert not light.update(True, 1000, 5099, ticks_diff)
assert light.update(True, 1000, 5100, ticks_diff)
assert light.play_count == 1
assert not light.update(True, 1000, 20000, ticks_diff)

# Values in the hysteresis band do not re-arm the warning. Ten seconds of
# clearly acceptable light does, but the global 30-minute cooldown still wins.
assert not light.update(True, 1600, 21000, ticks_diff)
assert not light.update(True, 1800, 22000, ticks_diff)
assert not light.update(True, 1800, 31999, ticks_diff)
assert not light.update(True, 1800, 32000, ticks_diff)
assert light.armed
assert not light.update(True, 1200, 33000, ticks_diff)
assert not light.update(True, 1200, 38000, ticks_diff)
assert not light.update(True, 1200, 1_805_099, ticks_diff)
assert light.update(True, 1200, 1_805_100, ticks_diff)
assert light.play_count == 2

# Leaving the desk re-arms darkness detection but does not erase cooldown.
assert not light.update(False, 1200, 1_805_200, ticks_diff)
assert light.armed
assert not light.update(True, 1200, 1_805_300, ticks_diff)
assert not light.update(True, 1200, 1_810_300, ticks_diff)
assert light.play_count == 2

print("study reminder tests: OK")
