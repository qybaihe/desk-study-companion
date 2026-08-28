#!/usr/bin/env python3
"""Generate the ignored MicroPython Wi-Fi/device-token configuration."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
OUTPUT_DIR = ROOT / "generated"
OUTPUT_PATH = OUTPUT_DIR / "voice_qa_config.py"


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def ensure_device_token(values: dict[str, str]) -> str:
    token = values.get("VOICE_DEVICE_TOKEN", "").strip()
    if token:
        return token
    token = secrets.token_hex(24)
    with ENV_PATH.open("a", encoding="utf-8") as env_file:
        if ENV_PATH.stat().st_size:
            env_file.write("\n")
        env_file.write("VOICE_DEVICE_TOKEN=%s\n" % token)
    os.chmod(ENV_PATH, 0o600)
    values["VOICE_DEVICE_TOKEN"] = token
    return token


def require(values: dict[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise RuntimeError("missing %s in %s" % (key, ENV_PATH))
    return value


def build() -> Path:
    values = read_env(ENV_PATH)
    token = ensure_device_token(values)
    ssid = require(values, "VOICE_WIFI_SSID")
    password = require(values, "VOICE_WIFI_PASSWORD")
    fallback_host = require(values, "VOICE_MAC_HOST")
    fast_port = int(values.get("VOICE_FAST_PORT", "8766"))
    discovery_port = int(values.get("VOICE_DISCOVERY_PORT", "8767"))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        "# Generated from services/voice_ai/.env; do not commit.\n"
        "WIFI_SSID = %r\n"
        "WIFI_PASSWORD = %r\n"
        "FALLBACK_HOST = %r\n"
        "VOICE_PORT = %d\n"
        "DISCOVERY_PORT = %d\n"
        "DEVICE_TOKEN = %r\n"
        % (
            ssid,
            password,
            fallback_host,
            fast_port,
            discovery_port,
            token,
        ),
        encoding="utf-8",
    )
    os.chmod(OUTPUT_PATH, 0o600)
    return OUTPUT_PATH


if __name__ == "__main__":
    output = build()
    print("generated board voice config:", output)
