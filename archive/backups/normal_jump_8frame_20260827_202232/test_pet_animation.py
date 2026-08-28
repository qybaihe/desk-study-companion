"""Regression checks for the normal pet jump and its LCD assets."""

from pathlib import Path

from pet_animation import OneShotFrameAnimator


ROOT = Path(__file__).resolve().parent
LCD = ROOT / "assets" / "pets" / "v2" / "lcd"


def straight_diff(new, old):
    return new - old


animator = OneShotFrameAnimator((260, 220, 340, 260), 60_000, 0)
assert animator.update(59_999, True, straight_diff) is False
assert animator.frame == -1
assert animator.update(60_000, True, straight_diff) is True
seen = [animator.frame]

# Deliberately irregular/slow display cycles: all frames must still appear.
now = 60_000
for delay in (310, 390, 460):
    now += delay
    animator.update(now, True, straight_diff)
    seen.append(animator.frame)
assert seen == [0, 1, 2, 3], seen
now += 410
animator.update(now, True, straight_diff)
assert animator.frame == -1
assert animator.play_count == 1

# A state change cancels a jump and starts a fresh full-minute idle period.
animator.update(now + 60_000, True, straight_diff)
assert animator.active
animator.update(now + 60_100, False, straight_diff)
assert not animator.active and animator.frame == -1
assert not animator.update(now + 120_099, True, straight_diff)
assert animator.update(now + 120_100, True, straight_diff)

expected_bytes = 136 * 112 * 2
for filename in ("normal.rgb565",) + tuple(
    "normal_%d.rgb565" % index for index in range(4)
):
    assert (LCD / filename).stat().st_size == expected_bytes, filename

# The idle image must be exactly the landing pose, eliminating end-of-jump pop.
assert (LCD / "normal.rgb565").read_bytes() == (
    LCD / "normal_3.rgb565"
).read_bytes()

print("pet animation tests: OK")
