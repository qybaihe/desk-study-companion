#!/usr/bin/env python3
"""LAN server for low-latency ESP32 voice questions.

Protocol (big-endian lengths):
client -> ``VQW1`` + JSON length + JSON header + WAV bytes
server -> ``VA01`` + JSON length + answer JSON + repeated PCM length/data + 0
client -> ``EVT1`` + JSON length + authenticated behaviour-event JSON
server -> ``EV01`` + JSON length + persistence result

MiMo returns 24 kHz mono PCM16LE.  The server downsamples it to 16 kHz before
forwarding so the ESP32's Wi-Fi link has enough headroom for uninterrupted
playback.
"""

from __future__ import annotations

import json
import hmac
import os
import socket
import socketserver
import struct
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fast_voice_pipeline import limit_spoken_answer, solve_fast, stream_tts_pcm
from learning_event_sink import publish_learning_event
from mimo_voice_qa import (
    DEFAULT_ENV,
    PipelineError,
    load_dotenv,
    require_setting,
    transcribe_audio,
)


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "lan_outputs"
MAX_AUDIO_BYTES = 4 * 1024 * 1024
MAX_HEADER_BYTES = 8192
DEFAULT_DISCOVERY_PORT = 8767
OUTPUT_SAMPLE_RATE = 16_000
NETWORK_PCM_FRAME_BYTES = 8_192


class PCM24To16Resampler:
    """Streaming linear 24 kHz -> 16 kHz converter for mono PCM16LE.

    Three 24 kHz samples cover the same time span as two 16 kHz samples.  The
    first output is input sample 0 and the second is linearly interpolated
    halfway between input samples 1 and 2.  Remainders are retained across
    arbitrary MiMo chunk boundaries.
    """

    def __init__(self) -> None:
        self.pending = b""

    def process(self, chunk: bytes) -> bytes:
        if not chunk:
            return b""
        data = self.pending + chunk
        usable = (len(data) // 6) * 6
        if not usable:
            self.pending = data
            return b""

        output = bytearray((usable // 6) * 4)
        output_offset = 0
        for input_offset in range(0, usable, 6):
            first, second, third = struct.unpack_from("<hhh", data, input_offset)
            interpolated = (second + third) // 2
            struct.pack_into(
                "<hh", output, output_offset, first, interpolated
            )
            output_offset += 4
        self.pending = data[usable:]
        return bytes(output)

    def finish(self) -> bytes:
        data = self.pending
        self.pending = b""
        if len(data) % 2:
            raise ValueError("TTS PCM16 数据长度不是偶数")
        if not data:
            return b""
        # One final source sample (or the first of two) is still a valid
        # output point.  At most one 16-bit sample is emitted here.
        return data[:2]


def recv_exact(connection: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = connection.recv(size - len(chunks))
        if not chunk:
            raise ConnectionError("客户端提前断开")
        chunks.extend(chunk)
    return bytes(chunks)


def send_frame(connection: socket.socket, payload: bytes) -> None:
    # One send avoids a tiny length-only TCP packet before every PCM frame.
    connection.sendall(struct.pack(">I", len(payload)) + payload)


def send_header(connection: socket.socket, magic: bytes, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    connection.sendall(magic + struct.pack(">I", len(encoded)) + encoded)


class VoiceRequestHandler(socketserver.BaseRequestHandler):
    def _read_header(self, connection: socket.socket) -> dict[str, Any]:
        header_size = struct.unpack(">I", recv_exact(connection, 4))[0]
        if not 1 <= header_size <= MAX_HEADER_BYTES:
            raise ValueError("请求头长度错误")
        header = json.loads(recv_exact(connection, header_size).decode("utf-8"))
        if not isinstance(header, dict):
            raise ValueError("请求头必须是JSON对象")
        return header

    def _authenticate(self, header: dict[str, Any]) -> str:
        load_dotenv(DEFAULT_ENV)
        expected_token = require_setting("VOICE_DEVICE_TOKEN")
        provided_token = str(header.pop("device_token", ""))
        if not hmac.compare_digest(provided_token, expected_token):
            raise PermissionError("设备认证失败")
        device_id = str(header.get("device_id", "")).strip()
        if not device_id:
            raise ValueError("缺少设备ID")
        return device_id

    def _handle_event(
        self, connection: socket.socket, header: dict[str, Any]
    ) -> None:
        device_id = self._authenticate(header)
        telemetry = header.get("telemetry")
        if not isinstance(telemetry, dict):
            telemetry = {}
        event = {
            "event_id": str(header.get("event_id", "")).strip(),
            "event_type": str(header.get("event_type", "study.telemetry"))[:128],
            "device_id": device_id,
            "session_id": str(header.get("session_id", ""))[:128],
            "source": "esp32.telemetry",
            "client_ip": self.client_address[0],
            "telemetry": telemetry,
        }
        if not event["event_id"]:
            event.pop("event_id")
        delivery = publish_learning_event(event)
        send_header(connection, b"EV01", {"ok": True, "delivery": delivery})
        print(
            "LAN_EVENT client=%s device=%s type=%s"
            % (self.client_address[0], device_id, event["event_type"]),
            flush=True,
        )

    def handle(self) -> None:
        connection: socket.socket = self.request
        connection.settimeout(180)
        try:
            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        request_started = time.monotonic()
        response_started = False
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S-%f")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        wav_path = OUTPUT_DIR / (stamp + "-question.wav")
        pcm_path = OUTPUT_DIR / (stamp + "-answer-16k.pcm")
        result_path = OUTPUT_DIR / (stamp + "-result.json")
        try:
            magic = recv_exact(connection, 4)
            header = self._read_header(connection)
            if magic == b"EVT1":
                self._handle_event(connection, header)
                return
            if magic != b"VQW1":
                raise ValueError("协议标识错误")
            device_id = self._authenticate(header)
            audio_bytes = int(header.get("audio_bytes", 0))
            if not 44 <= audio_bytes <= MAX_AUDIO_BYTES:
                raise ValueError("录音长度不合理")

            upload_started = time.monotonic()
            remaining = audio_bytes
            with wav_path.open("wb") as output:
                while remaining:
                    chunk = connection.recv(min(16_384, remaining))
                    if not chunk:
                        raise ConnectionError("录音上传中断")
                    output.write(chunk)
                    remaining -= len(chunk)
            upload_ms = round((time.monotonic() - upload_started) * 1000)

            api_key = require_setting("MIMO_API_KEY")
            base_url = os.environ.get(
                "MIMO_BASE_URL", "https://api.xiaomimimo.com/v1"
            ).strip()
            asr_model = os.environ.get("MIMO_ASR_MODEL", "mimo-v2.5-asr").strip()
            solver_model = os.environ.get(
                "MIMO_SOLVER_MODEL", "mimo-v2.5-pro"
            ).strip()
            tts_model = os.environ.get("MIMO_TTS_MODEL", "mimo-v2.5-tts").strip()
            voice = os.environ.get("MIMO_TTS_VOICE", "冰糖").strip()

            transcript, asr_meta, asr_ms = transcribe_audio(
                wav_path,
                api_key=api_key,
                base_url=base_url,
                model=asr_model,
            )
            answer, solver_meta, solver_ms = solve_fast(
                transcript,
                api_key=api_key,
                base_url=base_url,
                model=solver_model,
            )
            answer["spoken_answer"] = limit_spoken_answer(
                answer["spoken_answer"]
            )
            response_header = {
                "ok": True,
                "transcript": transcript,
                "short_answer": answer["short_answer"],
                "spoken_answer": answer["spoken_answer"],
                "sample_rate": OUTPUT_SAMPLE_RATE,
                "channels": 1,
                "sample_width": 2,
                "latency_ms": {
                    "upload": upload_ms,
                    "asr": asr_ms,
                    "solver": solver_ms,
                },
            }
            send_header(connection, b"VA01", response_header)
            response_started = True

            first_pcm_at: float | None = None
            pcm_bytes = 0
            pcm_lock = threading.Lock()
            resampler = PCM24To16Resampler()
            with pcm_path.open("wb") as pcm_output:

                def emit_pcm(chunk: bytes) -> None:
                    nonlocal first_pcm_at, pcm_bytes
                    if not chunk:
                        return
                    if first_pcm_at is None:
                        first_pcm_at = time.monotonic()
                    with pcm_lock:
                        pcm_output.write(chunk)
                        for offset in range(0, len(chunk), NETWORK_PCM_FRAME_BYTES):
                            send_frame(
                                connection,
                                chunk[offset : offset + NETWORK_PCM_FRAME_BYTES],
                            )
                    pcm_bytes += len(chunk)

                def forward_pcm(chunk: bytes) -> None:
                    emit_pcm(resampler.process(chunk))

                tts_meta, tts_first_ms, tts_total_ms = stream_tts_pcm(
                    answer["spoken_answer"],
                    api_key=api_key,
                    base_url=base_url,
                    model=tts_model,
                    voice=voice,
                    on_chunk=forward_pcm,
                )
                emit_pcm(resampler.finish())
            tts_meta["source_sample_rate"] = int(
                tts_meta.get("sample_rate", 24_000)
            )
            tts_meta["delivered_sample_rate"] = OUTPUT_SAMPLE_RATE
            tts_meta["delivered_pcm_bytes"] = pcm_bytes
            send_frame(connection, b"")
            total_ms = round((time.monotonic() - request_started) * 1000)
            first_audio_ms = (
                round((first_pcm_at - request_started) * 1000)
                if first_pcm_at is not None
                else None
            )
            release_to_upload_ms = max(
                0, min(120_000, int(header.get("release_to_upload_ms", 0)))
            )
            release_to_first_audio_ms = (
                release_to_upload_ms + first_audio_ms
                if first_audio_ms is not None
                else None
            )
            telemetry = header.get("telemetry")
            if not isinstance(telemetry, dict):
                telemetry = {}
            result = {
                "created_at": datetime.now().astimezone().isoformat(
                    timespec="seconds"
                ),
                "client": self.client_address[0],
                "device_id": device_id,
                "session_id": str(header.get("session_id", "")),
                "question_wav": str(wav_path.resolve()),
                "answer_pcm": str(pcm_path.resolve()),
                "transcript": transcript,
                "answer": answer,
                "latency_ms": {
                    "upload": upload_ms,
                    "asr": asr_ms,
                    "solver": solver_ms,
                    "tts_first": tts_first_ms,
                    "tts_total": tts_total_ms,
                    "connection_to_first_audio": first_audio_ms,
                    "connection_to_complete": total_ms,
                    "release_to_upload": release_to_upload_ms,
                    "release_to_first_audio_estimate": release_to_first_audio_ms,
                },
                "telemetry": telemetry,
                "pcm_bytes": pcm_bytes,
                "api_metadata": {
                    "asr": asr_meta,
                    "solver": solver_meta,
                    "tts": tts_meta,
                },
            }
            learning_event = {
                "event_type": "voice_qa.completed",
                "device_id": device_id,
                "session_id": result["session_id"],
                "question": transcript,
                "short_answer": answer["short_answer"],
                "spoken_answer": answer["spoken_answer"],
                "latency_ms": result["latency_ms"],
                "telemetry": telemetry,
            }
            result["event_delivery"] = publish_learning_event(learning_event)
            result_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (OUTPUT_DIR / "latest_lan.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(
                "LAN_ANSWER client=%s transcript=%r answer=%r first_audio_ms=%s total_ms=%d"
                % (
                    self.client_address[0],
                    transcript,
                    answer["short_answer"],
                    first_audio_ms,
                    total_ms,
                ),
                flush=True,
            )
        except Exception as error:
            if not response_started:
                try:
                    send_header(
                        connection,
                        b"ER01",
                        {"ok": False, "error": "%s" % error},
                    )
                except Exception:
                    pass
            else:
                try:
                    send_frame(connection, b"")
                except Exception:
                    pass
            print(
                "LAN_REQUEST_ERROR client=%s error=%r"
                % (self.client_address[0], error),
                flush=True,
            )


class VoiceServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class DiscoveryResponder(threading.Thread):
    """Answer authenticated UDP broadcasts with the current TCP endpoint."""

    def __init__(self, discovery_port: int, voice_port: int, token: str):
        super().__init__(name="voice-discovery", daemon=True)
        self.discovery_port = discovery_port
        self.voice_port = voice_port
        self.token = token
        self.stop_event = threading.Event()

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        discovery = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        discovery.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        discovery.bind(("0.0.0.0", self.discovery_port))
        discovery.settimeout(0.5)
        print(
            "VOICE_DISCOVERY_READY 0.0.0.0:%d" % self.discovery_port,
            flush=True,
        )
        try:
            while not self.stop_event.is_set():
                try:
                    payload, address = discovery.recvfrom(2048)
                except socket.timeout:
                    continue
                except OSError:
                    continue
                try:
                    request = json.loads(payload.decode("utf-8"))
                    provided = str(request.get("device_token", ""))
                    if request.get("magic") != "VQDISC1" or not hmac.compare_digest(
                        provided, self.token
                    ):
                        continue
                    response = json.dumps(
                        {
                            "magic": "VQDISC1",
                            "device_id": str(request.get("device_id", "")),
                            "port": self.voice_port,
                            "beijing_rtc": list(
                                _beijing_rtc_tuple()
                            ),
                        },
                        separators=(",", ":"),
                    ).encode("utf-8")
                    discovery.sendto(response, address)
                except Exception:
                    continue
        finally:
            discovery.close()


def _beijing_rtc_tuple() -> tuple[int, int, int, int, int, int, int, int]:
    """Return the tuple shape expected by MicroPython machine.RTC."""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return (
        now.year,
        now.month,
        now.day,
        now.weekday(),
        now.hour,
        now.minute,
        now.second,
        0,
    )


def main() -> None:
    load_dotenv(DEFAULT_ENV)
    host = os.environ.get("VOICE_SERVER_BIND", "0.0.0.0").strip()
    port = int(os.environ.get("VOICE_FAST_PORT", "8766"))
    discovery_port = int(
        os.environ.get("VOICE_DISCOVERY_PORT", str(DEFAULT_DISCOVERY_PORT))
    )
    device_token = require_setting("VOICE_DEVICE_TOKEN")
    discovery = DiscoveryResponder(discovery_port, port, device_token)
    discovery.start()
    try:
        with VoiceServer((host, port), VoiceRequestHandler) as server:
            print("VOICE_FAST_SERVER_READY %s:%d" % (host, port), flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    finally:
        discovery.stop()
        discovery.join(timeout=2)


if __name__ == "__main__":
    main()
