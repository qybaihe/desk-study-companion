"""Deterministic voice commands that must be executed on the ESP32.

These commands are parsed before the general study-question agent runs.  A
strict intent check prevents ordinary questions containing a duration from
changing device settings accidentally.
"""

from __future__ import annotations

import re
from typing import Any


MIN_DAILY_GOAL_SECONDS = 5 * 60
MAX_DAILY_GOAL_SECONDS = 24 * 60 * 60

_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_UNITS = {"十": 10, "百": 100, "千": 1000}
_NUMBER_PATTERN = r"(?:\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百千点]+)"
_SETTER_PHRASES = (
    "设置成",
    "设置为",
    "设成",
    "设为",
    "修改成",
    "修改为",
    "改成",
    "改为",
    "调整成",
    "调整为",
    "调成",
    "调为",
    "调到",
    "定成",
    "定为",
    "设置",
    "修改",
    "调整",
)
_FULLWIDTH_TRANSLATION = str.maketrans(
    "０１２３４５６７８９．，：；（）％",
    "0123456789.,:;()%",
)


def _normalize(text: str) -> str:
    return (
        str(text or "")
        .translate(_FULLWIDTH_TRANSLATION)
        .lower()
        .replace(" ", "")
        .replace("\u3000", "")
        .replace("鐘頭", "小时")
        .replace("钟头", "小时")
    )


def _parse_chinese_integer(text: str) -> int | None:
    if not text:
        return 0
    total = 0
    digit: int | None = None
    for character in text:
        if character in _DIGITS:
            digit = _DIGITS[character]
            continue
        unit = _UNITS.get(character)
        if unit is None:
            return None
        total += (1 if digit is None else digit) * unit
        digit = None
    return total + (0 if digit is None else digit)


def _parse_number(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        pass
    if "点" not in text:
        integer = _parse_chinese_integer(text)
        return None if integer is None else float(integer)
    left, right = text.split("点", 1)
    integer = _parse_chinese_integer(left)
    if integer is None or not right:
        return None
    fraction = 0.0
    place = 0.1
    for character in right:
        if character not in _DIGITS:
            return None
        fraction += _DIGITS[character] * place
        place /= 10
    return integer + fraction


def parse_duration_seconds(text: str) -> int | None:
    """Parse common Mandarin hour/minute expressions to whole minutes."""

    normalized = _normalize(text)
    hours = 0.0
    minutes = 0.0
    found = False

    hour_half = re.search(
        r"(" + _NUMBER_PATTERN + r")(?:个)?半小时", normalized
    )
    if hour_half:
        number = _parse_number(hour_half.group(1))
        if number is not None:
            hours = number + 0.5
            found = True
    else:
        hour_match = re.search(
            r"(" + _NUMBER_PATTERN + r")(?:个)?小时", normalized
        )
        if hour_match:
            number = _parse_number(hour_match.group(1))
            if number is not None:
                hours = number
                found = True
                if normalized[hour_match.end() :].startswith("半"):
                    hours += 0.5
        elif "半小时" in normalized:
            hours = 0.5
            found = True

    minute_match = re.search(
        r"(" + _NUMBER_PATTERN + r")(?:分钟|分)", normalized
    )
    if minute_match:
        number = _parse_number(minute_match.group(1))
        if number is not None:
            minutes = number
            found = True

    if not found:
        return None
    seconds = round((hours * 60 + minutes) * 60)
    # Configuration and UI operate at minute precision.
    return int(round(seconds / 60) * 60)


def format_duration_zh(seconds: int) -> str:
    total_minutes = max(0, int(seconds)) // 60
    hours, minutes = divmod(total_minutes, 60)
    parts = []
    if hours:
        parts.append("%d小时" % hours)
    if minutes or not parts:
        parts.append("%d分钟" % minutes)
    return "".join(parts)


def match_device_command(transcript: str) -> dict[str, Any] | None:
    """Return a local command response, or ``None`` for a normal question."""

    normalized = _normalize(transcript)
    has_goal_subject = (
        "目标" in normalized
        and any(
            subject in normalized
            for subject in ("学习", "每日", "每天", "今日", "今天")
        )
    ) or "学习时长" in normalized
    if not has_goal_subject:
        return None

    setter_position = -1
    setter_length = 0
    for setter in _SETTER_PHRASES:
        position = normalized.rfind(setter)
        if position > setter_position or (
            position == setter_position and len(setter) > setter_length
        ):
            setter_position = position
            setter_length = len(setter)
    if setter_position < 0:
        return None

    duration_text = normalized[setter_position + setter_length :]
    seconds = parse_duration_seconds(duration_text)
    if seconds is None:
        spoken = "请说，例如，把每日学习目标设置为两小时。"
        return {
            "answer": {
                "needs_repeat": True,
                "short_answer": "没有听清目标时长",
                "spoken_answer": spoken,
            },
            "device_action": None,
            "command_error": "missing_duration",
        }
    if not MIN_DAILY_GOAL_SECONDS <= seconds <= MAX_DAILY_GOAL_SECONDS:
        spoken = "每日学习目标需要设置在五分钟到二十四小时之间。"
        return {
            "answer": {
                "needs_repeat": True,
                "short_answer": "目标时长超出范围",
                "spoken_answer": spoken,
            },
            "device_action": None,
            "command_error": "duration_out_of_range",
        }

    duration = format_duration_zh(seconds)
    spoken = "好的，每日学习目标已设置为%s。完成目标可获得六十成长值。" % duration
    return {
        "answer": {
            "needs_repeat": False,
            "short_answer": "每日学习目标已设置为%s" % duration,
            "spoken_answer": spoken,
        },
        "device_action": {
            "type": "set_daily_goal_seconds",
            "seconds": seconds,
        },
        "command_error": "",
    }
