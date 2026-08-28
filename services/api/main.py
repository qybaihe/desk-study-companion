"""书桌学习伴侣 · HTTP 中转层

一个后端服务两端：
  ESP32  --POST /ingest-->  写 TiDB，响应里回带配置（配置下行通道）
  iOS App --GET /api/*-->   读 TiDB

设备和 App 互不知道对方存在。数据库凭据只存在这里。
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

import db
import features

app = FastAPI(title="Banxue API", version="0.1")

USE_DB = db.configured()


# ---------------------------------------------------------------- 设备上报

class MinuteSample(BaseModel):
    ts: datetime
    present: bool = False
    distance_mm: Optional[int] = None
    light_left: Optional[int] = None
    light_right: Optional[int] = None
    temperature: Optional[float] = None
    humidity: Optional[int] = None
    pir_hits: int = 0
    abnormal: bool = False


class IngestBody(BaseModel):
    """攒 30–60 秒一批。ESP32 的 TLS 握手开销远大于传输本身，
    减少连接次数比压缩数据重要得多。"""
    device_id: str
    child_id: str
    firmware: Optional[str] = None
    samples: list[MinuteSample] = Field(default_factory=list)
    hp: Optional[int] = None
    grow: Optional[int] = None
    form: Optional[str] = None


DEFAULT_CONFIG = {
    "rev": 1, "goal_hours": 4, "distance_min": 400, "distance_max": 850,
    # 实测常态室内光照 ADC 3935（12 位满量程 4095），原阈值 1500 几乎永不触发
    "light_min": 3600,
    "cooldown_s": 1800, "voice_on": 1, "anim_on": 1, "push_on": 1, "child_visible": 1,
}


def _config_for(child_id: str) -> dict[str, Any]:
    if not USE_DB:
        return DEFAULT_CONFIG
    with db.cursor() as cur:
        cur.execute("SELECT * FROM device_config WHERE child_id=%s", (child_id,))
        row = cur.fetchone()
    if not row:
        return DEFAULT_CONFIG
    row.pop("updated_at", None)
    row.pop("child_id", None)
    return row


@app.post("/ingest")
def ingest(body: IngestBody) -> dict[str, Any]:
    """写入并在响应里回带配置 —— 设备比对 rev，变了就落盘生效。
    零额外连接、零额外协议，配置变更在一个上报周期内生效。"""
    if USE_DB and body.samples:
        rows = [
            (body.child_id, body.device_id, s.ts, int(s.present), s.distance_mm,
             s.light_left, s.light_right, s.temperature, s.humidity,
             s.pir_hits, int(s.abnormal))
            for s in body.samples
        ]
        with db.cursor() as cur:
            cur.executemany(
                """INSERT INTO sensor_minute
                   (child_id, device_id, ts, present, distance_mm, light_left, light_right,
                    temperature, humidity, pir_hits, abnormal)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE present=VALUES(present),
                     distance_mm=VALUES(distance_mm), light_left=VALUES(light_left),
                     light_right=VALUES(light_right), temperature=VALUES(temperature),
                     humidity=VALUES(humidity), pir_hits=VALUES(pir_hits),
                     abnormal=VALUES(abnormal)""", rows)
            cur.execute(
                """INSERT INTO device (device_id, child_id, firmware, last_seen)
                   VALUES (%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE firmware=VALUES(firmware), last_seen=VALUES(last_seen)""",
                (body.device_id, body.child_id, body.firmware, datetime.utcnow()))
            if body.hp is not None:
                cur.execute(
                    """INSERT INTO pet_state (child_id, hp, grow, form, updated_at)
                       VALUES (%s,%s,%s,%s,%s)
                       ON DUPLICATE KEY UPDATE hp=VALUES(hp), grow=VALUES(grow),
                         form=VALUES(form), updated_at=VALUES(updated_at)""",
                    (body.child_id, body.hp, body.grow or 0, body.form or "normal",
                     datetime.utcnow()))
    return {"ok": True, "accepted": len(body.samples), "config": _config_for(body.child_id)}


@app.get("/config")
def config(child_id: str = Query(...)) -> dict[str, Any]:
    return _config_for(child_id)


# ---------------------------------------------------------------- App 读取
#
# 下面八个端点对应 iOS 的 APISource。未接库时返回演示数据，
# 接库后由 SQL 聚合填充 —— 结构完全一致，App 侧不需要改任何代码。

from mockdata import MOCK  # noqa: E402


def _serve(key: str, child_id: str) -> Any:
    if not USE_DB:
        return MOCK[key]
    fn = globals().get(f"_db_{key}")
    if fn is None:
        return MOCK[key]
    try:
        return fn(child_id)
    except Exception as exc:  # 查询失败时不假装有数据
        raise HTTPException(status_code=503, detail=f"查询失败: {exc}") from exc


@app.get("/api/snapshot")
def api_snapshot(child_id: str = Query(...)): return _serve("snapshot", child_id)

@app.get("/api/eye")
def api_eye(child_id: str = Query(...)): return _serve("eye", child_id)

@app.get("/api/study")
def api_study(child_id: str = Query(...)): return _serve("study", child_id)

@app.get("/api/diary")
def api_diary(child_id: str = Query(...)): return _serve("diary", child_id)

@app.get("/api/milestones")
def api_milestones(child_id: str = Query(...)): return _serve("milestones", child_id)

@app.get("/api/weekly")
def api_weekly(child_id: str = Query(...)): return _serve("weekly", child_id)

@app.get("/api/reminders")
def api_reminders(child_id: str = Query(...)): return _serve("reminders", child_id)

@app.get("/api/settings")
def api_settings(child_id: str = Query(...)): return _serve("settings", child_id)


# ---------------------------------------------------------------- 真实查询

def _db_snapshot(child_id: str) -> dict[str, Any]:
    with db.cursor() as cur:
        cur.execute(
            """SELECT * FROM sensor_minute WHERE child_id=%s
               ORDER BY ts DESC LIMIT 1""", (child_id,))
        last = cur.fetchone()
        cur.execute(
            """SELECT COALESCE(SUM(present),0) AS mins FROM sensor_minute
               WHERE child_id=%s AND ts >= %s""",
            (child_id, datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)))
        today = cur.fetchone()["mins"]
        cur.execute("SELECT * FROM pet_state WHERE child_id=%s", (child_id,))
        pet = cur.fetchone() or {"hp": 100, "grow": 0, "form": "normal"}
        cur.execute("SELECT last_seen FROM device WHERE child_id=%s ORDER BY last_seen DESC LIMIT 1",
                    (child_id,))
        dev = cur.fetchone()

    online = bool(dev and dev["last_seen"] and
                  datetime.utcnow() - dev["last_seen"] < timedelta(seconds=90))
    cfg = _config_for(child_id)
    base = dict(MOCK["snapshot"])
    base.update({
        "form": pet.get("form", "normal"),
        "link": "online" if online else "offline",
        "hp": pet.get("hp", 100),
        "grow": pet.get("grow", 0),
        "todayMinutes": int(today),
        "goalHours": cfg["goal_hours"],
        "lightLeft": (last or {}).get("light_left") or 0,
        "lightRight": (last or {}).get("light_right") or 0,
        "temperature": float((last or {}).get("temperature") or 0),
        "humidity": int((last or {}).get("humidity") or 0),
        "lastSync": dev["last_seen"].strftime("%H:%M") if dev and dev["last_seen"] else "—",
    })
    return base


def _db_reminders(child_id: str) -> dict[str, Any]:
    since = datetime.utcnow() - timedelta(days=7)
    with db.cursor() as cur:
        cur.execute(
            """SELECT fired_at, kind, detail, improved FROM reminder_event
               WHERE child_id=%s AND fired_at >= %s ORDER BY fired_at""", (child_id, since))
        rows = cur.fetchall()
    items = [{
        "when": r["fired_at"].strftime("%m-%d %H:%M"),
        "kind": r["kind"],
        "detail": r["detail"] or "",
        "improved": bool(r["improved"]),
    } for r in rows]
    total = len(items)
    improved = sum(1 for i in items if i["improved"])
    out = dict(MOCK["reminders"])
    out.update({"total": total, "improved": improved,
                "rate": (improved * 100 // total) if total else 0,
                "items": items})
    return out


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "db": USE_DB}


@app.on_event("startup")
def _startup() -> None:
    if USE_DB and os.environ.get("AUTO_MIGRATE", "1") == "1":
        db.ensure_schema()
