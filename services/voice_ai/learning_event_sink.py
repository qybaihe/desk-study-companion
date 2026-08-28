#!/usr/bin/env python3
"""Persist learning events and optionally forward them to TiDB Agent Stack."""

from __future__ import annotations

import json
import os
import threading
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import tidb_store


ROOT = Path(__file__).resolve().parent
SPOOL_DIR = ROOT / "event_spool"
SPOOL_PATH = SPOOL_DIR / "learning_events.jsonl"
_SPOOL_LOCK = threading.Lock()


def _post_json(url: str, token: str, event: dict[str, Any]) -> int:
    body = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        response.read(1024)
        return int(response.status)


def publish_learning_event(event: dict[str, Any]) -> dict[str, Any]:
    """Spool locally, persist to TiDB, and optionally forward to Agent Stack."""
    enriched = dict(event)
    enriched.setdefault("event_id", str(uuid.uuid4()))
    enriched.setdefault(
        "event_created_at",
        datetime.now().astimezone().isoformat(timespec="seconds"),
    )
    SPOOL_DIR.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(enriched, ensure_ascii=False, separators=(",", ":"))
    with _SPOOL_LOCK:
        with SPOOL_PATH.open("a", encoding="utf-8") as spool:
            spool.write(encoded + "\n")

    url = os.environ.get("TIDB_AGENT_STACK_URL", "").strip()
    token = os.environ.get("TIDB_AGENT_STACK_TOKEN", "").strip()
    delivery: dict[str, Any] = {
        "spooled": True,
        "spool_path": str(SPOOL_PATH.resolve()),
        "agent_stack_configured": bool(url),
        "tidb_configured": tidb_store.configured(),
    }
    if delivery["tidb_configured"]:
        try:
            delivery["tidb_event_id"] = tidb_store.persist_event(enriched)
            delivery["tidb_delivered"] = True
        except Exception as error:
            delivery["tidb_delivered"] = False
            delivery["tidb_error"] = str(error)
    else:
        delivery["tidb_delivered"] = False
    if url:
        try:
            delivery["http_status"] = _post_json(url, token, enriched)
            delivery["delivered"] = True
        except Exception as error:
            delivery["delivered"] = False
            delivery["error"] = str(error)
    else:
        delivery["delivered"] = False
    return delivery
