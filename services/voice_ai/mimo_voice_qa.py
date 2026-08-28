#!/usr/bin/env python3
"""Isolated MiMo audio-to-text and question-solving pipeline.

This module only reads an existing WAV/MP3 and writes results beneath its own
directory.  It never imports or communicates with the ESP32 display program.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import shutil
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_ENV = ROOT / ".env"
DEFAULT_OUTPUT_DIR = ROOT / "outputs"
SUPPORTED_AUDIO = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
}
MAX_BASE64_BYTES = 10 * 1024 * 1024


class PipelineError(RuntimeError):
    """A user-facing pipeline failure without secret material."""


def load_dotenv(path: Path) -> None:
    """Load a minimal KEY=VALUE env file without third-party dependencies."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def require_setting(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise PipelineError("缺少环境变量 %s" % name)
    return value


def request_json(
    url: str,
    api_key: str,
    payload: dict[str, Any],
    *,
    timeout: float,
    attempts: int = 3,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "desk-study-companion-mimo/1.0",
    }
    retryable_statuses = {408, 409, 429, 500, 502, 503, 504}

    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            url=url,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=timeout, context=ssl.create_default_context()
            ) as response:
                raw = response.read()
            parsed = json.loads(raw.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise PipelineError("MiMo API 返回了非对象 JSON")
            return parsed
        except urllib.error.HTTPError as error:
            response_body = error.read().decode("utf-8", "replace")
            if error.code in retryable_statuses and attempt < attempts:
                time.sleep(2 ** (attempt - 1))
                continue
            try:
                detail = json.loads(response_body)
                detail_text = json.dumps(detail, ensure_ascii=False)
            except json.JSONDecodeError:
                detail_text = response_body[:1000]
            raise PipelineError(
                "MiMo API HTTP %d：%s" % (error.code, detail_text)
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))
                continue
            raise PipelineError("连接 MiMo API 失败：%s" % error) from error
        except json.JSONDecodeError as error:
            raise PipelineError("MiMo API 返回内容不是有效 JSON") from error

    raise PipelineError("MiMo API 请求失败")


def extract_message(response: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    try:
        choice = response["choices"][0]
        message = choice["message"]
        content = message["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise PipelineError("MiMo API 响应缺少 choices[0].message.content") from error

    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        fragments: list[str] = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if isinstance(value, str):
                    fragments.append(value)
        text = "".join(fragments).strip()
    else:
        text = str(content).strip()

    if not text:
        raise PipelineError("MiMo API 返回了空文本")

    metadata = {
        "response_id": response.get("id"),
        "model": response.get("model"),
        "finish_reason": choice.get("finish_reason"),
        "usage": response.get("usage", {}),
    }
    return text, metadata


def audio_to_data_url(audio_path: Path) -> tuple[str, str, int]:
    suffix = audio_path.suffix.lower()
    mime_type = SUPPORTED_AUDIO.get(suffix)
    if mime_type is None:
        guessed, _ = mimetypes.guess_type(audio_path.name)
        raise PipelineError(
            "仅支持 WAV/MP3，当前文件为 %s（%s）"
            % (suffix or "无扩展名", guessed or "未知类型")
        )
    audio_bytes = audio_path.read_bytes()
    encoded = base64.b64encode(audio_bytes).decode("ascii")
    if len(encoded.encode("ascii")) > MAX_BASE64_BYTES:
        raise PipelineError("音频 Base64 编码后超过 MiMo 的 10 MB 上限")
    return "data:%s;base64,%s" % (mime_type, encoded), mime_type, len(audio_bytes)


def transcribe_audio(
    audio_path: Path,
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> tuple[str, dict[str, Any], int]:
    data_url, mime_type, audio_size = audio_to_data_url(audio_path)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": data_url},
                    }
                ],
            }
        ],
        "asr_options": {"language": "zh"},
        "stream": False,
    }
    started = time.monotonic()
    response = request_json(
        base_url.rstrip("/") + "/chat/completions",
        api_key,
        payload,
        timeout=120,
    )
    elapsed_ms = round((time.monotonic() - started) * 1000)
    transcript, metadata = extract_message(response)
    metadata.update({"mime_type": mime_type, "audio_bytes": audio_size})
    return transcript, metadata, elapsed_ms


ANSWER_FORMAT = {
    "recognized_question": "完整复述识别到的问题；不确定时保留原文",
    "question_type": "math|science|language|general|not_a_question|unclear",
    "needs_repeat": False,
    "repeat_reason": None,
    "solution_steps": ["面向孩子的简洁步骤"],
    "short_answer": "一句话最终答案",
    "answer_text": "完整但易懂的答案",
    "spoken_answer": "适合以后直接语音播报的答案，不使用Markdown",
}


def parse_answer_json(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise PipelineError("解题 Agent 返回的内容不是有效 JSON：%s" % text[:500]) from error
    if not isinstance(parsed, dict):
        raise PipelineError("解题 Agent 返回的 JSON 不是对象")

    required = {
        "recognized_question",
        "question_type",
        "needs_repeat",
        "repeat_reason",
        "solution_steps",
        "short_answer",
        "answer_text",
        "spoken_answer",
    }
    missing = sorted(required - set(parsed))
    if missing:
        raise PipelineError("解题 Agent 缺少字段：%s" % ", ".join(missing))
    if not isinstance(parsed["needs_repeat"], bool):
        raise PipelineError("解题 Agent 的 needs_repeat 不是布尔值")
    if not isinstance(parsed["solution_steps"], list):
        raise PipelineError("解题 Agent 的 solution_steps 不是数组")
    return parsed


def make_solver_system_prompt() -> str:
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    return (
        "你是MiMo（中文名称也是MiMo），是小米公司研发的AI智能助手。"
        "今天的日期是%s。\n"
        "你现在是书桌学习伴侣里的儿童答疑Agent。用户输入来自麦克风语音识别。\n"
        "请先判断题目是否完整，再解答。尤其核对所有数字、分数、单位和数量关系。"
        "如果关键信息缺失、互相矛盾或明显没有听清，needs_repeat必须为true，"
        "并用repeat_reason说明需要孩子重说哪一部分；此时不要猜题。\n"
        "对于数学题，要独立复算最终结果，使用适合小学生理解的步骤，保留必要单位。"
        "对于其他问题，也使用准确、简洁、儿童能理解的中文回答。\n"
        "只返回JSON，不要Markdown代码块，不要在JSON外添加任何文字。"
        "JSON字段和类型必须严格如下：%s"
    ) % (today, json.dumps(ANSWER_FORMAT, ensure_ascii=False))


def solve_question(
    transcript: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": make_solver_system_prompt()},
            {
                "role": "user",
                "content": "语音识别原文如下：\n" + transcript,
            },
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "enabled"},
        "max_completion_tokens": 4096,
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
    answer_text, metadata = extract_message(response)
    return parse_answer_json(answer_text), metadata, elapsed_ms


def verify_answer(
    transcript: str,
    draft: dict[str, Any],
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    verifier_prompt = (
        make_solver_system_prompt()
        + "\n你现在是第二遍复核Agent。请根据语音识别原文独立核对草稿，"
        "修正任何题意、计算、单位或表达错误，再返回同一JSON结构。"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": verifier_prompt},
            {
                "role": "user",
                "content": (
                    "语音识别原文：\n%s\n\n第一遍解题草稿：\n%s"
                    % (transcript, json.dumps(draft, ensure_ascii=False))
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "enabled"},
        "max_completion_tokens": 4096,
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
    answer_text, metadata = extract_message(response)
    return parse_answer_json(answer_text), metadata, elapsed_ms


def write_outputs(result: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    request_id = result["request_id"]
    result_path = output_dir / (request_id + ".json")
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copyfile(result_path, output_dir / "latest.json")
    (output_dir / "latest_transcript.txt").write_text(
        result["transcript"] + "\n", encoding="utf-8"
    )
    final_answer = result["answer"]
    answer_lines = [
        "识别题目：" + str(final_answer["recognized_question"]),
        "最终答案：" + str(final_answer["short_answer"]),
        "",
        str(final_answer["answer_text"]),
    ]
    (output_dir / "latest_answer.txt").write_text(
        "\n".join(answer_lines).rstrip() + "\n", encoding="utf-8"
    )
    return result_path


def run_pipeline(audio_path: Path, output_dir: Path) -> tuple[dict[str, Any], Path]:
    load_dotenv(DEFAULT_ENV)
    api_key = require_setting("MIMO_API_KEY")
    base_url = os.environ.get(
        "MIMO_BASE_URL", "https://api.xiaomimimo.com/v1"
    ).strip()
    asr_model = os.environ.get("MIMO_ASR_MODEL", "mimo-v2.5-asr").strip()
    solver_model = os.environ.get(
        "MIMO_SOLVER_MODEL", "mimo-v2.5-pro"
    ).strip()

    audio_path = audio_path.expanduser().resolve()
    if not audio_path.is_file():
        raise PipelineError("找不到音频文件：%s" % audio_path)

    request_id = datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    audio_sha256 = hashlib.sha256(audio_path.read_bytes()).hexdigest()

    print("[1/3] MiMo 语音转文字...", flush=True)
    transcript, asr_meta, asr_ms = transcribe_audio(
        audio_path,
        api_key=api_key,
        base_url=base_url,
        model=asr_model,
    )
    print("识别文字：%s" % transcript, flush=True)

    print("[2/3] MiMo Agent 解题...", flush=True)
    draft, solver_meta, solver_ms = solve_question(
        transcript,
        api_key=api_key,
        base_url=base_url,
        model=solver_model,
    )

    if draft["needs_repeat"]:
        answer = draft
        verifier_meta: dict[str, Any] = {"skipped": True}
        verifier_ms = 0
    else:
        print("[3/3] MiMo Agent 复核答案...", flush=True)
        answer, verifier_meta, verifier_ms = verify_answer(
            transcript,
            draft,
            api_key=api_key,
            base_url=base_url,
            model=solver_model,
        )

    result = {
        "pipeline_version": 1,
        "request_id": request_id,
        "created_at": created_at,
        "status": "NEED_REPEAT" if answer["needs_repeat"] else "SOLVED",
        "audio": {
            "path": str(audio_path),
            "sha256": audio_sha256,
            "bytes": audio_path.stat().st_size,
        },
        "transcript": transcript,
        "answer": answer,
        "models": {"asr": asr_model, "solver": solver_model},
        "latency_ms": {
            "asr": asr_ms,
            "solver": solver_ms,
            "verifier": verifier_ms,
            "total_api": asr_ms + solver_ms + verifier_ms,
        },
        "api_metadata": {
            "asr": asr_meta,
            "solver": solver_meta,
            "verifier": verifier_meta,
        },
    }
    result_path = write_outputs(result, output_dir)
    return result, result_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Use Xiaomi MiMo to transcribe an audio question and solve it."
    )
    parser.add_argument("audio", type=Path, help="WAV or MP3 input file")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="directory for result files",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result, result_path = run_pipeline(args.audio, args.output_dir.resolve())
    except PipelineError as error:
        print("ERROR: %s" % error, file=sys.stderr)
        return 1

    print("状态：%s" % result["status"])
    print("答案：%s" % result["answer"]["short_answer"])
    print("完整结果：%s" % result_path)
    print("文字答案：%s" % (args.output_dir.resolve() / "latest_answer.txt"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
