#!/usr/bin/env python3
"""Offline checks for deterministic ESP32 voice commands."""

from device_commands import (
    format_duration_zh,
    match_device_command,
    parse_duration_seconds,
)


assert parse_duration_seconds("两个小时") == 7200
assert parse_duration_seconds("一个半小时") == 5400
assert parse_duration_seconds("两小时半") == 9000
assert parse_duration_seconds("一小时三十分钟") == 5400
assert parse_duration_seconds("九十分钟") == 5400
assert parse_duration_seconds("1.25小时") == 4500
assert parse_duration_seconds("半小时") == 1800
assert format_duration_zh(9000) == "2小时30分钟"

command = match_device_command("把每日学习目标设置为两个半小时")
assert command is not None
assert command["device_action"] == {
    "type": "set_daily_goal_seconds",
    "seconds": 9000,
}
assert "2小时30分钟" in command["answer"]["spoken_answer"]

command = match_device_command("将今天的学习目标改为九十分钟")
assert command is not None
assert command["device_action"]["seconds"] == 5400

# General questions and descriptive statements must never change a setting.
assert match_device_command("每天学习两个小时有什么好处") is None
assert match_device_command("我的学习目标是多少") is None
assert match_device_command("一加一等于几") is None

invalid = match_device_command("把每日学习目标设置为两分钟")
assert invalid is not None
assert invalid["device_action"] is None
assert invalid["command_error"] == "duration_out_of_range"

missing = match_device_command("请修改每日学习目标")
assert missing is not None
assert missing["device_action"] is None
assert missing["command_error"] == "missing_duration"

print("device command tests: OK")
