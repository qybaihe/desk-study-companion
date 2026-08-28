#!/usr/bin/env python3
"""Read the attached board's Python files, CRC them, and compare firmware."""

from __future__ import annotations

import argparse
import base64
import json
import zlib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import deploy
import mprepl


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "docs" / "hardware" / "board-python-manifest.json"
SECRET_FILES = {"voice_qa_config.py"}
CANONICAL_NAMES = {
    "boot.py": "boot.py",
    "main.py": "main.py",
    "audio_manager.py": "audio_manager.py",
    "fusion_tracker.py": "fusion_tracker.py",
    "pet_animation.py": "pet_animation.py",
    "pet_growth.py": "pet_growth.py",
    "presence_tracker.py": "presence_tracker.py",
    "speaker_prompt.py": "speaker_prompt.py",
    "st7789.py": "st7789.py",
    "study_reminder.py": "study_reminder.py",
    "vl53l0x.py": "vl53l0x.py",
    "voice_qa_client.py": "voice_qa_client.py",
}

CANONICAL_PATHS = {
    "mic_button_test.py": "diagnostics/deployed/mic_button_test.py",
    "mic_capture_io10.py": "diagnostics/mic_capture_io10.py",
    "voice_qa_mic_once.py": "diagnostics/voice_qa_mic_once.py",
}


def read_board_file(port: mprepl.Port, name: str) -> bytes:
    stdout, stderr = port.exec(
        "import binascii;print(binascii.b2a_base64("
        "open('/%s','rb').read()).decode())" % name,
        timeout=20,
    )
    if stderr:
        raise RuntimeError(stderr)
    return base64.b64decode("".join(stdout.split()))


def audit(snapshot_dir: Path | None = None) -> dict:
    lock = deploy.acquire_deployment_lock()
    deploy.hard_reset_into_recovery_window()
    port = mprepl.Port()
    entries = []
    try:
        stdout, stderr = port.exec(
            "import os;print('\\n'.join(sorted(n for n in os.listdir('/') "
            "if n.endswith('.py'))))"
        )
        if stderr:
            raise RuntimeError(stderr)
        for name in [line.strip() for line in stdout.splitlines() if line.strip()]:
            data = read_board_file(port, name) if name not in SECRET_FILES else None
            if data is None:
                meta, meta_error = port.exec(
                    "import binascii;d=open('/%s','rb').read();"
                    "print(len(d),binascii.crc32(d)&0xffffffff)" % name
                )
                if meta_error:
                    raise RuntimeError(meta_error)
                size_text, crc_text = meta.strip().split()
                size = int(size_text)
                crc = int(crc_text)
            else:
                size = len(data)
                crc = zlib.crc32(data) & 0xFFFFFFFF

            entry = {
                "path": "/" + name,
                "size": size,
                "crc32": "%08x" % crc,
                "captured": data is not None,
            }
            canonical_name = CANONICAL_NAMES.get(name) or CANONICAL_PATHS.get(name)
            if canonical_name:
                local = (REPO_ROOT / "firmware" / canonical_name).read_bytes()
                entry["canonical"] = "firmware/" + canonical_name
                entry["matches_canonical"] = data == local
            entries.append(entry)
            if data is not None and snapshot_dir is not None:
                snapshot_dir.mkdir(parents=True, exist_ok=True)
                (snapshot_dir / name).write_bytes(data)
    finally:
        port.reset()
        lock.close()

    return {
        "audited_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(
            timespec="seconds"
        ),
        "source": "ESP32-S3 root filesystem",
        "secret_files_excluded": ["/" + name for name in sorted(SECRET_FILES)],
        "files": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--snapshot-dir", type=Path)
    args = parser.parse_args()
    result = audit(args.snapshot_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    mismatches = [
        entry["path"]
        for entry in result["files"]
        if entry.get("matches_canonical") is False
    ]
    print("manifest:", args.output.resolve())
    print("python_files:", len(result["files"]))
    print("canonical_mismatches:", mismatches or "none")


if __name__ == "__main__":
    main()
