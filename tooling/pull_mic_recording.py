#!/usr/bin/env python3
"""Download /mic_recording.wav from the attached MicroPython board."""

from __future__ import annotations

import base64
from pathlib import Path

import mprepl


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "runtime" / "recordings"
OUTPUT_PATH = OUTPUT_DIR / "mic_recording.wav"


def main() -> None:
    port = mprepl.Port()
    try:
        code = (
            "import ubinascii\n"
            "f=open('/mic_recording.wav','rb')\n"
            "while True:\n"
            " b=f.read(768)\n"
            " if not b: break\n"
            " print(ubinascii.b2a_base64(b).decode().strip())\n"
            "f.close()\n"
        )
        stdout, stderr = port.exec(code, timeout=180)
    finally:
        port.close()

    if stderr:
        raise RuntimeError(stderr)

    encoded = "".join(stdout.split())
    audio = base64.b64decode(encoded)
    if not audio.startswith(b"RIFF") or audio[8:12] != b"WAVE":
        raise RuntimeError("downloaded data is not a WAV file")

    OUTPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_PATH.write_bytes(audio)
    print(OUTPUT_PATH)
    print("bytes", len(audio))


if __name__ == "__main__":
    main()
