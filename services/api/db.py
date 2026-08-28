"""TiDB Cloud 连接。凭据只存在服务端 —— ESP32 和 iOS App 都不碰数据库。"""
from __future__ import annotations

import os
import ssl
from contextlib import contextmanager
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

_SSL_CA = os.environ.get("TIDB_SSL_CA", "/etc/ssl/cert.pem")


def configured() -> bool:
    return all(os.environ.get(k, "").strip() for k in ("TIDB_HOST", "TIDB_USER", "TIDB_PASSWORD"))


def connect():
    if not configured():
        raise RuntimeError("缺少 TIDB_HOST / TIDB_USER / TIDB_PASSWORD 环境变量")
    ssl_opts: dict[str, Any] = {"check_hostname": True, "verify_mode": ssl.CERT_REQUIRED}
    if os.path.exists(_SSL_CA):
        ssl_opts["ca"] = _SSL_CA
    return pymysql.connect(
        host=os.environ["TIDB_HOST"].strip(),
        port=int(os.environ.get("TIDB_PORT", "4000")),
        user=os.environ["TIDB_USER"].strip(),
        password=os.environ["TIDB_PASSWORD"],
        database=os.environ.get("TIDB_DATABASE", "study_buddy"),
        ssl=ssl_opts,
        cursorclass=DictCursor,
        autocommit=True,
        charset="utf8mb4",
    )


@contextmanager
def cursor():
    conn = connect()
    try:
        with conn.cursor() as cur:
            yield cur
    finally:
        conn.close()


def ensure_schema() -> None:
    sql = open(os.path.join(os.path.dirname(__file__), "schema.sql"), encoding="utf-8").read()
    with cursor() as cur:
        for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
            cur.execute(stmt)
