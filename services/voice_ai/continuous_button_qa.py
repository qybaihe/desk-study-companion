#!/usr/bin/env python3
"""Continuously map IO10 press/release events to MiMo question answering.

The existing board /main.py and all OLED/LCD sources remain untouched. This
controller enters the existing MicroPython startup grace window, runs an
isolated microphone script, and restores /main.py when it exits.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[1]
FIRMWARE_ROOT = PROJECT_ROOT / "firmware"
TOOLING_ROOT = PROJECT_ROOT / "tooling"
CAPTURE_DIR = ROOT / "captures"
OUTPUT_DIR = ROOT / "outputs"
BOARD_SOURCE = FIRMWARE_ROOT / "diagnostics" / "mic_capture_io10.py"
REMOTE_SCRIPT = "/voice_qa_mic_once.py"
REMOTE_WAV = "/mic_recording_io10.wav"

# Reuse the verified raw-REPL transport without changing its source.
sys.path.insert(0, str(TOOLING_ROOT))
import mprepl  # noqa: E402
import run_mic_to_mp3 as recorder  # noqa: E402
from mimo_voice_qa import PipelineError, run_pipeline  # noqa: E402


print_lock = threading.Lock()
event_lock = threading.Lock()


def safe_print(*parts: object) -> None:
    with print_lock:
        print(*parts, flush=True)


def find_ffmpeg() -> str:
    preferred = Path("/opt/homebrew/bin/ffmpeg")
    if preferred.is_file():
        return str(preferred)
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    raise RuntimeError("找不到 ffmpeg")


def convert_to_mp3(wav_path: Path, mp3_path: Path) -> None:
    subprocess.run(
        [
            find_ffmpeg(),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(wav_path),
            "-af",
            "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "64k",
            str(mp3_path),
        ],
        check=True,
    )


def upload_isolated_recorder(port: Any) -> None:
    source = BOARD_SOURCE.read_bytes()
    encoded = base64.b64encode(source).decode("ascii")
    code = (
        "import ubinascii\n"
        "d=ubinascii.a2b_base64(%r)\n"
        "f=open(%r,'wb')\n"
        "f.write(d)\n"
        "f.close()\n"
        "compile(open(%r).read(),%r,'exec')\n"
        "print('ISOLATED_RECORDER_READY',len(d))\n"
    ) % (encoded, REMOTE_SCRIPT, REMOTE_SCRIPT, REMOTE_SCRIPT)
    stdout, stderr = recorder.exec_collect(port, code, 30)
    if stderr:
        raise RuntimeError(stderr)
    if "ISOLATED_RECORDER_READY" not in stdout:
        raise RuntimeError("独立录音脚本上传校验失败：%r" % stdout)


def append_event(event: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False) + "\n"
    with event_lock:
        with (OUTPUT_DIR / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(line)


def process_question(sequence: int, wav_path: Path, mp3_path: Path) -> dict[str, Any]:
    try:
        safe_print("[问题 %d] 正在转换 MP3..." % sequence)
        convert_to_mp3(wav_path, mp3_path)
        result, result_path = run_pipeline(mp3_path, OUTPUT_DIR)
        event = {
            "sequence": sequence,
            "status": result["status"],
            "audio_wav": str(wav_path),
            "audio_mp3": str(mp3_path),
            "transcript": result["transcript"],
            "short_answer": result["answer"]["short_answer"],
            "answer_text": result["answer"]["answer_text"],
            "result_path": str(result_path),
            "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        append_event(event)
        safe_print("\n========== 问题 %d 已完成 ==========" % sequence)
        safe_print("识别：", result["transcript"])
        safe_print("答案：", result["answer"]["answer_text"])
        safe_print("结果：", result_path)
        safe_print("====================================\n")
        return event
    except (PipelineError, subprocess.CalledProcessError, OSError) as error:
        event = {
            "sequence": sequence,
            "status": "ERROR",
            "audio_wav": str(wav_path),
            "audio_mp3": str(mp3_path),
            "error": str(error),
            "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        append_event(event)
        safe_print("[问题 %d] 处理失败：%s" % (sequence, error))
        return event


def report_worker_failure(future: Future[dict[str, Any]]) -> None:
    try:
        future.result()
    except Exception as error:
        safe_print("后台处理异常：", repr(error))


def save_downloaded_wav(sequence: int, data: bytes) -> tuple[Path, Path]:
    if not data.startswith(b"RIFF") or data[8:12] != b"WAVE":
        raise RuntimeError("下载内容不是有效 WAV")
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    stem = "%s-q%04d" % (timestamp, sequence)
    wav_path = CAPTURE_DIR / (stem + ".wav")
    mp3_path = CAPTURE_DIR / (stem + ".mp3")
    wav_path.write_bytes(data)
    return wav_path, mp3_path


def connect_and_prepare(port_name: str, initial_repaint: bool) -> Any:
    if initial_repaint:
        # Let the unchanged main application paint its normal screen once.
        recorder.pulse_normal_reset(port_name)
        time.sleep(8)
    port = recorder.reset_and_interrupt(port_name)
    recorder.REMOTE_SCRIPT = REMOTE_SCRIPT
    recorder.REMOTE_WAV = REMOTE_WAV
    upload_isolated_recorder(port)
    return port


def main() -> int:
    port_name = mprepl.detect_port()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mimo-qa")
    port = None
    sequence = 0

    safe_print("正在启动连续 IO10 语音问答服务...")
    try:
        port = connect_and_prepare(port_name, initial_repaint=True)
        safe_print("服务已启动；每次看到 MIC_CAPTURE_READY 后即可长按下拉一。")

        while True:
            sequence += 1
            safe_print("\n[问题 %d] 等待 IO10 长按..." % sequence)
            try:
                recorder.run_recorder_streaming(port)
                safe_print("[问题 %d] 松开完成，正在下载录音..." % sequence)
                wav_data = recorder.download_wav(port)
                wav_path, mp3_path = save_downloaded_wav(sequence, wav_data)
                safe_print("[问题 %d] 录音已保存：%s" % (sequence, wav_path))
                future = executor.submit(
                    process_question, sequence, wav_path, mp3_path
                )
                future.add_done_callback(report_worker_failure)
                safe_print("[问题 %d] 已进入 MiMo 队列，马上重新监听按钮。" % sequence)
            except KeyboardInterrupt:
                raise
            except Exception as error:
                safe_print("[问题 %d] 录音链路异常：%s" % (sequence, error))
                try:
                    port.close()
                except Exception:
                    pass
                time.sleep(1)
                port = connect_and_prepare(port_name, initial_repaint=False)
    except KeyboardInterrupt:
        safe_print("\n正在停止服务并恢复主程序...")
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
        executor.shutdown(wait=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
