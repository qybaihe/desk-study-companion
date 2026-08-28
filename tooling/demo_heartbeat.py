#!/usr/bin/env python3
"""发一条设备心跳，让 App 显示「在线」—— 专门给截图用。

板子不在现场时，首页会老实显示「设备离线，读不到小羊的状态」。这是对的，
但拿去当宣传图不合适。这个脚本发一条格式完全真实的上报，让 `link` 变成在线。

注意它是**故意**不带 `simulated` 标记的 —— 和 seed_demo.py 正相反：
那个灌历史数据，绝不能碰设备存活；这个只碰设备存活，就是为了截图。

自愈：Worker 判定在线的条件是 last_seen 距今 < 90 秒，所以 90 秒后自动
回落成离线，不会留下一个长期撒谎的状态。
"""
import argparse, datetime as dt, json, urllib.request

BASE = "https://sheepy.timoz.me"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--child", default="sheepy")
    ap.add_argument("--device", default="esp32-s3-01")
    ap.add_argument("--hp", type=int, default=96)
    ap.add_argument("--grow", type=int, default=48)
    ap.add_argument("--form", default="normal",
                    help="normal / away / lowLight / restBreak / sick / evolved / fed")
    a = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    body = {
        "device_id": a.device, "child_id": a.child, "firmware": "sheepy-1.0",
        "hp": a.hp, "grow": a.grow, "form": a.form,
        "samples": [{
            "ts": now.strftime("%Y-%m-%d %H:%M:00"),
            "present": a.form != "away",
            "distance_mm": 520, "light_left": 3880, "light_right": 3810,
            "temperature": 26.0, "humidity": 55, "pir_hits": 7, "abnormal": False,
        }],
    }
    req = urllib.request.Request(
        BASE + "/ingest", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + a.token,
                 "User-Agent": "sheepy-demo/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.load(r)
    print("已上报，%d 条样本 · form=%s hp=%d grow=%d" %
          (out["accepted"], a.form, a.hp, a.grow))
    print("App 会在 90 秒内显示「在线」，之后自动回落成离线。")


if __name__ == "__main__":
    main()
