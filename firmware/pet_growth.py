"""Persistent cultivation rules for the desk-companion pet."""

try:
    import ujson as json
except ImportError:
    import json


class PetGrowthSystem:
    # Growth rewards.
    DEFAULT_DAILY_GOAL_SECONDS = 4 * 60 * 60
    DAILY_GOAL_REWARD = 50
    FIRST_FOCUS_SECONDS = 45 * 60
    FIRST_FOCUS_REWARD = 5
    EXTRA_FOCUS_SECONDS = 30 * 60
    EXTRA_FOCUS_REWARD = 3

    # Image 2 becomes the healthy evolved state only above 80 growth.
    EVOLVED_GROWTH = 80

    # Environment and stamina. ADC values are relative intensity, not lux.
    LIGHT_MIN = 1500
    LIGHT_MAX = 4050
    DISTANCE_MIN_MM = 400
    DISTANCE_MAX_MM = 850
    SICK_STAMINA = 30
    BAD_ENVIRONMENT_GRACE_MS = 10_000
    BAD_DRAIN_INTERVAL_MS = 30_000
    GOOD_RECOVER_INTERVAL_MS = 5 * 60_000
    AWAY_RECOVER_INTERVAL_MS = 3 * 60_000
    SAVE_INTERVAL_MS = 60_000
    CONFIG_RELOAD_MS = 5_000
    EVENT_VISIBLE_MS = 8_000

    def __init__(
        self,
        state_path="/pet_state.json",
        config_path="/pet_config.json",
    ):
        self.state_path = state_path
        self.config_path = config_path
        self.daily_goal_seconds = self.DEFAULT_DAILY_GOAL_SECONDS
        self.day_key = ""
        self.daily_study_ms = 0
        self.daily_goal_awarded = False
        self.growth = 0
        self.stamina = 100
        self.recover_accumulator_ms = 0
        self.drain_accumulator_ms = 0

        self.last_update_ms = None
        self.last_save_ms = None
        self.last_config_check_ms = None
        self.bad_environment_ms = 0
        self.last_session_seconds = 0
        self.session_milestones_awarded = 0
        self.was_sick = False
        self.last_event = ""
        self.last_event_at = None
        self._load_config()
        self._load()
        self.was_sick = self.stamina < self.SICK_STAMINA

    @staticmethod
    def _date_number(day_key):
        try:
            year, month, day = [int(part) for part in day_key.split("-")]
            if year < 2025 or not 1 <= month <= 12 or not 1 <= day <= 31:
                return 0
            return year * 10_000 + month * 100 + day
        except Exception:
            return 0

    def _load(self):
        try:
            with open(self.state_path, "r") as state_file:
                state = json.loads(state_file.read())
            self.day_key = str(state.get("day_key", ""))
            self.daily_study_ms = max(0, int(state.get("daily_study_ms", 0)))
            self.daily_goal_awarded = bool(
                state.get("daily_goal_awarded", False)
            )
            self.growth = max(0, min(999, int(state.get("growth", 0))))
            self.stamina = max(0, min(100, int(state.get("stamina", 100))))
            self.recover_accumulator_ms = max(
                0, int(state.get("recover_accumulator_ms", 0))
            )
            self.drain_accumulator_ms = max(
                0, int(state.get("drain_accumulator_ms", 0))
            )
        except Exception:
            pass

    def save(self):
        state = {
            "version": 1,
            "day_key": self.day_key,
            "daily_study_ms": self.daily_study_ms,
            "daily_goal_awarded": self.daily_goal_awarded,
            "growth": self.growth,
            "stamina": self.stamina,
            "recover_accumulator_ms": self.recover_accumulator_ms,
            "drain_accumulator_ms": self.drain_accumulator_ms,
        }
        try:
            with open(self.state_path, "w") as state_file:
                state_file.write(json.dumps(state))
                try:
                    state_file.flush()
                except Exception:
                    pass
            return True
        except Exception:
            return False

    def _load_config(self):
        previous_goal = self.daily_goal_seconds
        try:
            with open(self.config_path, "r") as config_file:
                config = json.loads(config_file.read())
            configured_goal = int(
                config.get("daily_goal_seconds", self.DEFAULT_DAILY_GOAL_SECONDS)
            )
            self.daily_goal_seconds = max(300, min(86_400, configured_goal))
        except Exception:
            self.daily_goal_seconds = previous_goal
            try:
                with open(self.config_path, "r"):
                    pass
            except Exception:
                self.save_config()
        return self.daily_goal_seconds != previous_goal

    def save_config(self):
        config = {
            "version": 1,
            "daily_goal_seconds": self.daily_goal_seconds,
        }
        try:
            with open(self.config_path, "w") as config_file:
                config_file.write(json.dumps(config))
                try:
                    config_file.flush()
                except Exception:
                    pass
            return True
        except Exception:
            return False

    def set_daily_goal_seconds(self, seconds):
        """Configuration hook reserved for the future app."""
        self.daily_goal_seconds = max(300, min(86_400, int(seconds)))
        self.save_config()
        return self.daily_goal_seconds

    def stage(self):
        return 2 if self.growth > self.EVOLVED_GROWTH else 1

    def visual_state(self):
        if self.stamina < self.SICK_STAMINA:
            return "SICK"
        if self.growth > self.EVOLVED_GROWTH:
            return "EVOLVED"
        return "NORMAL"

    def _roll_day(self, current_day_key):
        current_number = self._date_number(current_day_key)
        stored_number = self._date_number(self.day_key)
        if not current_number:
            return False
        if not stored_number:
            self.day_key = current_day_key
            self.daily_study_ms = 0
            self.daily_goal_awarded = False
            return True
        if current_number > stored_number:
            self.day_key = current_day_key
            self.daily_study_ms = 0
            self.daily_goal_awarded = False
            return True
        # Ignore a clock that jumped backwards after an un-synchronised reboot.
        return False

    def _focus_milestone_count(self, session_seconds):
        if session_seconds < self.FIRST_FOCUS_SECONDS:
            return 0
        return 1 + (
            (session_seconds - self.FIRST_FOCUS_SECONDS)
            // self.EXTRA_FOCUS_SECONDS
        )

    def _update_focus_rewards(self, present, session_seconds, events):
        if not present:
            self.last_session_seconds = 0
            self.session_milestones_awarded = 0
            return False

        session_seconds = max(0, int(session_seconds))
        if session_seconds < self.last_session_seconds:
            self.session_milestones_awarded = 0
        self.last_session_seconds = session_seconds

        reached = self._focus_milestone_count(session_seconds)
        if reached <= self.session_milestones_awarded:
            return False

        reward = 0
        while self.session_milestones_awarded < reached:
            if self.session_milestones_awarded == 0:
                reward += self.FIRST_FOCUS_REWARD
            else:
                reward += self.EXTRA_FOCUS_REWARD
            self.session_milestones_awarded += 1
        self.growth = min(999, self.growth + reward)
        events.append("FOCUS +%d" % reward)
        return True

    def _change_stamina(self, delta):
        before = self.stamina
        self.stamina = max(0, min(100, self.stamina + delta))
        return before != self.stamina

    def _update_stamina(self, present, environment_ok, elapsed_ms):
        changed = False
        if present and not environment_ok:
            self.recover_accumulator_ms = 0
            before_bad = self.bad_environment_ms
            self.bad_environment_ms += elapsed_ms
            penalty_elapsed = max(
                0,
                self.bad_environment_ms
                - max(before_bad, self.BAD_ENVIRONMENT_GRACE_MS),
            )
            self.drain_accumulator_ms += penalty_elapsed
            while self.drain_accumulator_ms >= self.BAD_DRAIN_INTERVAL_MS:
                self.drain_accumulator_ms -= self.BAD_DRAIN_INTERVAL_MS
                changed = self._change_stamina(-1) or changed
                if self.stamina == 0:
                    self.drain_accumulator_ms = 0
                    break
        else:
            self.bad_environment_ms = 0
            self.drain_accumulator_ms = 0
            interval = (
                self.GOOD_RECOVER_INTERVAL_MS
                if present
                else self.AWAY_RECOVER_INTERVAL_MS
            )
            self.recover_accumulator_ms += elapsed_ms
            while self.recover_accumulator_ms >= interval:
                self.recover_accumulator_ms -= interval
                changed = self._change_stamina(1) or changed
                if self.stamina == 100:
                    self.recover_accumulator_ms = 0
                    break
        return changed

    def update(
        self,
        present,
        session_seconds,
        light_value,
        distance_mm,
        now_ms,
        day_key,
        ticks_diff,
    ):
        events = []
        if (
            self.last_config_check_ms is None
            or ticks_diff(now_ms, self.last_config_check_ms)
            >= self.CONFIG_RELOAD_MS
        ):
            self._load_config()
            self.last_config_check_ms = now_ms
        important_change = self._roll_day(day_key)
        previous_stage = self.stage()

        if self.last_update_ms is None:
            elapsed_ms = 0
        else:
            elapsed_ms = max(0, ticks_diff(now_ms, self.last_update_ms))
            # A delayed sensor read must not fabricate minutes of study time.
            elapsed_ms = min(elapsed_ms, 10_000)
        self.last_update_ms = now_ms

        present = bool(present)
        if present:
            self.daily_study_ms += elapsed_ms

        if (
            not self.daily_goal_awarded
            and self.daily_study_ms >= self.daily_goal_seconds * 1000
        ):
            self.daily_goal_awarded = True
            self.growth = min(999, self.growth + self.DAILY_GOAL_REWARD)
            events.append("GOAL +%d" % self.DAILY_GOAL_REWARD)
            important_change = True

        if self._update_focus_rewards(present, session_seconds, events):
            important_change = True

        light_ok = self.LIGHT_MIN <= light_value <= self.LIGHT_MAX
        distance_ok = (
            distance_mm is not None
            and self.DISTANCE_MIN_MM <= distance_mm <= self.DISTANCE_MAX_MM
        )
        environment_ok = (light_ok and distance_ok) if present else True
        if self._update_stamina(present, environment_ok, elapsed_ms):
            important_change = True

        sick = self.stamina < self.SICK_STAMINA
        if sick != self.was_sick:
            events.append("SICK" if sick else "RECOVERED")
            self.was_sick = sick
            important_change = True

        current_stage = self.stage()
        if current_stage != previous_stage:
            events.append("EVOLVED" if current_stage == 2 else "NORMAL")
            important_change = True

        if events:
            self.last_event = events[-1]
            self.last_event_at = now_ms

        event = ""
        if (
            self.last_event_at is not None
            and ticks_diff(now_ms, self.last_event_at) < self.EVENT_VISIBLE_MS
        ):
            event = self.last_event

        should_save = important_change or self.last_save_ms is None
        if (
            self.last_save_ms is not None
            and ticks_diff(now_ms, self.last_save_ms) >= self.SAVE_INTERVAL_MS
        ):
            should_save = True
        if should_save and self.save():
            self.last_save_ms = now_ms

        daily_seconds = self.daily_study_ms // 1000
        return {
            "day_key": self.day_key,
            "daily_study_seconds": daily_seconds,
            "daily_goal_seconds": self.daily_goal_seconds,
            "daily_goal_percent": min(
                100, daily_seconds * 100 // self.daily_goal_seconds
            ),
            "daily_goal_awarded": self.daily_goal_awarded,
            "growth": self.growth,
            "stage": current_stage,
            "visual_state": self.visual_state(),
            "stamina": self.stamina,
            "sick": sick,
            "light_ok": light_ok,
            "distance_ok": distance_ok,
            "environment_ok": environment_ok,
            "event": event,
        }
