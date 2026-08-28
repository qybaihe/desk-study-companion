#!/usr/bin/env python3
"""Low-latency MiMo ASR -> one-pass answer -> streaming TTS pipeline.

This module is isolated from the ESP32 display application.  It only reads an
audio file and writes benchmark/output files below ``voice_qa_mimo``.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import ssl
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from mimo_voice_qa import (
    DEFAULT_ENV,
    PipelineError,
    extract_message,
    load_dotenv,
    request_json,
    require_setting,
    transcribe_audio,
)


ROOT = Path(__file__).resolve().parent
FAST_OUTPUT_DIR = ROOT / "fast_outputs"
MAX_SPOKEN_CHARACTERS = 48


def limit_spoken_answer(text: str, limit: int = MAX_SPOKEN_CHARACTERS) -> str:
    """Keep board playback concise while ending at a natural boundary."""
    normalized = " ".join(str(text).split()).strip()
    if len(normalized) <= limit:
        return normalized
    candidate = normalized[:limit]
    cut = max(candidate.rfind(mark) for mark in "。！？；")
    if cut >= max(12, limit // 2):
        return candidate[: cut + 1]
    return candidate[: limit - 1].rstrip("，,；;：:。.!！?") + "。"


def _parse_fast_answer(text: str) -> dict[str, Any]:
    try:
        answer = json.loads(text)
    except json.JSONDecodeError as error:
        raise PipelineError("快速解题返回的内容不是有效 JSON") from error
    if not isinstance(answer, dict):
        raise PipelineError("快速解题返回的 JSON 不是对象")
    required = {"needs_repeat", "short_answer", "spoken_answer"}
    missing = sorted(required - set(answer))
    if missing:
        raise PipelineError("快速解题缺少字段：%s" % ", ".join(missing))
    if not isinstance(answer["needs_repeat"], bool):
        raise PipelineError("快速解题 needs_repeat 字段类型错误")
    for key in ("short_answer", "spoken_answer"):
        answer[key] = " ".join(str(answer[key]).split()).strip()
    if not answer["spoken_answer"]:
        raise PipelineError("快速解题没有可播报答案")
    answer["spoken_answer"] = limit_spoken_answer(answer["spoken_answer"])
    return answer


def solve_fast(
    transcript: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    system_prompt = (
        "你是书桌学习伴侣里的儿童答疑老师。输入来自中文语音识别。"
        "先在内部核对题意、数字、单位和计算，然后直接给适合儿童听的准确答案。"
        "普通题最多用两句话：第一句先说最终答案，第二句只讲关键解释。"
        "复杂题仍要先算准确，但朗读时只说结论和一个关键步骤。"
        "如果题目信息缺失或明显没有听清，needs_repeat为true，并请孩子简短重说。"
        "只返回JSON对象，严格包含三个字段："
        "needs_repeat（布尔值）、short_answer（简短结论）、"
        "spoken_answer（可直接朗读、无Markdown、控制在20到45个汉字）。"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcript},
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "max_completion_tokens": 768,
        "stream": False,
    }
    started = time.monotonic()
    response = request_json(
        base_url.rstrip("/") + "/chat/completions",
        api_key,
        payload,
        timeout=90,
        attempts=1,
    )
    elapsed_ms = round((time.monotonic() - started) * 1000)
    content, metadata = extract_message(response)
    return _parse_fast_answer(content), metadata, elapsed_ms


def stream_tts_pcm(
    text: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
    voice: str,
    on_chunk: Callable[[bytes], None] | None = None,
) -> tuple[dict[str, Any], int, int]:
    """Stream 24 kHz mono PCM16; return metadata, first-byte ms, total ms."""

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "请用温和、清晰的中文老师语气朗读，数字和单位读清楚。",
            },
            {"role": "assistant", "content": text},
        ],
        "audio": {"format": "pcm16", "voice": voice},
        "stream": True,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": "desk-study-companion-fast/1.0",
        },
        method="POST",
    )
    started = time.monotonic()
    first_audio_ms: int | None = None
    pcm_bytes = 0
    chunks = 0
    response_id = None
    response_model = None
    finish_reason = None
    usage: dict[str, Any] = {}
    with urllib.request.urlopen(
        request, timeout=120, context=ssl.create_default_context()
    ) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            response_id = event.get("id", response_id)
            response_model = event.get("model", response_model)
            if isinstance(event.get("usage"), dict):
                usage = event["usage"]
            choices = event.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            finish_reason = choice.get("finish_reason") or finish_reason
            delta = choice.get("delta") or {}
            audio = delta.get("audio") if isinstance(delta, dict) else None
            if not isinstance(audio, dict) or not audio.get("data"):
                continue
            try:
                chunk = base64.b64decode(audio["data"], validate=True)
            except (ValueError, TypeError) as error:
                raise PipelineError("流式 TTS 返回了无效音频块") from error
            if not chunk:
                continue
            if first_audio_ms is None:
                first_audio_ms = round((time.monotonic() - started) * 1000)
            pcm_bytes += len(chunk)
            chunks += 1
            if on_chunk is not None:
                on_chunk(chunk)
    total_ms = round((time.monotonic() - started) * 1000)
    if first_audio_ms is None or pcm_bytes == 0:
        raise PipelineError("流式 TTS 没有返回音频")
    metadata = {
        "response_id": response_id,
        "model": response_model,
        "finish_reason": finish_reason,
        "usage": usage,
        "pcm_bytes": pcm_bytes,
        "chunks": chunks,
        "sample_rate": 24_000,
        "channels": 1,
        "sample_width": 2,
    }
    return metadata, first_audio_ms, total_ms


def run_fast_pipeline(audio_path: Path, output_dir: Path) -> tuple[dict[str, Any], Path]:
    load_dotenv(DEFAULT_ENV)
    api_key = require_setting("MIMO_API_KEY")
    base_url = os.environ.get(
        "MIMO_BASE_URL", "https://api.xiaomimimo.com/v1"
    ).strip()
    asr_model = os.environ.get("MIMO_ASR_MODEL", "mimo-v2.5-asr").strip()
    solver_model = os.environ.get("MIMO_SOLVER_MODEL", "mimo-v2.5-pro").strip()
    tts_model = os.environ.get("MIMO_TTS_MODEL", "mimo-v2.5-tts").strip()
    voice = os.environ.get("MIMO_TTS_VOICE", "冰糖").strip()

    audio_path = audio_path.expanduser().resolve()
    if not audio_path.is_file():
        raise PipelineError("找不到音频文件：%s" % audio_path)

    overall_started = time.monotonic()
    print("[快速 1/3] 语音识别...", flush=True)
    transcript, asr_meta, asr_ms = transcribe_audio(
        audio_path,
        api_key=api_key,
        base_url=base_url,
        model=asr_model,
    )
    print("识别：%s" % transcript, flush=True)
    print("[快速 2/3] 单次 Agent 解题...", flush=True)
    answer, solver_meta, solver_ms = solve_fast(
        transcript,
        api_key=api_key,
        base_url=base_url,
        model=solver_model,
    )
    print("答案：%s" % answer["short_answer"], flush=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    pcm_path = output_dir / (stamp + "-answer-24k.pcm")
    print("[快速 3/3] 流式生成语音...", flush=True)
    with pcm_path.open("wb") as pcm_file:
        tts_meta, tts_first_ms, tts_total_ms = stream_tts_pcm(
            answer["spoken_answer"],
            api_key=api_key,
            base_url=base_url,
            model=tts_model,
            voice=voice,
            on_chunk=pcm_file.write,
        )
    total_to_first_audio_ms = asr_ms + solver_ms + tts_first_ms
    total_ms = round((time.monotonic() - overall_started) * 1000)
    result = {
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "audio": str(audio_path),
        "transcript": transcript,
        "answer": answer,
        "latency_ms": {
            "asr": asr_ms,
            "solver": solver_ms,
            "tts_first_audio": tts_first_ms,
            "tts_total": tts_total_ms,
            "release_to_first_audio_estimate": total_to_first_audio_ms,
            "total_pipeline": total_ms,
        },
        "models": {
            "asr": asr_model,
            "solver": solver_model,
            "tts": tts_model,
        },
        "api_metadata": {"asr": asr_meta, "solver": solver_meta, "tts": tts_meta},
        "pcm": str(pcm_path.resolve()),
    }
    result_path = output_dir / (stamp + "-fast.json")
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "latest_fast.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result, result_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("--output-dir", type=Path, default=FAST_OUTPUT_DIR)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result, result_path = run_fast_pipeline(args.audio, args.output_dir)
    except Exception as error:
        print("FAST_PIPELINE_ERROR: %s" % error, file=sys.stderr)
        return 1
    print(json.dumps(result["latency_ms"], ensure_ascii=False, indent=2))
    print("结果：%s" % result_path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
