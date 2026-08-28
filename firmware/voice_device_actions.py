"""Apply authenticated voice-server actions exactly once on the device."""


class VoiceDeviceActionHandler:
    MIN_DAILY_GOAL_SECONDS = 5 * 60
    MAX_DAILY_GOAL_SECONDS = 24 * 60 * 60

    def __init__(self, pet_system):
        self.pet_system = pet_system
        self.last_action_id = ""
        self.last_result = None

    def consume(self, response):
        if not isinstance(response, dict):
            return None
        action = response.get("device_action")
        if not isinstance(action, dict):
            return None
        action_id = str(action.get("id", ""))
        if not action_id or action_id == self.last_action_id:
            return None

        # Mark first so a malformed action cannot be retried on every display
        # loop while the same answer is playing.
        self.last_action_id = action_id
        action_type = str(action.get("type", ""))
        if action_type != "set_daily_goal_seconds":
            result = {"ok": False, "error": "unsupported_action"}
        else:
            try:
                requested = int(action.get("seconds", 0))
            except Exception:
                requested = 0
            if not (
                self.MIN_DAILY_GOAL_SECONDS
                <= requested
                <= self.MAX_DAILY_GOAL_SECONDS
            ):
                result = {"ok": False, "error": "goal_out_of_range"}
            else:
                applied = self.pet_system.set_daily_goal_seconds(requested)
                result = {
                    "ok": applied == requested,
                    "type": action_type,
                    "seconds": applied,
                }

        response["device_action_result"] = result
        self.last_result = result
        return result
