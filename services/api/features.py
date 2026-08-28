"""学习时段的 16 维手工特征向量。

不用文本 embedding：设备端和后端零额外成本、零额外延迟，维度低检索快，
而且每一维都有物理含义，出问题可解释、可调试。

相对最初方案改了三处：
  1. 星期从原始 0-6 改成 sin/cos —— 原来它是唯一没归一化的维度，
     数值影响力是其他维的 6 倍，且周日(6) 和周一(0) 现实相邻数值最远。
  2. 移出「护眼分」和「桌宠体力」—— 它们由距离、光照、时长派生而来，
     放进向量等于把同样的信号计入两次，人为放大权重。
  3. 末位换成「在座占比」，比派生分数信息量大。
检索用 VEC_L2_DISTANCE，不用 cosine：余弦忽略模长，但这里模长就是信号本身。
"""
from __future__ import annotations

import math
from datetime import datetime


def build(*, duration_s: int, avg_distance_mm: float, distance_var: float,
          light_percent: float, light_diff: float, close_events: int,
          close_seconds: int, lowlight_seconds: int, interruptions: int,
          started_at: datetime, temperature: float, humidity: float,
          present_ratio: float) -> list[float]:
    h = started_at.hour + started_at.minute / 60.0
    d = started_at.weekday()
    return [
        min(duration_s / 7200, 1.0),
        min(avg_distance_mm / 1000, 1.0),
        min(distance_var / 200, 1.0),
        light_percent / 100,
        (light_diff + 500) / 1000,
        min(close_events / 20, 1.0),
        min(close_seconds / 1800, 1.0),
        min(lowlight_seconds / 1800, 1.0),
        min(interruptions / 10, 1.0),
        math.sin(2 * math.pi * h / 24),
        math.cos(2 * math.pi * h / 24),
        math.sin(2 * math.pi * d / 7),
        math.cos(2 * math.pi * d / 7),
        temperature / 40,
        humidity / 100,
        present_ratio,
    ]


def to_sql(vec: list[float]) -> str:
    """TiDB VECTOR 字面量格式。"""
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"
