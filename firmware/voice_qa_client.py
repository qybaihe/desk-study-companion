"""Cooperative Wi-Fi voice-question state machine for the display main loop."""

import binascii
import gc
import json
import os
import socket
import struct
import time

import network
from machine import unique_id

from voice_qa_config import (
    DEVICE_TOKEN,
    DISCOVERY_PORT,
    FALLBACK_HOST,
    VOICE_PORT,
    WIFI_PASSWORD,
    WIFI_SSID,
)


def _would_block(error):
    try:
        code = error.args[0]
    except Exception:
        return False
    return code in (11, 35, 110, 115, 116, 118, 119, 120, 128)


def _safe_remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _write_wav_header(target, data_size, sample_rate=16_000):
    target.write(b"RIFF")
    target.write(struct.pack("<I", 36 + data_size))
    target.write(b"WAVEfmt ")
    target.write(
        struct.pack(
            "<IHHIIHH",
            16,
            1,
            1,
            sample_rate,
            sample_rate * 2,
            2,
            16,
        )
    )
    target.write(b"data")
    target.write(struct.pack("<I", data_size))


class VoiceQAClient:
    """Yield frequently while recording, uploading, thinking, and playing."""

    IDLE = "IDLE"
    RECORDING = "RECORDING"
    PROCESSING = "PROCESSING"
    UPLOADING = "UPLOADING"
    THINKING = "THINKING"
    PLAYING = "PLAYING"
    ERROR = "ERROR"

    RAW_PATH = "/voice_question.raw32"
    WAV_PATH = "/voice_question.wav"
    STATE_PATH = "/voice_qa_state.txt"

    SAMPLE_RATE = 16_000
    MIN_RECORD_MS = 250
    MAX_RECORD_MS = 20_000
    BUTTON_DEBOUNCE_MS = 40
    PLAYBACK_PREBUFFER_MS = 2_000
    MAX_PLAYBACK_PREBUFFER_BYTES = 131_072

    def __init__(self, audio_manager, button_pin):
        self.audio = audio_manager
        self.button = button_pin
        self.device_id = binascii.hexlify(unique_id()).decode()

        self.state = self.IDLE
        self.state_started_at = time.ticks_ms()
        self.state_changed = True
        self.error = ""
        self.question_count = 0
        self.context = {}

        self.station = network.WLAN(network.STA_IF)
        self.station.active(True)
        self.wifi_connecting = False
        self.wifi_started_at = None
        self.next_wifi_retry_at = time.ticks_ms()
        self.wifi_ip = "0.0.0.0"
        self._reported_wifi_connected = None
        self._reported_wifi_ip = None

        self.server_host = FALLBACK_HOST
        self.server_port = int(VOICE_PORT)
        self.server_discovered = False
        self._pending_beijing_rtc = None
        self.discovery_socket = None
        self.discovery_started_at = None
        self.next_discovery_at = time.ticks_ms()

        self._button_armed = not bool(self.button.value())
        self._pressed_at = None
        self._record_started_at = None
        self._released_at = None
        self._discard_blocks = 0
        self._raw_file = None
        self._sample_count = 0
        self._sample_sum = 0
        self._minimum = 2_147_483_647
        self._maximum = -2_147_483_648

        self._process_source = None
        self._process_target = None
        self._process_input = None
        self._process_output = None
        self._process_mean = 0
        self._process_peak = 1
        self._converted = 0
        self._wav_bytes = 0

        self.connection = None
        self._next_connect_at = None
        self._tx_buffer = None
        self._tx_offset = 0
        self._tx_source = None
        self._tx_prefix_done = False
        self._rx_buffer = bytearray()
        self._rx_magic = None
        self._rx_header_size = None
        self._pcm_frame_size = None
        self._server_finished = False
        self._pcm_prebuffer = bytearray()
        self._playback_started = False
        self._playback_sample_rate = 16_000
        self._playback_prebuffer_bytes = 64_000
        self._last_network_progress_at = None
        self._response = {}
        self._first_audio_at = None
        self._release_to_upload_ms = None
        self._release_to_first_audio_ms = None

        self._set_state(self.IDLE, self.state_started_at)

    @property
    def busy(self):
        return self.state != self.IDLE

    @property
    def capture_priority(self):
        return self.state == self.RECORDING

    @property
    def wants_fast_loop(self):
        return self.busy or bool(self.button.value())

    @property
    def wifi_connected(self):
        return bool(self.station.isconnected())

    def set_context(self, context):
        self.context = dict(context or {})

    def take_beijing_rtc(self):
        value = self._pending_beijing_rtc
        self._pending_beijing_rtc = None
        return value

    def submit_existing_wav(self, path=None, now_ms=None, context=None):
        """Queue an existing WAV for a factory/integration diagnostic.

        Normal operation always records through IO10.  This entry point keeps
        end-to-end Wi-Fi/server/speaker verification independent of a person
        physically holding the button during deployment.
        """
        if self.busy:
            return False
        if now_ms is None:
            now_ms = time.ticks_ms()
        source_path = path or self.WAV_PATH
        try:
            if source_path != self.WAV_PATH:
                source = open(source_path, "rb")
                target = open(self.WAV_PATH, "wb")
                try:
                    while True:
                        chunk = source.read(8_192)
                        if not chunk:
                            break
                        target.write(chunk)
                finally:
                    source.close()
                    target.close()
            self._wav_bytes = os.stat(self.WAV_PATH)[6]
            if self._wav_bytes < 44:
                raise ValueError("diagnostic WAV is too short")
            self._cleanup_transfer()
            if context is not None:
                self.set_context(context)
            self._released_at = now_ms
            self._next_connect_at = now_ms
            self.error = ""
            self._set_state(self.UPLOADING, now_ms)
            return True
        except Exception as exc:
            self._fail(now_ms, exc)
            return False

    def consume_state_change(self):
        changed = self.state_changed
        self.state_changed = False
        return changed

    def _write_state_file(self):
        try:
            safe_error = (self.error or "-").replace("\n", "_")
            with open(self.STATE_PATH, "w") as state_file:
                state_file.write(
                    "state=%s wifi=%d ip=%s server=%s:%d discovered=%d questions=%d "
                    "error=%s release_to_upload_ms=%d "
                    "release_to_first_audio_ms=%d\n"
                    % (
                        self.state,
                        1 if self.wifi_connected else 0,
                        self.wifi_ip,
                        self.server_host,
                        self.server_port,
                        1 if self.server_discovered else 0,
                        self.question_count,
                        safe_error.replace(" ", "_"),
                        self._release_to_upload_ms
                        if self._release_to_upload_ms is not None
                        else -1,
                        self._release_to_first_audio_ms
                        if self._release_to_first_audio_ms is not None
                        else -1,
                    )
                )
            self._reported_wifi_connected = self.wifi_connected
            self._reported_wifi_ip = self.wifi_ip
        except Exception:
            pass

    def _publish_wifi_change(self):
        connected = self.wifi_connected
        if (
            connected != self._reported_wifi_connected
            or self.wifi_ip != self._reported_wifi_ip
        ):
            self._write_state_file()
            self.state_changed = True

    def _set_state(self, state, now_ms, error=None):
        self.state = state
        self.state_started_at = now_ms
        self.state_changed = True
        if error is not None:
            self.error = repr(error)
        self._write_state_file()

    def _update_wifi(self, now_ms):
        if self.station.isconnected():
            self.wifi_connecting = False
            try:
                self.wifi_ip = self.station.ifconfig()[0]
            except Exception:
                self.wifi_ip = "0.0.0.0"
            self._publish_wifi_change()
            return

        self.wifi_ip = "0.0.0.0"
        self._publish_wifi_change()
        if self.wifi_connecting:
            if time.ticks_diff(now_ms, self.wifi_started_at) < 15_000:
                return
            try:
                self.station.disconnect()
            except Exception:
                pass
            self.wifi_connecting = False
            self.next_wifi_retry_at = time.ticks_add(now_ms, 3_000)
            return

        if time.ticks_diff(now_ms, self.next_wifi_retry_at) < 0:
            return
        try:
            if not self.station.active():
                self.station.active(True)
            self.station.connect(WIFI_SSID, WIFI_PASSWORD)
            self.wifi_connecting = True
            self.wifi_started_at = now_ms
        except Exception:
            self.next_wifi_retry_at = time.ticks_add(now_ms, 3_000)

    def _close_discovery(self):
        if self.discovery_socket is not None:
            try:
                self.discovery_socket.close()
            except Exception:
                pass
        self.discovery_socket = None
        self.discovery_started_at = None

    def _start_discovery(self, now_ms):
        self._close_discovery()
        try:
            discovery = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                discovery.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except Exception:
                pass
            discovery.setblocking(False)
            request = json.dumps(
                {
                    "magic": "VQDISC1",
                    "device_id": self.device_id,
                    "device_token": DEVICE_TOKEN,
                }
            ).encode()
            discovery.sendto(request, ("255.255.255.255", int(DISCOVERY_PORT)))
            # Also probe the last-known address.  Some phone hotspots suppress
            # broadcast forwarding even though direct client-to-client UDP is
            # available; broadcast still repairs a changed Mac address.
            try:
                discovery.sendto(
                    request, (FALLBACK_HOST, int(DISCOVERY_PORT))
                )
            except Exception:
                pass
            self.discovery_socket = discovery
            self.discovery_started_at = now_ms
        except Exception:
            self._close_discovery()
            self.next_discovery_at = time.ticks_add(now_ms, 10_000)

    def _update_discovery(self, now_ms):
        if not self.wifi_connected:
            self._close_discovery()
            if self.server_discovered:
                self.server_discovered = False
                self._write_state_file()
                self.state_changed = True
            return
        if self.discovery_socket is None:
            if time.ticks_diff(now_ms, self.next_discovery_at) >= 0:
                self._start_discovery(now_ms)
            return
        try:
            payload, address = self.discovery_socket.recvfrom(512)
            response = json.loads(payload.decode())
            if (
                response.get("magic") == "VQDISC1"
                and response.get("device_id") == self.device_id
            ):
                self.server_host = address[0]
                self.server_port = int(response.get("port", VOICE_PORT))
                self.server_discovered = True
                rtc_value = response.get("beijing_rtc")
                if (
                    isinstance(rtc_value, list)
                    and len(rtc_value) == 8
                    and all(isinstance(value, int) for value in rtc_value)
                ):
                    self._pending_beijing_rtc = tuple(rtc_value)
                self._close_discovery()
                self.next_discovery_at = time.ticks_add(now_ms, 60_000)
                self._write_state_file()
                self.state_changed = True
                return
        except OSError as exc:
            if not _would_block(exc):
                self._close_discovery()
        except Exception:
            self._close_discovery()
        if (
            self.discovery_started_at is not None
            and time.ticks_diff(now_ms, self.discovery_started_at) >= 2_000
        ):
            self._close_discovery()
            self.next_discovery_at = time.ticks_add(now_ms, 10_000)

    def _start_recording(self, now_ms):
        self._cleanup_transfer()
        _safe_remove(self.RAW_PATH)
        _safe_remove(self.WAV_PATH)
        try:
            self._raw_file = open(self.RAW_PATH, "wb")
        except Exception as exc:
            self._fail(now_ms, exc)
            return
        if not self.audio.start_capture(
            sample_rate=self.SAMPLE_RATE,
            bits=32,
            block_size=4_096,
            i2s_buffer_size=32_768,
        ):
            self._fail(now_ms, self.audio.error or "microphone start failed")
            return
        self._record_started_at = now_ms
        self._released_at = None
        self._discard_blocks = 2
        self._sample_count = 0
        self._sample_sum = 0
        self._minimum = 2_147_483_647
        self._maximum = -2_147_483_648
        self.error = ""
        self._set_state(self.RECORDING, now_ms)

    def _consume_microphone_block(self, block, count):
        count -= count % 4
        if count <= 0:
            return
        if self._discard_blocks:
            self._discard_blocks -= 1
            return
        self._raw_file.write(memoryview(block)[:count])
        for position in range(0, count, 4):
            sample = struct.unpack_from("<i", block, position)[0]
            self._sample_count += 1
            self._sample_sum += sample
            if sample < self._minimum:
                self._minimum = sample
            if sample > self._maximum:
                self._maximum = sample

    def _step_recording(self, now_ms):
        completed = self.audio.take_capture_block()
        if completed is not None:
            self._consume_microphone_block(completed[0], completed[1])

        pressed = bool(self.button.value())
        elapsed = time.ticks_diff(now_ms, self._record_started_at)
        should_stop = not pressed or elapsed >= self.MAX_RECORD_MS
        if should_stop:
            # I2S RX deinit while an asynchronous read is outstanding can
            # wedge the ESP32 driver.  The last 64 ms block is allowed to
            # complete, then capture is closed without another rearm.
            if completed is None:
                return
            self._released_at = now_ms
            self._begin_processing(now_ms)
            return
        if completed is not None:
            self.audio.rearm_capture()

    def _begin_processing(self, now_ms):
        self.audio.stop_capture()
        if self._raw_file is not None:
            try:
                self._raw_file.flush()
                self._raw_file.close()
            except Exception:
                pass
            self._raw_file = None
        elapsed = time.ticks_diff(now_ms, self._record_started_at)
        if elapsed < self.MIN_RECORD_MS or self._sample_count < self.SAMPLE_RATE // 5:
            self._fail(now_ms, "recording shorter than 0.25 seconds")
            return
        try:
            self._process_mean = self._sample_sum // self._sample_count
            self._process_peak = max(
                abs(self._minimum - self._process_mean),
                abs(self._maximum - self._process_mean),
                1,
            )
            self._process_source = open(self.RAW_PATH, "rb")
            self._process_target = open(self.WAV_PATH, "wb")
            _write_wav_header(
                self._process_target,
                self._sample_count * 2,
                self.SAMPLE_RATE,
            )
            self._process_input = bytearray(4_096)
            self._process_output = bytearray(2_048)
            self._converted = 0
            self._set_state(self.PROCESSING, now_ms)
        except Exception as exc:
            self._fail(now_ms, exc)

    def _step_processing(self, now_ms):
        try:
            count = self._process_source.readinto(self._process_input)
            if count:
                count -= count % 4
                output_position = 0
                for position in range(0, count, 4):
                    sample = struct.unpack_from("<i", self._process_input, position)[0]
                    value = (
                        (sample - self._process_mean) * 27_000
                    ) // self._process_peak
                    if value > 32_767:
                        value = 32_767
                    elif value < -32_768:
                        value = -32_768
                    struct.pack_into(
                        "<h", self._process_output, output_position, value
                    )
                    output_position += 2
                    self._converted += 1
                self._process_target.write(
                    memoryview(self._process_output)[:output_position]
                )
                return

            self._process_source.close()
            self._process_target.flush()
            self._process_target.close()
            self._process_source = None
            self._process_target = None
            _safe_remove(self.RAW_PATH)
            try:
                os.sync()
            except Exception:
                pass
            self._wav_bytes = os.stat(self.WAV_PATH)[6]
            self._next_connect_at = now_ms
            self._set_state(self.UPLOADING, now_ms)
            gc.collect()
        except Exception as exc:
            self._fail(now_ms, exc)

    def _close_connection(self):
        if self.connection is not None:
            try:
                self.connection.close()
            except Exception:
                pass
        self.connection = None

    def _open_connection(self, now_ms):
        self._close_connection()
        try:
            connection = socket.socket()
            connection.setblocking(False)
            try:
                connection.connect((self.server_host, self.server_port))
            except OSError as exc:
                if not _would_block(exc):
                    raise
            self.connection = connection
            self._release_to_upload_ms = time.ticks_diff(
                now_ms, self._released_at
            )
            header = {
                "audio_bytes": self._wav_bytes,
                "format": "wav",
                "rate": self.SAMPLE_RATE,
                "device_id": self.device_id,
                "device_token": DEVICE_TOKEN,
                "session_id": self.context.get("session_id", ""),
                "release_to_upload_ms": self._release_to_upload_ms,
                "telemetry": self.context,
            }
            encoded = json.dumps(header).encode()
            self._tx_buffer = b"VQW1" + struct.pack(">I", len(encoded)) + encoded
            self._tx_offset = 0
            self._tx_source = None
            self._tx_prefix_done = False
            self._last_network_progress_at = now_ms
            return True
        except Exception:
            self._close_connection()
            self._next_connect_at = time.ticks_add(now_ms, 2_000)
            return False

    def _send_current_buffer(self, now_ms):
        if self._tx_buffer is None:
            return True
        try:
            sent = self.connection.send(
                memoryview(self._tx_buffer)[self._tx_offset :]
            )
        except OSError as exc:
            if _would_block(exc):
                return False
            raise
        if not sent:
            raise RuntimeError("voice upload socket closed")
        self._tx_offset += sent
        self._last_network_progress_at = now_ms
        if self._tx_offset >= len(self._tx_buffer):
            self._tx_buffer = None
            self._tx_offset = 0
            return True
        return False

    def _step_upload(self, now_ms):
        if not self.wifi_connected:
            return
        if self.connection is None:
            if time.ticks_diff(now_ms, self._next_connect_at) < 0:
                return
            self._open_connection(now_ms)
            return
        try:
            if (
                self._last_network_progress_at is not None
                and time.ticks_diff(now_ms, self._last_network_progress_at)
                >= 30_000
            ):
                raise RuntimeError("voice upload connection timeout")
            if self._tx_buffer is not None:
                self._send_current_buffer(now_ms)
                return
            if not self._tx_prefix_done:
                self._tx_prefix_done = True
                self._tx_source = open(self.WAV_PATH, "rb")
            chunk = self._tx_source.read(8_192)
            if chunk:
                self._tx_buffer = chunk
                self._tx_offset = 0
                self._send_current_buffer(now_ms)
                return
            self._tx_source.close()
            self._tx_source = None
            self._rx_buffer = bytearray()
            self._rx_magic = None
            self._rx_header_size = None
            self._pcm_frame_size = None
            self._server_finished = False
            self._pcm_prebuffer = bytearray()
            self._playback_started = False
            self._set_state(self.THINKING, now_ms)
        except Exception as exc:
            self._fail(now_ms, exc)

    def _receive_available(self, now_ms):
        try:
            chunk = self.connection.recv(8_192)
        except OSError as exc:
            if _would_block(exc):
                return False
            raise
        if not chunk:
            raise RuntimeError("voice answer socket closed")
        self._rx_buffer.extend(chunk)
        self._last_network_progress_at = now_ms
        return True

    def _start_buffered_playback(self, now_ms):
        """Move the initial two-second cushion into the I2S DMA buffer."""
        if self._playback_started:
            return
        if not self._pcm_prebuffer:
            raise RuntimeError("voice response contained no PCM")

        buffered = self._pcm_prebuffer
        self._pcm_prebuffer = bytearray()
        if not self.audio.start_stream(self._playback_sample_rate):
            raise RuntimeError(self.audio.error or "speaker start failed")
        self._playback_started = True
        if not self.audio.write_stream(buffered):
            raise RuntimeError(self.audio.error or "speaker stream failed")

        self._first_audio_at = now_ms
        self._release_to_first_audio_ms = time.ticks_diff(
            now_ms, self._released_at
        )
        self._set_state(self.PLAYING, now_ms)

    def _parse_response(self, now_ms):
        while True:
            if self._rx_magic is None:
                if len(self._rx_buffer) < 8:
                    return
                self._rx_magic = bytes(self._rx_buffer[:4])
                self._rx_header_size = struct.unpack(
                    ">I", bytes(self._rx_buffer[4:8])
                )[0]
                # MicroPython bytearray supports slicing but not item
                # deletion, so consume frames by rebinding the remainder.
                self._rx_buffer = self._rx_buffer[8:]
                if self._rx_header_size < 1 or self._rx_header_size > 8_192:
                    raise RuntimeError("voice response header is invalid")

            if self._response == {}:
                if len(self._rx_buffer) < self._rx_header_size:
                    return
                encoded = bytes(self._rx_buffer[: self._rx_header_size])
                self._rx_buffer = self._rx_buffer[self._rx_header_size :]
                self._response = json.loads(encoded.decode())
                if self._rx_magic != b"VA01":
                    raise RuntimeError(
                        self._response.get("error", "voice server rejected request")
                    )
                self._playback_sample_rate = int(
                    self._response.get("sample_rate", 16_000)
                )
                channels = int(self._response.get("channels", 1))
                sample_width = int(self._response.get("sample_width", 2))
                if (
                    self._playback_sample_rate < 8_000
                    or self._playback_sample_rate > 48_000
                    or channels != 1
                    or sample_width != 2
                ):
                    raise RuntimeError("voice PCM format is unsupported")
                target = (
                    self._playback_sample_rate
                    * channels
                    * sample_width
                    * self.PLAYBACK_PREBUFFER_MS
                    // 1_000
                )
                self._playback_prebuffer_bytes = min(
                    target, self.MAX_PLAYBACK_PREBUFFER_BYTES
                )

            if self._pcm_frame_size is None:
                if len(self._rx_buffer) < 4:
                    return
                self._pcm_frame_size = struct.unpack(
                    ">I", bytes(self._rx_buffer[:4])
                )[0]
                self._rx_buffer = self._rx_buffer[4:]
                if self._pcm_frame_size == 0:
                    self._server_finished = True
                    if not self._playback_started:
                        self._start_buffered_playback(now_ms)
                    # At 16 kHz the 64 KB I2S ring can still contain about two
                    # seconds of audio.  Drain for the full cushion instead of
                    # cutting off the final words after the old 1.2 seconds.
                    self.audio.finish_stream(
                        time.ticks_ms(), self.PLAYBACK_PREBUFFER_MS + 300
                    )
                    self._close_connection()
                    return
                if self._pcm_frame_size > 1_048_576:
                    raise RuntimeError("voice PCM frame is too large")

            if len(self._rx_buffer) < self._pcm_frame_size:
                return
            pcm = bytes(self._rx_buffer[: self._pcm_frame_size])
            self._rx_buffer = self._rx_buffer[self._pcm_frame_size :]
            self._pcm_frame_size = None
            if not self._playback_started:
                self._pcm_prebuffer.extend(pcm)
                if len(self._pcm_prebuffer) >= self._playback_prebuffer_bytes:
                    self._start_buffered_playback(now_ms)
            elif not self.audio.write_stream(pcm):
                raise RuntimeError(self.audio.error or "speaker stream failed")

    def _step_receive(self, now_ms):
        if self._server_finished:
            if not self.audio.playing:
                self.question_count += 1
                self._cleanup_transfer(keep_audio=True)
                self._button_armed = not bool(self.button.value())
                self._set_state(self.IDLE, now_ms)
            return
        try:
            self._receive_available(now_ms)
            self._parse_response(now_ms)
            if (
                self._last_network_progress_at is not None
                and time.ticks_diff(now_ms, self._last_network_progress_at)
                >= 180_000
            ):
                raise RuntimeError("voice server timeout")
        except Exception as exc:
            self._fail(now_ms, exc)

    def _cleanup_transfer(self, keep_audio=False):
        if self._raw_file is not None:
            try:
                self._raw_file.close()
            except Exception:
                pass
        self._raw_file = None
        for source in (self._process_source, self._process_target, self._tx_source):
            if source is not None:
                try:
                    source.close()
                except Exception:
                    pass
        self._process_source = None
        self._process_target = None
        self._tx_source = None
        self._close_connection()
        self._tx_buffer = None
        self._rx_buffer = bytearray()
        self._response = {}
        self._rx_magic = None
        self._rx_header_size = None
        self._pcm_frame_size = None
        self._server_finished = False
        self._pcm_prebuffer = bytearray()
        self._playback_started = False
        self._playback_sample_rate = 16_000
        self._playback_prebuffer_bytes = 64_000
        self._first_audio_at = None
        if not keep_audio:
            self.audio.stop()

    def _fail(self, now_ms, error):
        self._cleanup_transfer()
        self.error = repr(error)
        self._button_armed = False
        self._set_state(self.ERROR, now_ms, error)

    def update(self, now_ms):
        self._update_wifi(now_ms)
        self._update_discovery(now_ms)

        if self.state == self.IDLE:
            pressed = bool(self.button.value())
            if not self._button_armed:
                if not pressed:
                    self._button_armed = True
                self._pressed_at = None
                return
            if not pressed:
                self._pressed_at = None
                return
            if self._pressed_at is None:
                self._pressed_at = now_ms
                return
            if time.ticks_diff(now_ms, self._pressed_at) >= self.BUTTON_DEBOUNCE_MS:
                self._pressed_at = None
                self._start_recording(now_ms)
            return

        if self.state == self.RECORDING:
            self._step_recording(now_ms)
        elif self.state == self.PROCESSING:
            self._step_processing(now_ms)
        elif self.state == self.UPLOADING:
            self._step_upload(now_ms)
        elif self.state in (self.THINKING, self.PLAYING):
            self._step_receive(now_ms)
        elif self.state == self.ERROR:
            if (
                time.ticks_diff(now_ms, self.state_started_at) >= 2_000
                and not self.button.value()
            ):
                self.error = ""
                self._button_armed = True
                self._set_state(self.IDLE, now_ms)
