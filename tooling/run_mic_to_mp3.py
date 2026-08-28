#!/usr/bin/env python3
"""Run the isolated IO10 recorder, download WAV, and create an MP3."""

from __future__ import annotations

import base64
import subprocess
import time
from pathlib import Path

import serial

import mprepl


ROOT = Path(__file__).resolve().parents[1]
RECORDINGS = ROOT / "runtime" / "recordings"
WAV_PATH = RECORDINGS / "mic_recording_io10.wav"
MP3_PATH = RECORDINGS / "mic_recording_io10.mp3"
REMOTE_SCRIPT = "/mic_capture_io10.py"
REMOTE_WAV = "/mic_recording_io10.wav"
BAUD = 115200


def open_serial(port_name: str) -> serial.Serial:
    port = serial.Serial()
    port.port = port_name
    port.baudrate = BAUD
    port.timeout = 0.05
    port.write_timeout = 2
    # Keep BOOT and RESET inactive when opening an already running board.
    port.dtr = False
    port.rts = False
    port.open()
    return port


def pulse_normal_reset(port_name: str) -> None:
    port = open_serial(port_name)
    try:
        port.dtr = False
        port.rts = True
        time.sleep(0.15)
        port.rts = False
    finally:
        port.close()


def drain(port: serial.Serial, quiet: float = 0.12) -> bytes:
    result = bytearray()
    deadline = time.monotonic() + quiet
    while time.monotonic() < deadline:
        data = port.read(port.in_waiting or 1)
        if data:
            result.extend(data)
            deadline = time.monotonic() + quiet
    return bytes(result)


def read_until(port: serial.Serial, marker: bytes, timeout: float) -> bytes:
    result = bytearray()
    deadline = time.monotonic() + timeout
    while marker not in result:
        if time.monotonic() >= deadline:
            raise TimeoutError("waiting for %r, received %r" % (marker, bytes(result)))
        data = port.read(port.in_waiting or 1)
        if data:
            result.extend(data)
    return bytes(result)


def reset_and_interrupt(port_name: str) -> serial.Serial:
    port = open_serial(port_name)
    port.dtr = False
    port.rts = True
    time.sleep(0.15)
    port.rts = False

    started = time.monotonic()
    next_interrupt = started + 0.55
    received = bytearray()
    while time.monotonic() - started < 4.0:
        now = time.monotonic()
        try:
            if now >= next_interrupt:
                port.write(b"\x03")
                port.flush()
                next_interrupt += 0.16
            data = port.read(port.in_waiting or 1)
        except serial.SerialException:
            # Some CH340/macOS combinations briefly detach the tty during an
            # ESP reset.  Reopen it and keep sending Ctrl-C inside the same
            # three-second startup grace window.
            try:
                port.close()
            except Exception:
                pass
            time.sleep(0.10)
            port = open_serial(mprepl.detect_port())
            continue
        if data:
            received.extend(data)
            if b">>>" in received:
                return port
    port.close()
    raise RuntimeError("did not reach MicroPython REPL after reset")


def enter_raw(port: serial.Serial) -> None:
    port.write(b"\r\x03\x03")
    port.flush()
    time.sleep(0.12)
    drain(port)
    port.write(b"\r\x01")
    port.flush()
    banner = read_until(port, b">", 5)
    if b"raw REPL" not in banner:
        raise RuntimeError("raw REPL entry failed: %r" % banner)


def send_code(port: serial.Serial, code: str) -> bytes:
    payload = code.encode()
    for position in range(0, len(payload), 256):
        port.write(payload[position:position + 256])
        port.flush()
        time.sleep(0.01)
    port.write(b"\x04")
    port.flush()
    # A CH340 can occasionally lose one byte of the two-byte raw-REPL "OK"
    # acknowledgement.  Wait for the first response, then collect through a
    # short quiet period; program output is still delimited by the two EOTs.
    response = bytearray()
    deadline = time.monotonic() + 3
    last_data = None
    while True:
        if not response and time.monotonic() >= deadline:
            raise TimeoutError("board did not acknowledge raw-REPL code")
        if response and time.monotonic() - last_data >= 0.20:
            break
        data = port.read(port.in_waiting or 1)
        if data:
            response.extend(data)
            last_data = time.monotonic()
    acknowledgement = bytes(response)
    ok_position = acknowledgement[:4].find(b"OK")
    if ok_position >= 0:
        return acknowledgement[ok_position + 2:]
    return acknowledgement


def run_recorder_streaming(port: serial.Serial) -> None:
    enter_raw(port)
    initial = send_code(
        port,
        "exec(open(%r).read(), {'__name__':'__main__'})" % REMOTE_SCRIPT,
    )
    pending = bytearray(initial)
    printable = initial.replace(b"\x04", b"")
    if printable:
        print(printable.decode("utf-8", "replace"), end="", flush=True)
    deadline = time.monotonic() + 1800
    while pending.count(4) < 2:
        if time.monotonic() >= deadline:
            raise TimeoutError("waiting for IO10 recording")
        data = port.read(port.in_waiting or 1)
        if data:
            pending.extend(data)
            printable = data.replace(b"\x04", b"")
            if printable:
                print(printable.decode("utf-8", "replace"), end="", flush=True)

    stdout, remainder = bytes(pending).split(b"\x04", 1)
    stderr, _ = remainder.split(b"\x04", 1)
    if stderr:
        raise RuntimeError(stderr.decode("utf-8", "replace"))


def exec_collect(port: serial.Serial, code: str, timeout: float) -> tuple[str, str]:
    enter_raw(port)
    pending = bytearray(send_code(port, code))
    deadline = time.monotonic() + timeout
    while pending.count(4) < 2:
        if time.monotonic() >= deadline:
            raise TimeoutError("board execution timed out")
        data = port.read(port.in_waiting or 1)
        if data:
            pending.extend(data)
    stdout, remainder = bytes(pending).split(b"\x04", 1)
    stderr, _ = remainder.split(b"\x04", 1)
    return stdout.decode(), stderr.decode()


def download_wav(port: serial.Serial) -> bytes:
    code = (
        "import ubinascii\n"
        "f=open(%r,'rb')\n"
        "print('AUDIO_B64_BEGIN')\n"
        "while True:\n"
        " b=f.read(768)\n"
        " if not b: break\n"
        " print(ubinascii.b2a_base64(b).decode().strip())\n"
        "f.close()\n"
        "print('AUDIO_B64_END')\n"
    ) % REMOTE_WAV
    stdout, stderr = exec_collect(port, code, 240)
    if stderr:
        raise RuntimeError(stderr)
    payload = stdout.split("AUDIO_B64_BEGIN", 1)[1]
    payload = payload.split("AUDIO_B64_END", 1)[0]
    return base64.b64decode("".join(payload.split()))


def convert_mp3() -> None:
    subprocess.run(
        [
            "/opt/homebrew/bin/ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(WAV_PATH),
            "-af", "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", "16000", "-ac", "1", "-codec:a", "libmp3lame",
            "-b:a", "64k", str(MP3_PATH),
        ],
        check=True,
    )


def main() -> None:
    port_name = mprepl.detect_port()

    # First let the unmodified main application repaint both displays normally.
    pulse_normal_reset(port_name)
    time.sleep(8)

    # A second reset is interrupted inside main.py's existing grace window.
    # The displays retain their last normal frame while this isolated test runs.
    port = reset_and_interrupt(port_name)
    try:
        print("RECORDER_PREPARING", flush=True)
        run_recorder_streaming(port)
        print("DOWNLOADING_WAV", flush=True)
        audio = download_wav(port)
        if not audio.startswith(b"RIFF") or audio[8:12] != b"WAVE":
            raise RuntimeError("downloaded data is not a WAV file")
        RECORDINGS.mkdir(exist_ok=True)
        WAV_PATH.write_bytes(audio)
        convert_mp3()
        probe = subprocess.run(
            [
                "/opt/homebrew/bin/ffprobe", "-v", "error",
                "-show_entries", "format=duration,size",
                "-of", "default=noprint_wrappers=1", str(MP3_PATH),
            ],
            check=True, text=True, stdout=subprocess.PIPE,
        )
        print("MP3_READY", MP3_PATH, flush=True)
        print(probe.stdout, end="", flush=True)
    finally:
        port.close()
        pulse_normal_reset(port_name)
        print("MAIN_APP_RESTORED", flush=True)


if __name__ == "__main__":
    main()
