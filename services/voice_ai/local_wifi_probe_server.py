#!/usr/bin/env python3
"""Tiny LAN-only probe endpoint for the isolated ESP32 voice-QA work.

This file does not communicate with, import, or modify the OLED/LCD program.
It is intentionally standard-library-only so the Wi-Fi path can be checked
before the full audio service is started.
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class ProbeHandler(BaseHTTPRequestHandler):
    server_version = "VoiceQAProbe/1.0"

    def do_GET(self) -> None:  # noqa: N802 - HTTP handler API
        if self.path != "/voice-qa/probe":
            self.send_error(404)
            return
        body = json.dumps(
            {
                "ok": True,
                "service": "voice-qa-mac",
                "server_time_ms": int(time.time() * 1000),
            },
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, message: str, *args: object) -> None:
        print(
            "%s - %s" % (self.client_address[0], message % args),
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ProbeHandler)
    print("VOICE_QA_PROBE_READY %s:%d" % (args.host, args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
