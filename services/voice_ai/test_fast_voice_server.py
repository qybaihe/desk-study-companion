#!/usr/bin/env python3
"""Offline checks for answer limiting, authentication and LAN discovery."""

from __future__ import annotations

import json
import os
import socket
import struct
import tempfile
import threading
import time
from pathlib import Path

import learning_event_sink
from fast_voice_pipeline import limit_spoken_answer
from local_fast_voice_server import (
    DiscoveryResponder,
    VoiceRequestHandler,
    VoiceServer,
)
from mimo_voice_qa import DEFAULT_ENV, load_dotenv, require_setting


def free_udp_port() -> int:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()
    return port


def recv_server_header(client: socket.socket) -> tuple[bytes, dict]:
    prefix = client.recv(8)
    assert len(prefix) == 8
    magic = prefix[:4]
    size = struct.unpack(">I", prefix[4:])[0]
    payload = bytearray()
    while len(payload) < size:
        payload.extend(client.recv(size - len(payload)))
    return magic, json.loads(payload.decode("utf-8"))


load_dotenv(DEFAULT_ENV)
token = require_setting("VOICE_DEVICE_TOKEN")

# Spoken answers stay concise and end cleanly.
short = "答案是四。因为二加二等于四。"
assert limit_spoken_answer(short) == short
limited = limit_spoken_answer("这是一个很长的答案，" * 30)
assert len(limited) <= 100 and limited.endswith("。")

# Invalid device tokens are rejected before any WAV/API processing occurs.
server = VoiceServer(("127.0.0.1", 0), VoiceRequestHandler)
server_thread = threading.Thread(target=server.serve_forever, daemon=True)
server_thread.start()
client = socket.create_connection(server.server_address, timeout=2)
bad_header = json.dumps(
    {
        "audio_bytes": 44,
        "device_id": "offline-test",
        "device_token": "not-the-device-token",
    },
    separators=(",", ":"),
).encode("utf-8")
client.sendall(b"VQW1" + struct.pack(">I", len(bad_header)) + bad_header)
magic, payload = recv_server_header(client)
assert magic == b"ER01" and not payload["ok"]
client.close()
server.shutdown()
server.server_close()
server_thread.join(timeout=2)

# UDP discovery ignores unauthenticated probes and answers an authenticated one.
discovery_port = free_udp_port()
discovery = DiscoveryResponder(discovery_port, 8766, token)
discovery.start()
time.sleep(0.1)
probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
probe.settimeout(0.25)
probe.sendto(
    json.dumps(
        {
            "magic": "VQDISC1",
            "device_id": "offline-test",
            "device_token": "invalid",
        }
    ).encode("utf-8"),
    ("127.0.0.1", discovery_port),
)
try:
    probe.recvfrom(512)
    raise AssertionError("unauthenticated discovery request received a reply")
except socket.timeout:
    pass
probe.sendto(
    json.dumps(
        {
            "magic": "VQDISC1",
            "device_id": "offline-test",
            "device_token": token,
        }
    ).encode("utf-8"),
    ("127.0.0.1", discovery_port),
)
response, _ = probe.recvfrom(512)
decoded = json.loads(response.decode("utf-8"))
assert decoded["magic"] == "VQDISC1"
assert decoded["device_id"] == "offline-test"
assert decoded["port"] == 8766
assert len(decoded["beijing_rtc"]) == 8
probe.close()
discovery.stop()
discovery.join(timeout=2)

# Agent Stack integration always has a durable local event fallback.
with tempfile.TemporaryDirectory() as temporary_directory:
    learning_event_sink.SPOOL_DIR = Path(temporary_directory)
    learning_event_sink.SPOOL_PATH = (
        Path(temporary_directory) / "learning_events.jsonl"
    )
    old_url = os.environ.pop("TIDB_AGENT_STACK_URL", None)
    delivery = learning_event_sink.publish_learning_event(
        {"event_type": "voice_qa.completed", "device_id": "offline-test"}
    )
    assert delivery["spooled"] and not delivery["agent_stack_configured"]
    event = json.loads(learning_event_sink.SPOOL_PATH.read_text("utf-8"))
    assert event["event_type"] == "voice_qa.completed"
    if old_url is not None:
        os.environ["TIDB_AGENT_STACK_URL"] = old_url

print("fast voice server tests: OK")
