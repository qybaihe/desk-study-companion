#!/usr/bin/env python3
"""Direct TiDB Cloud persistence for device events and repository snapshots."""

from __future__ import annotations

import json
import mimetypes
import os
import ssl
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
MIGRATION_PATH = ROOT / "migrations" / "001_project_observability.sql"

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS project_event (
        event_id VARCHAR(128) NOT NULL,
        event_type VARCHAR(128) NOT NULL,
        device_id VARCHAR(128) NOT NULL DEFAULT '',
        session_id VARCHAR(128) NOT NULL DEFAULT '',
        source VARCHAR(64) NOT NULL DEFAULT 'desk-study-companion',
        event_time DATETIME(6) NOT NULL,
        payload JSON NOT NULL,
        created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        PRIMARY KEY (event_id),
        KEY idx_project_event_device_time (device_id, event_time),
        KEY idx_project_event_session_time (session_id, event_time),
        KEY idx_project_event_type_time (event_type, event_time)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_code_snapshot (
        project_id VARCHAR(64) NOT NULL,
        git_commit CHAR(40) NOT NULL,
        path VARCHAR(512) NOT NULL,
        content_sha256 CHAR(64) NOT NULL,
        size_bytes BIGINT UNSIGNED NOT NULL,
        language VARCHAR(64) NOT NULL DEFAULT '',
        github_url TEXT NOT NULL,
        content MEDIUMTEXT NOT NULL,
        captured_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        PRIMARY KEY (project_id, git_commit, path),
        KEY idx_code_snapshot_hash (content_sha256)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_asset_manifest (
        project_id VARCHAR(64) NOT NULL,
        git_commit CHAR(40) NOT NULL,
        path VARCHAR(512) NOT NULL,
        content_sha256 CHAR(64) NOT NULL,
        size_bytes BIGINT UNSIGNED NOT NULL,
        mime_type VARCHAR(128) NOT NULL DEFAULT 'application/octet-stream',
        github_url TEXT NOT NULL,
        captured_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
        PRIMARY KEY (project_id, git_commit, path),
        KEY idx_asset_manifest_hash (content_sha256)
    )
    """,
)


def configured() -> bool:
    """Return whether all required direct-connection settings are present."""
    return all(
        os.environ.get(name, "").strip()
        for name in ("TIDB_HOST", "TIDB_USER", "TIDB_PASSWORD", "TIDB_DATABASE")
    )


def connect():
    if not configured():
        raise RuntimeError("TiDB direct connection is not configured")
    try:
        import pymysql
    except ImportError as error:
        raise RuntimeError("Install PyMySQL from requirements.txt") from error

    ca_path = os.environ.get("TIDB_SSL_CA", "/etc/ssl/cert.pem").strip()
    ssl_options: dict[str, Any] = {
        "check_hostname": True,
        "verify_mode": ssl.CERT_REQUIRED,
    }
    if ca_path:
        ssl_options["ca"] = ca_path
    return pymysql.connect(
        host=os.environ["TIDB_HOST"].strip(),
        port=int(os.environ.get("TIDB_PORT", "4000")),
        user=os.environ["TIDB_USER"].strip(),
        password=os.environ["TIDB_PASSWORD"],
        database=os.environ["TIDB_DATABASE"].strip(),
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=8,
        read_timeout=15,
        write_timeout=15,
        ssl=ssl_options,
    )


def ensure_schema(connection=None) -> None:
    """Create the idempotent project tables."""
    owns_connection = connection is None
    connection = connection or connect()
    try:
        with connection.cursor() as cursor:
            for statement in SCHEMA_STATEMENTS:
                cursor.execute(statement)
    finally:
        if owns_connection:
            connection.close()


def _event_time(event: dict[str, Any]) -> datetime:
    text = str(event.get("event_created_at", "")).strip()
    if text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError:
            pass
    return datetime.now(timezone.utc).replace(tzinfo=None)


def persist_event(event: dict[str, Any], connection=None) -> str:
    """Idempotently store one behaviour event and return its stable ID."""
    event_id = str(event.get("event_id", "")).strip() or str(uuid.uuid4())
    payload = dict(event)
    payload["event_id"] = event_id
    owns_connection = connection is None
    connection = connection or connect()
    try:
        ensure_schema(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO project_event (
                    event_id, event_type, device_id, session_id,
                    source, event_time, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    event_type = VALUES(event_type),
                    device_id = VALUES(device_id),
                    session_id = VALUES(session_id),
                    source = VALUES(source),
                    event_time = VALUES(event_time),
                    payload = VALUES(payload)
                """,
                (
                    event_id,
                    str(event.get("event_type", "unknown"))[:128],
                    str(event.get("device_id", ""))[:128],
                    str(event.get("session_id", ""))[:128],
                    str(event.get("source", "desk-study-companion"))[:64],
                    _event_time(event),
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                ),
            )
    finally:
        if owns_connection:
            connection.close()
    return event_id


def upsert_code_snapshots(rows: Iterable[dict[str, Any]], connection=None) -> int:
    owns_connection = connection is None
    connection = connection or connect()
    materialized = list(rows)
    try:
        ensure_schema(connection)
        if materialized:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO project_code_snapshot (
                        project_id, git_commit, path, content_sha256,
                        size_bytes, language, github_url, content
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        content_sha256 = VALUES(content_sha256),
                        size_bytes = VALUES(size_bytes),
                        language = VALUES(language),
                        github_url = VALUES(github_url),
                        content = VALUES(content),
                        captured_at = CURRENT_TIMESTAMP(6)
                    """,
                    [
                        (
                            row["project_id"], row["git_commit"], row["path"],
                            row["content_sha256"], row["size_bytes"],
                            row["language"], row["github_url"], row["content"],
                        )
                        for row in materialized
                    ],
                )
    finally:
        if owns_connection:
            connection.close()
    return len(materialized)


def upsert_asset_manifests(rows: Iterable[dict[str, Any]], connection=None) -> int:
    owns_connection = connection is None
    connection = connection or connect()
    materialized = list(rows)
    try:
        ensure_schema(connection)
        if materialized:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO project_asset_manifest (
                        project_id, git_commit, path, content_sha256,
                        size_bytes, mime_type, github_url
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        content_sha256 = VALUES(content_sha256),
                        size_bytes = VALUES(size_bytes),
                        mime_type = VALUES(mime_type),
                        github_url = VALUES(github_url),
                        captured_at = CURRENT_TIMESTAMP(6)
                    """,
                    [
                        (
                            row["project_id"], row["git_commit"], row["path"],
                            row["content_sha256"], row["size_bytes"],
                            row.get("mime_type") or mimetypes.guess_type(row["path"])[0]
                            or "application/octet-stream",
                            row["github_url"],
                        )
                        for row in materialized
                    ],
                )
    finally:
        if owns_connection:
            connection.close()
    return len(materialized)
