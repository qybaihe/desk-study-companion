import os
import tempfile

from pet_growth import PetGrowthSystem


def diff(new, old):
    return new - old


with tempfile.TemporaryDirectory() as directory:
    path = os.path.join(directory, "pet_state.json")
    config_path = os.path.join(directory, "pet_config.json")
    pet = PetGrowthSystem(path, config_path)

    # First 45-minute focus milestone and each extra 30 minutes award once.
    state = pet.update(True, 2700, 2500, 600, 0, "2026-08-27", diff)
    assert state["growth"] == 5 and state["event"] == "FOCUS +5"
    state = pet.update(True, 4500, 2500, 600, 1000, "2026-08-27", diff)
    assert state["growth"] == 8 and state["event"] == "FOCUS +3"
    state = pet.update(True, 4501, 2500, 600, 2000, "2026-08-27", diff)
    assert state["growth"] == 8

    # A new session can earn the focus milestone again.
    pet.update(False, 4501, 2500, None, 3000, "2026-08-27", diff)
    state = pet.update(True, 2700, 2500, 600, 4000, "2026-08-27", diff)
    assert state["growth"] == 13

    # Four accumulated hours award the daily goal exactly once.
    pet.daily_study_ms = pet.daily_goal_seconds * 1000 - 1000
    pet.last_update_ms = 4000
    state = pet.update(True, 10, 2500, 600, 5000, "2026-08-27", diff)
    assert state["daily_goal_awarded"]
    assert state["growth"] == 63
    pet.update(True, 11, 2500, 600, 6000, "2026-08-27", diff)
    assert pet.growth == 63

    # Bad light/distance has a 10-second grace, then drains one point/30 sec.
    pet.stamina = 50
    pet.last_update_ms = 6000
    for second in range(1, 41):
        state = pet.update(
            True, 12 + second, 100, 1200,
            6000 + second * 1000, "2026-08-27", diff,
        )
    assert state["stamina"] == 49 and not state["environment_ok"]

    # Five minutes in a good study environment restores one point.
    for second in range(1, 301):
        state = pet.update(
            True, 60 + second, 2500, 600,
            46_000 + second * 1000, "2026-08-27", diff,
        )
    assert state["stamina"] == 50 and state["environment_ok"]

    # Daily study resets on the next valid date; lifetime growth/stamina remain.
    growth_before = pet.growth
    stamina_before = pet.stamina
    state = pet.update(False, 0, 2500, None, 347_000, "2026-08-28", diff)
    assert state["daily_study_seconds"] == 0
    assert not state["daily_goal_awarded"]
    assert state["growth"] == growth_before
    assert state["stamina"] == stamina_before

    # A backwards unsynchronised clock must not erase the new day's progress.
    pet.daily_study_ms = 123_000
    pet.update(False, 0, 2500, None, 348_000, "2026-08-24", diff)
    assert pet.day_key == "2026-08-28" and pet.daily_study_ms == 123_000

    # Growth above 80 maps to new image 2; exactly 80 remains normal.
    pet.growth = 80
    assert pet.stage() == 1
    pet.growth = 81
    assert pet.stage() == 2

    # HP below 30 overrides the growth image with the new sick image 1.
    pet.stamina = 30
    assert pet.visual_state() == "EVOLVED"
    pet.stamina = 29
    assert pet.visual_state() == "SICK"

    # Future app configuration is persisted and hot-reloaded from JSON.
    assert pet.set_daily_goal_seconds(2 * 3600) == 7200
    configured = PetGrowthSystem(path, config_path)
    assert configured.daily_goal_seconds == 7200

    pet.save()
    restored = PetGrowthSystem(path, config_path)
    assert restored.growth == 81
    assert restored.stamina == 29
    assert restored.day_key == "2026-08-28"

print("pet growth tests: OK")
