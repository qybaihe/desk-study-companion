#!/usr/bin/env python3
"""往线上灌一段可信的历史数据，用来验证 /api/study 和 /api/eye 的实时计算。

只走公开的 /ingest 接口 —— 和板子走的是同一条路，所以它同时也是一次
端到端链路自检。库里一律存 UTC，北京时间只在 Worker 里做展示转换。
"""
import argparse, datetime as dt, json, math, random, urllib.request

# 有些网络（比如国内不少家宽）没有到 Cloudflare 的 IPv6 路由，而 Python 的
# urllib 会优先试 AAAA 然后卡住。强制走 IPv4 —— 浏览器和 URLSession 有
# Happy Eyeballs 会自动回退，urllib 没有。
import socket as _socket
_orig_getaddrinfo = _socket.getaddrinfo
def _ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, _socket.AF_INET, type, proto, flags)
_socket.getaddrinfo = _ipv4_only


BASE = "https://sheepy.timoz.me"
CST = dt.timezone(dt.timedelta(hours=8))


def post(path, body, token):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + token,
                 # 默认的 Python-urllib UA 会被 Cloudflare 边缘挡成 403
                 "User-Agent": "sheepy-seed/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def session(day, start_h, minutes, rng):
    """一段学习：在座为主，中间穿插离开和光线偏暗。"""
    out = []
    t = day.replace(hour=start_h, minute=0, second=0, microsecond=0)
    away_at = {rng.randrange(15, minutes - 10) for _ in range(2)}
    away_left = 0
    for i in range(minutes):
        if i in away_at:
            away_left = rng.randrange(6, 14)
        present = away_left == 0
        if away_left:
            away_left -= 1
        dark = present and (0.35 < ((i / minutes) % 0.5) < 0.45)
        light = rng.randrange(3300, 3560) if dark else rng.randrange(3700, 3980)
        # 越坐越往前凑，是真实会发生的漂移
        drift = int(120 * math.sin(i / 18.0)) - int(i * 1.1)
        dist = max(280, min(1000, 640 + drift + rng.randrange(-40, 40)))
        out.append({
            "ts": (t + dt.timedelta(minutes=i)).astimezone(dt.timezone.utc)
                    .strftime("%Y-%m-%d %H:%M:00"),
            "present": present,
            "distance_mm": dist if present else None,
            "light_left": light,
            "light_right": light - rng.randrange(20, 90),
            "temperature": round(25.5 + rng.random() * 2, 1),
            "humidity": rng.randrange(52, 63),
            "pir_hits": rng.randrange(3, 12) if present else 0,
            "abnormal": bool(present and dark),
        })
    return out


ASKS = [
    ("数学应用题", "这道题为什么要先算括号里的？"),
    ("数学应用题", "鸡兔同笼怎么列式子？"),
    ("数学应用题", "小数点对齐是什么意思？"),
    ("生字读音", "「畜」这个字什么时候读 chù？"),
    ("生字读音", "「差」有几个读音？"),
    ("英语单词", "practice 和 practise 有区别吗？"),
    ("英语单词", "为什么 mouse 的复数是 mice？"),
    ("科学常识", "为什么天是蓝的？"),
]


def seed_asks(day, rng, token, child):
    """给这一天造几条提问。板子的 voice_qa_client 将来打的是同一个口。"""
    n = rng.randrange(0, 5)
    for _ in range(n):
        topic, q = ASKS[rng.randrange(len(ASKS))]
        t = day.replace(hour=rng.randrange(15, 21), minute=rng.randrange(0, 60),
                        second=0, microsecond=0)
        post("/api/ask", {
            "child_id": child, "topic": topic, "question": q,
            "asked_at": t.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }, token)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--child", default="sheepy")
    ap.add_argument("--device", default="sim-demo")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--skip-recent", type=int, default=0,
                    help="跳过最近 N 天，用来只补历史、不动已有数据")
    a = ap.parse_args()

    rng = random.Random(20260828)
    now = dt.datetime.now(CST)
    total = 0
    for back in range(a.days - 1, a.skip_recent - 1, -1):
        day = now - dt.timedelta(days=back)
        if back == 0:
            # 今天这段一直贴到"现在"，设备状态才会显示在线
            start = max(15, now.hour - 1)
            mins = max(20, (now.hour - start) * 60 + now.minute)
        else:
            start = rng.choice([15, 16, 18, 19])
            mins = rng.randrange(40, 95)
        samples = session(day, start, mins, rng)
        for i in range(0, len(samples), 120):
            r = post("/ingest", {
                "device_id": a.device, "child_id": a.child,
                "firmware": "seed-demo",
                # 这不是设备。别让它刷新 last_seen，也别覆盖小羊的真实状态。
                "simulated": True,
                "samples": samples[i:i + 120]}, a.token)
            total += r["accepted"]
        asks = seed_asks(day, rng, a.token, a.child)
        print("D-%d  %02d:00 起 %3d 分钟  累计 %d 条  提问 %d 条"
              % (back, start, mins, total, asks))
    print("完成，共写入", total, "条")


if __name__ == "__main__":
    main()
