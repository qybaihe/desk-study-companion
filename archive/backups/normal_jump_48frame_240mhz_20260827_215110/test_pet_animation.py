"""Regression checks for the normal pet jump and its LCD assets."""

from pathlib import Path

from pet_animation import LoopingFrameAnimator, OneShotFrameAnimator


ROOT = Path(__file__).resolve().parent
LCD = ROOT / "assets" / "pets" / "v2" / "lcd"
LOW_LIGHT_LCD = ROOT / "assets" / "pets" / "low_light" / "lcd"
REST_BREAK_LCD = ROOT / "assets" / "pets" / "rest_break" / "lcd"


def straight_diff(new, old):
    return new - old


def straight_add(old, delta):
    return old + delta


durations = tuple(84 if index % 3 == 0 else 83 for index in range(24))
assert len(durations) == 24 and sum(durations) == 2_000
animator = OneShotFrameAnimator(durations, 60_000, 0)
assert animator.update(59_999, True, straight_diff) is False
assert animator.frame == -1
assert animator.update(60_000, True, straight_diff, straight_add) is True
seen = [animator.frame]

# The full 24-frame timeline finishes at exactly 2,000 ms.
now = 60_000
for duration in durations[:-1]:
    now += duration
    animator.update(now, True, straight_diff, straight_add)
    seen.append(animator.frame)
assert seen == list(range(24)), seen
now += durations[-1]
animator.update(now, True, straight_diff, straight_add)
assert now == 62_000
assert animator.frame == -1
assert animator.play_count == 1

# Starts are spaced by 60 seconds, independent of the two-second duration.
assert not animator.update(119_999, True, straight_diff, straight_add)
assert animator.update(120_000, True, straight_diff, straight_add)
assert animator.active

# SICK cancels immediately. Recovery must remain NORMAL for a fresh 60 seconds.
animator.update(120_100, False, straight_diff, straight_add)
assert not animator.active and animator.frame == -1
assert not animator.update(180_099, True, straight_diff, straight_add)
assert animator.update(180_100, True, straight_diff, straight_add)

expected_bytes = 136 * 112 * 2
for filename in ("normal.rgb565",) + tuple(
    "normal_%d.rgb565" % index for index in range(24)
):
    assert (LCD / filename).stat().st_size == expected_bytes, filename

# The idle image must be exactly the landing pose, eliminating end-of-jump pop.
assert (LCD / "normal.rgb565").read_bytes() == (
    LCD / "normal_23.rgb565"
).read_bytes()

# The lamp voice animation loops and, even after a delayed update, advances by
# one frame rather than skipping generated poses.
lamp = LoopingFrameAnimator(8, 125)
assert lamp.update(1_000, True, straight_diff, straight_add)
assert lamp.frame == 0
assert not lamp.update(1_500, True, straight_diff, straight_add)
assert lamp.frame == 1
for index in range(2, 8):
    lamp.update(1_000 + index * 500, True, straight_diff, straight_add)
    assert lamp.frame == index
lamp.update(5_000, True, straight_diff, straight_add)
assert lamp.frame == 0
lamp.update(5_001, False, straight_diff, straight_add)
assert not lamp.active and lamp.frame == -1

for index in range(8):
    filename = LOW_LIGHT_LCD / ("low_light_%d.rgb565" % index)
    assert filename.stat().st_size == expected_bytes, filename
assert len(
    {
        (LOW_LIGHT_LCD / ("low_light_%d.rgb565" % index)).read_bytes()
        for index in range(8)
    }
) == 8

for index in range(8):
    filename = REST_BREAK_LCD / ("rest_break_%d.rgb565" % index)
    assert filename.stat().st_size == expected_bytes, filename
assert len(
    {
        (REST_BREAK_LCD / ("rest_break_%d.rgb565" % index)).read_bytes()
        for index in range(8)
    }
) == 8

print("pet animation tests: OK")
