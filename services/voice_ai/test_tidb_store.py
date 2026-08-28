#!/usr/bin/env python3
"""Offline TiDB persistence tests with a recording DB-API connection."""

from __future__ import annotations

import os

import tidb_store


class RecordingCursor:
    def __init__(self, calls):
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, parameters=None):
        self.calls.append(("execute", sql, parameters))

    def executemany(self, sql, parameters):
        self.calls.append(("executemany", sql, list(parameters)))


class RecordingConnection:
    def __init__(self):
        self.calls = []
        self.closed = False

    def cursor(self):
        return RecordingCursor(self.calls)

    def close(self):
        self.closed = True


saved = {name: os.environ.pop(name, None) for name in (
    "TIDB_HOST", "TIDB_USER", "TIDB_PASSWORD", "TIDB_DATABASE"
)}
try:
    assert not tidb_store.configured()
finally:
    for name, value in saved.items():
        if value is not None:
            os.environ[name] = value

connection = RecordingConnection()
event_id = tidb_store.persist_event(
    {
        "event_id": "offline-event-1",
        "event_type": "study.started",
        "device_id": "board-1",
        "session_id": "session-1",
        "telemetry": {"present": True},
    },
    connection,
)
assert event_id == "offline-event-1"
assert len(connection.calls) == len(tidb_store.SCHEMA_STATEMENTS) + 1
assert "INSERT INTO project_event" in connection.calls[-1][1]
assert not connection.closed

code_count = tidb_store.upsert_code_snapshots(
    [
        {
            "project_id": "desk-study-companion",
            "git_commit": "a" * 40,
            "path": "firmware/main.py",
            "content_sha256": "b" * 64,
            "size_bytes": 10,
            "language": "Python",
            "github_url": "https://github.com/example/repo/blob/a/firmware/main.py",
            "content": "print(1)\n",
        }
    ],
    connection,
)
assert code_count == 1
assert "project_code_snapshot" in connection.calls[-1][1]

asset_count = tidb_store.upsert_asset_manifests(
    [
        {
            "project_id": "desk-study-companion",
            "git_commit": "a" * 40,
            "path": "firmware/assets/pet.png",
            "content_sha256": "c" * 64,
            "size_bytes": 20,
            "mime_type": "image/png",
            "github_url": "https://github.com/example/repo/blob/a/pet.png",
        }
    ],
    connection,
)
assert asset_count == 1
assert "project_asset_manifest" in connection.calls[-1][1]

print("TiDB store tests: OK")
