#!/usr/bin/env python3
"""MiMo text-to-speech client for the isolated voice-QA module."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import sys
import time
import wave
from io import BytesIO
from pathlib import Path
from typing import Any

from mimo_voice_qa import (
    DEFAULT_ENV,
    PipelineError,
    load_dotenv,
    request_json,
    require_setting,
)


DEFAULT_STYLE = (
    "请用温和、清晰、有耐心的中文辅导老师语气朗读。"
    "语速稍慢，数字和单位要读清楚，不要加入目标文本之外的内容。"
)


def extract_audio(response: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    try:
        choice = response["choices"][0]
        message = choice["message"]
        audio = message["audio"]
        encoded = audio["data"]
    except (KeyError, IndexError, TypeError) as error:
        raise PipelineError("MiMo TTS 响应缺少 choices[0].message.audio.data") from error
    if not isinstance(encoded, str) or not encoded:
        raise PipelineError("MiMo TTS 返回的音频数据为空")
    try:
        audio_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise PipelineError("MiMo TTS 返回了无效的 Base64 音频") from error
    metadata = {
        "response_id": response.get("id"),
        "model": response.get("model"),
        "finish_reason": choice.get("finish_reason"),
        "usage": response.get("usage", {}),
        "audio_id": audio.get("id") if isinstance(audio, dict) else None,
    }
    return audio_bytes, metadata


def inspect_wav(audio_bytes: bytes) -> dict[str, int]:
    if not audio_bytes.startswith(b"RIFF") or audio_bytes[8:12] != b"WAVE":
        raise PipelineError("MiMo TTS 返回内容不是 WAV")
    try:
        with wave.open(BytesIO(audio_bytes), "rb") as stream:
            channels = stream.getnchannels()
            sample_width = stream.getsampwidth()
            sample_rate = stream.getframerate()
            frames = stream.getnframes()
    except (wave.Error, EOFError) as error:
        raise PipelineError("MiMo TTS WAV 文件结构无效") from error
    duration_ms = round(frames * 1000 / sample_rate) if sample_rate else 0
    return {
        "channels": channels,
        "sample_width": sample_width,
        "sample_rate": sample_rate,
        "frames": frames,
        "duration_ms": duration_ms,
        "bytes": len(audio_bytes),
    }


def synthesize_wav(
    text: str,
    output_path: Path,
    *,
    style: str = DEFAULT_STYLE,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    voice: str | None = None,
) -> tuple[dict[str, Any], int]:
    load_dotenv(DEFAULT_ENV)
    api_key = api_key or require_setting("MIMO_API_KEY")
    base_url = (
        base_url
        or os.environ.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
    ).strip()
    model = (model or os.environ.get("MIMO_TTS_MODEL", "mimo-v2.5-tts")).strip()
    voice = (voice or os.environ.get("MIMO_TTS_VOICE", "冰糖")).strip()
    text = " ".join(text.split()).strip()
    if not text:
        raise PipelineError("TTS 播报文本为空")

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": style},
            {"role": "assistant", "content": text},
        ],
        "audio": {"format": "wav", "voice": voice},
        "stream": False,
    }
    started = time.monotonic()
    response = request_json(
        base_url.rstrip("/") + "/chat/completions",
        api_key,
        payload,
        timeout=240,
    )
    elapsed_ms = round((time.monotonic() - started) * 1000)
    audio_bytes, api_metadata = extract_audio(response)
    wav_metadata = inspect_wav(audio_bytes)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(audio_bytes)
    metadata = {
        "text": text,
        "model": model,
        "voice": voice,
        "latency_ms": elapsed_ms,
        "wav": wav_metadata,
        "api": api_metadata,
        "path": str(output_path.resolve()),
    }
    return metadata, elapsed_ms


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a WAV with MiMo TTS")
    parser.add_argument("text", help="Chinese text to synthesize")
    parser.add_argument("output", type=Path, help="output WAV path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        metadata, _ = synthesize_wav(args.text, args.output.resolve())
    except PipelineError as error:
        print("ERROR: %s" % error, file=sys.stderr)
        return 1
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
