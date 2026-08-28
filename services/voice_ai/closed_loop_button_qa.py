#!/usr/bin/env python3
"""IO10 -> microphone -> MiMo ASR/Agent/TTS -> I2S speaker loop.

Only isolated files and temporary board paths prefixed with /voice_qa_ are
used. The board /main.py and all OLED/LCD code remain untouched.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "tooling"))

import mprepl  # noqa: E402
import run_mic_to_mp3 as recorder  # noqa: E402

from continuous_button_qa import (
    CAPTURE_DIR,
    OUTPUT_DIR,
    connect_and_prepare,
    convert_to_mp3,
    safe_print,
    save_downloaded_wav,
)
from mimo_tts import synthesize_wav
from mimo_voice_qa import PipelineError, run_pipeline


TTS_DIR = ROOT / "tts"
REMOTE_PCM = "/voice_qa_answer.pcm"
PLAYBACK_RATE = 16_000
MAX_SPOKEN_CHARACTERS = 260


def prepare_spoken_text(text: str) -> str:
    text = " ".join(str(text).split()).strip()
    if len(text) <= MAX_SPOKEN_CHARACTERS:
        return text
    candidate = text[:MAX_SPOKEN_CHARACTERS]
    cut = max(candidate.rfind(mark) for mark in "。！？；")
    if cut >= 80:
        candidate = candidate[: cut + 1]
    return candidate.rstrip("，,；;：:") + "。"


def convert_tts_wav_to_pcm(wav_path: Path, pcm_path: Path) -> None:
    ffmpeg = "/opt/homebrew/bin/ffmpeg"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(wav_path),
            "-ar",
            str(PLAYBACK_RATE),
            "-ac",
            "1",
            "-acodec",
            "pcm_s16le",
            "-f",
            "s16le",
            str(pcm_path),
        ],
        check=True,
    )
    if pcm_path.stat().st_size < 2:
        raise RuntimeError("TTS PCM 输出为空")


def upload_pcm(port: Any, pcm_path: Path) -> int:
    pcm = pcm_path.read_bytes()
    encoded = base64.b64encode(pcm).decode("ascii")
    code = (
        "import ubinascii\n"
        "d=ubinascii.a2b_base64(%r)\n"
        "f=open(%r,'wb')\n"
        "f.write(d)\n"
        "f.close()\n"
        "print('VOICE_QA_PCM_READY',len(d))\n"
    ) % (encoded, REMOTE_PCM)
    timeout = max(60, len(pcm) // 3000)
    stdout, stderr = recorder.exec_collect(port, code, timeout)
    if stderr:
        raise RuntimeError(stderr)
    if "VOICE_QA_PCM_READY" not in stdout:
        raise RuntimeError("PCM 上传校验失败：%r" % stdout)
    return len(pcm)


def play_uploaded_pcm(port: Any, pcm_bytes: int) -> int:
    duration_ms = (pcm_bytes * 1000) // (PLAYBACK_RATE * 2)
    code = """
import time
from machine import I2S, Pin
audio = I2S(
    0,
    sck=Pin(39),
    ws=Pin(40),
    sd=Pin(38),
    mode=I2S.TX,
    bits=16,
    format=I2S.MONO,
    rate=%d,
    ibuf=65536,
)
source = open(%r, 'rb')
buffer = bytearray(8192)
total = 0
try:
    while True:
        count = source.readinto(buffer)
        if not count:
            break
        view = memoryview(buffer)[:count]
        offset = 0
        while offset < count:
            written = audio.write(view[offset:])
            if written is None:
                written = count - offset
            if written <= 0:
                raise RuntimeError('I2S write made no progress')
            offset += written
        total += count
finally:
    source.close()
time.sleep_ms(2300)
audio.deinit()
print('VOICE_QA_PLAYBACK_DONE', total)
""" % (PLAYBACK_RATE, REMOTE_PCM)
    stdout, stderr = recorder.exec_collect(
        port, code, max(30, duration_ms // 1000 + 20)
    )
    if stderr:
        raise RuntimeError(stderr)
    if "VOICE_QA_PLAYBACK_DONE" not in stdout:
        raise RuntimeError("扬声器播放校验失败：%r" % stdout)
    return duration_ms


def append_closed_loop_event(event: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUTPUT_DIR / "closed_loop_events.jsonl").open(
        "a", encoding="utf-8"
    ) as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")


def run_one_question(port: Any, sequence: int) -> dict[str, Any]:
    safe_print("\n[闭环问题 %d] 等待 IO10 长按..." % sequence)
    recorder.run_recorder_streaming(port)
    safe_print("[闭环问题 %d] 松开完成，正在下载录音..." % sequence)
    wav_data = recorder.download_wav(port)
    wav_path, mp3_path = save_downloaded_wav(sequence, wav_data)
    convert_to_mp3(wav_path, mp3_path)

    result, result_path = run_pipeline(mp3_path, OUTPUT_DIR)
    spoken_text = prepare_spoken_text(result["answer"]["spoken_answer"])
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = wav_path.stem
    tts_wav_path = TTS_DIR / (stem + "-answer.wav")
    tts_pcm_path = TTS_DIR / (stem + "-answer-16k.pcm")

    safe_print("[闭环问题 %d] 正在生成答案语音..." % sequence)
    tts_metadata, tts_ms = synthesize_wav(spoken_text, tts_wav_path)
    convert_tts_wav_to_pcm(tts_wav_path, tts_pcm_path)

    safe_print("[闭环问题 %d] 正在发送到板上扬声器..." % sequence)
    pcm_bytes = upload_pcm(port, tts_pcm_path)
    playback_ms = play_uploaded_pcm(port, pcm_bytes)

    event = {
        "sequence": sequence,
        "status": "SPOKEN",
        "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "audio_question_wav": str(wav_path),
        "audio_question_mp3": str(mp3_path),
        "transcript": result["transcript"],
        "answer_text": result["answer"]["answer_text"],
        "spoken_text": spoken_text,
        "answer_result": str(result_path),
        "tts_wav": str(tts_wav_path),
        "tts_pcm": str(tts_pcm_path),
        "tts_metadata": tts_metadata,
        "tts_latency_ms": tts_ms,
        "playback_ms": playback_ms,
        "pcm_bytes": pcm_bytes,
    }
    append_closed_loop_event(event)
    safe_print("\n========== 闭环问题 %d 完成 ==========" % sequence)
    safe_print("识别：", result["transcript"])
    safe_print("答案：", result["answer"]["answer_text"])
    safe_print("播报：", spoken_text)
    safe_print("扬声器已播放，时长约 %.2f 秒" % (playback_ms / 1000))
    safe_print("========================================\n")
    return event


def main() -> int:
    port_name = mprepl.detect_port()
    port = None
    sequence = 0
    safe_print("正在启动完整语音问答播报闭环...")
    try:
        port = connect_and_prepare(port_name, initial_repaint=True)
        safe_print("闭环已启动；看到 MIC_CAPTURE_READY 后即可长按下拉一提问。")
        while True:
            sequence += 1
            try:
                run_one_question(port, sequence)
            except KeyboardInterrupt:
                raise
            except (PipelineError, subprocess.CalledProcessError, OSError, RuntimeError) as error:
                safe_print("[闭环问题 %d] 处理异常：%s" % (sequence, error))
                append_closed_loop_event(
                    {
                        "sequence": sequence,
                        "status": "ERROR",
                        "error": str(error),
                        "completed_at": datetime.now().astimezone().isoformat(
                            timespec="seconds"
                        ),
                    }
                )
                try:
                    port.close()
                except Exception:
                    pass
                time.sleep(1)
                port = connect_and_prepare(port_name, initial_repaint=False)
    except KeyboardInterrupt:
        safe_print("\n正在停止闭环并恢复主程序...")
    finally:
        if port is not None:
            try:
                port.close()
            except Exception:
                pass
        try:
            recorder.pulse_normal_reset(port_name)
            safe_print("主程序已恢复。")
        except Exception as error:
            safe_print("主程序复位信息：", error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
