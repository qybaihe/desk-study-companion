from voice_device_actions import VoiceDeviceActionHandler


class FakePetSystem:
    def __init__(self):
        self.daily_goal_seconds = 4 * 60 * 60
        self.calls = 0

    def set_daily_goal_seconds(self, seconds):
        self.calls += 1
        self.daily_goal_seconds = int(seconds)
        return self.daily_goal_seconds


pet = FakePetSystem()
handler = VoiceDeviceActionHandler(pet)
response = {
    "device_action": {
        "id": "voice-action-1",
        "type": "set_daily_goal_seconds",
        "seconds": 7200,
    }
}
result = handler.consume(response)
assert result == {
    "ok": True,
    "type": "set_daily_goal_seconds",
    "seconds": 7200,
}
assert pet.daily_goal_seconds == 7200 and pet.calls == 1

# The response remains visible for many display loops, but applies only once.
assert handler.consume(response) is None
assert pet.calls == 1

invalid = {
    "device_action": {
        "id": "voice-action-2",
        "type": "set_daily_goal_seconds",
        "seconds": 60,
    }
}
assert handler.consume(invalid) == {
    "ok": False,
    "error": "goal_out_of_range",
}
assert pet.calls == 1

print("voice device action tests: OK")
