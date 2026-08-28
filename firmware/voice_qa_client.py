"""Cooperative Wi-Fi voice-question state machine for the display main loop."""

import binascii
import gc
import json
import machine
import ntptime
import os
import socket
import struct
import time

import network
from machine import I2S, Pin, unique_id

from mimo_cloud import (
    AudioBase64Body,
    BytesBody,
    HTTPSRequest,
    SSEAudioDecoder,
    extract_message,
    extract_spoken_answer,
)

from voice_qa_config import (
    DEVICE_TOKEN,
    DISCOVERY_PORT,
    FALLBACK_HOST,
    MIMO_API_HOST,
    MIMO_API_KEY,
    MIMO_API_PATH,
    MIMO_API_PORT,
    MIMO_ASR_MODEL,
    MIMO_CA_PATH,
    MIMO_SOLVER_MODEL,
    MIMO_TTS_MODEL,
    MIMO_TTS_VOICE,
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


def _wav_header(data_size, sample_rate=16_000):
    return (
        b"RIFF"
        + struct.pack("<I", 36 + data_size)
        + b"WAVEfmt "
        + struct.pack(
            "<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16
        )
        + b"data"
        + struct.pack("<I", data_size)
    )


def _write_wav_header(target, data_size, sample_rate=16_000):
    target.write(_wav_header(data_size, sample_rate))


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
    MAX_RAW_BYTES = SAMPLE_RATE * 4 * MAX_RECORD_MS // 1_000
    MICROPHONE_I2S_ID = 1
    MICROPHONE_BLOCK_BYTES = 12_800
    MICROPHONE_I2S_BUFFER_BYTES = 32_768
    MICROPHONE_SCK_PIN = 41
    MICROPHONE_WS_PIN = 42
    MICROPHONE_SD_PIN = 2
    PRE_ROLL_MS = 2_000
    PRE_ROLL_BYTES = SAMPLE_RATE * 4 * PRE_ROLL_MS // 1_000
    PROCESS_BLOCK_BYTES = 16_384
    UPLOAD_CHUNK_BYTES = 16_384
    BUTTON_DEBOUNCE_MS = 40
    MAX_RESPONSE_PCM_BYTES = 640_000
    # Two to three MiMo PCM chunks are enough to absorb hotspot jitter while
    # starting playback roughly 0.7 seconds earlier than the old 64 KB gate.
    TTS_PREBUFFER_BYTES = 32_000
    TTS_SAMPLE_RATE = 24_000
    PLAYBACK_FEED_BYTES = 16_384
    PLAYBACK_DRAIN_MS = 2_300
    PLAYBACK_STALL_MS = 10_000
    MAX_CLOUD_RETRIES = 2
    CLOUD_RETRY_DELAY_MS = 450
    SERVER_RESPONSE_TIMEOUT_MS = 45_000
    TELEMETRY_HEARTBEAT_MS = 60_000
    TELEMETRY_RETRY_MS = 10_000
    WIFI_IDLE_POLL_MS = 500
    WIFI_BUSY_POLL_MS = 100
    MOTION_TELEMETRY_MIN_INTERVAL_MS = 5_000

    def __init__(self, audio_manager, button_pin):
        self.audio = audio_manager
        self.button = button_pin
        self.device_id = binascii.hexlify(unique_id()).decode()
        try:
            self._boot_id = binascii.hexlify(os.urandom(4)).decode()
        except Exception:
            self._boot_id = "%08x" % (time.ticks_ms() & 0xFFFFFFFF)

        self.state = self.IDLE
        self.state_started_at = time.ticks_ms()
        self.state_changed = True
        self.error = ""
        self.question_count = 0
        self.context = {}
        self._pending_telemetry_events = []
        self._telemetry_sequence = 0
        self._last_motion_telemetry_at = None
        self._next_telemetry_at = time.ticks_add(self.state_started_at, 5_000)

        self.station = network.WLAN(network.STA_IF)
        self.station.active(True)
        self._configure_wifi_performance()
        self._wifi_connected = bool(self.station.isconnected())
        self._next_wifi_poll_at = self.state_started_at
        self.wifi_connecting = False
        self.wifi_started_at = None
        self.next_wifi_retry_at = time.ticks_ms()
        self.wifi_ip = "0.0.0.0"
        self._reported_wifi_connected = None
        self._reported_wifi_ip = None

        # The voice path talks directly to MiMo over public HTTPS.  These
        # compatibility attributes remain because main.py includes them in
        # its existing diagnostics, but no Mac-side server is required.
        self.server_host = MIMO_API_HOST
        self.server_port = int(MIMO_API_PORT)
        self.server_discovered = True
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
        try:
            # Allocate once during boot.  Button presses must never wait for a
            # 1.28 MB PSRAM allocation before the microphone starts saving.
            self._recording_storage = bytearray(self.MAX_RAW_BYTES)
        except Exception:
            self._recording_storage = None
        self._raw_recording = None
        self._raw_recorded_bytes = 0
        self._sample_count = 0
        self._statistics_count = 0
        self._sample_sum = 0
        self._minimum = 2_147_483_647
        self._maximum = -2_147_483_648
        self._recording_uses_warm_microphone = False

        # I2S1 keeps the microphone warm while the normal application uses
        # I2S0 for speaker prompts.  A circular two-second pre-roll retains
        # speech that starts just before the debounced button edge.
        self._warm_microphone = None
        self._warm_buffers = (
            bytearray(self.MICROPHONE_BLOCK_BYTES),
            bytearray(self.MICROPHONE_BLOCK_BYTES),
        )
        self._warm_active_index = 0
        self._warm_ready_index = -1
        self._warm_ready = False
        self._warm_pending = False
        self._warm_count = 0
        self._pre_roll = bytearray(self.PRE_ROLL_BYTES)
        self._pre_roll_write = 0
        self._pre_roll_count = 0
        self._warm_microphone_error = ""

        self._process_mean = 0
        self._process_peak = 1
        self._process_scale_q20 = 1
        self._process_offset = 0
        self._converted = 0
        self._wav_buffer = None
        self._wav_bytes = 0

        self.connection = None
        self._next_connect_at = None
        self._tx_buffer = None
        self._tx_offset = 0
        self._tx_source = None
        self._tx_audio_offset = 0
        self._tx_prefix_done = False
        self._rx_buffer = bytearray()
        self._rx_magic = None
        self._rx_header_size = None
        self._pcm_frame_size = None
        self._server_finished = False
        self._pcm_prebuffer = bytearray()
        self._playback_buffer = None
        self._playback_offset = 0
        self._playback_feed_finished = False
        self._playback_started = False
        self._playback_sample_rate = 16_000
        self._last_network_progress_at = None
        self._response = {}
        self._first_audio_at = None
        self._release_to_upload_ms = None
        self._release_to_first_audio_ms = None
        self._cloud_phase = ""
        self._cloud_request = None
        self._cloud_transcript = ""
        self._cloud_answer = ""
        self._cloud_tts_decoder = None
        self._cloud_tts_done = False
        self._cloud_retry_count = 0
        self._cloud_retry_at = None
        self._tls_clock_ready = time.localtime()[0] >= 2024
        self._clock_sync_started_at = None
        self._next_clock_sync_at = self.state_started_at

        self._set_state(self.IDLE, self.state_started_at)
        self._start_warm_microphone()

    @property
    def busy(self):
        return self.state != self.IDLE

    @property
    def capture_priority(self):
        # main.py already has an early-continue path for this property.  Use it
        # throughout a question so sensor/display rendering cannot steal tens
        # of seconds from audio conversion, upload, receive, or playback.  A
        # state change is still rendered once, then the existing frame holds.
        return self.state in (
            self.RECORDING,
            self.PROCESSING,
            self.UPLOADING,
            self.THINKING,
            self.PLAYING,
        )

    @property
    def wants_fast_loop(self):
        return self.busy or bool(self.button.value())

    @property
    def wifi_connected(self):
        return self._wifi_connected

    def _configure_wifi_performance(self):
        """Disable ESP32 modem sleep so LAN audio gets predictable airtime."""
        try:
            self.station.config(pm=self.station.PM_NONE)
        except Exception:
            pass

    def set_context(self, context):
        updated = dict(context or {})
        previous = self.context
        if updated and not previous:
            self._queue_telemetry_event("device.snapshot", updated)
        elif previous:
            if bool(updated.get("present")) != bool(previous.get("present")):
                self._queue_telemetry_event(
                    "study.started" if updated.get("present") else "study.ended",
                    updated,
                )
            if bool(updated.get("pir_motion")) and not bool(
                previous.get("pir_motion")
            ):
                self._queue_telemetry_event("sensor.motion", updated)
            if (
                updated.get("session_id")
                and updated.get("session_id") != previous.get("session_id")
                and bool(updated.get("present"))
            ):
                self._queue_telemetry_event("study.session_started", updated)
        if updated.get("water_reminder_triggered"):
            self._queue_telemetry_event("reminder.rest_and_water", updated)
        if updated.get("low_light_triggered"):
            self._queue_telemetry_event("reminder.low_light", updated)
        self.context = updated

    def _queue_telemetry_event(self, event_type, telemetry=None):
        # Direct-cloud voice operation deliberately has no dependency on the
        # former Mac telemetry receiver.
        return

        if event_type == "sensor.motion":
            now_ms = time.ticks_ms()
            if (
                self._last_motion_telemetry_at is not None
                and time.ticks_diff(now_ms, self._last_motion_telemetry_at)
                < self.MOTION_TELEMETRY_MIN_INTERVAL_MS
            ):
                return
            self._last_motion_telemetry_at = now_ms
        if any(
            pending["event_type"] == event_type
            for pending in self._pending_telemetry_events
        ):
            return
        if len(self._pending_telemetry_events) >= 16:
            self._pending_telemetry_events.pop(0)
        self._pending_telemetry_events.append(
            {
                "event_type": event_type,
                "telemetry": dict(telemetry or self.context),
            }
        )

    def _send_telemetry_event(self, now_ms, event_type, telemetry):
        self._telemetry_sequence = (self._telemetry_sequence + 1) & 0xFFFF
        event_clock = str(telemetry.get("beijing_time", ""))
        event_clock = event_clock.replace("-", "").replace(":", "").replace(" ", "T")
        event_id = "%s-%s-%s-%08x-%04x" % (
            self.device_id,
            self._boot_id,
            event_clock or "boot",
            now_ms & 0xFFFFFFFF,
            self._telemetry_sequence,
        )
        header = {
            "event_id": event_id,
            "event_type": event_type,
            "device_id": self.device_id,
            "device_token": DEVICE_TOKEN,
            "session_id": telemetry.get("session_id", ""),
            "telemetry": telemetry,
        }
        encoded = json.dumps(header).encode()
        packet = b"EVT1" + struct.pack(">I", len(encoded)) + encoded
        connection = socket.socket()
        try:
            connection.settimeout(0.75)
            connection.connect((self.server_host, self.server_port))
            offset = 0
            while offset < len(packet):
                sent = connection.send(memoryview(packet)[offset:])
                if not sent:
                    raise RuntimeError("telemetry socket closed")
                offset += sent
        finally:
            try:
                connection.close()
            except Exception:
                pass

    def _update_telemetry(self, now_ms):
        return

        if (
            not self.context
            or not self.wifi_connected
            or bool(self.button.value())
        ):
            return
        pending = bool(self._pending_telemetry_events)
        if not pending and time.ticks_diff(now_ms, self._next_telemetry_at) < 0:
            return
        pending_event = self._pending_telemetry_events[0] if pending else None
        event_type = (
            pending_event["event_type"] if pending_event else "study.heartbeat"
        )
        telemetry = pending_event["telemetry"] if pending_event else self.context
        try:
            self._send_telemetry_event(now_ms, event_type, telemetry)
            if pending:
                self._pending_telemetry_events.pop(0)
            delay = 250 if self._pending_telemetry_events else self.TELEMETRY_HEARTBEAT_MS
            self._next_telemetry_at = time.ticks_add(now_ms, delay)
        except Exception:
            self._next_telemetry_at = time.ticks_add(
                now_ms, self.TELEMETRY_RETRY_MS
            )

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
            source = open(self.WAV_PATH, "rb")
            try:
                self._wav_buffer = bytearray(source.read())
            finally:
                source.close()
            self._wav_bytes = len(self._wav_buffer)
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
            # A Wi-Fi bookkeeping change must not force a full display frame
            # while voice owns the fast path.
            if not self.busy:
                self.state_changed = True

    def _set_state(self, state, now_ms, error=None):
        self.state = state
        self.state_started_at = now_ms
        # Busy voice phases deliberately hold the existing OLED/LCD frame.
        # main.py therefore takes its already-existing early-continue branch
        # immediately instead of spending seconds rendering a voice title.
        self.state_changed = state in (self.IDLE, self.ERROR)
        if error is not None:
            self.error = repr(error)
        self._write_state_file()

    def _update_wifi(self, now_ms):
        if time.ticks_diff(now_ms, self._next_wifi_poll_at) < 0:
            return
        self._next_wifi_poll_at = time.ticks_add(
            now_ms,
            self.WIFI_BUSY_POLL_MS if self.busy else self.WIFI_IDLE_POLL_MS,
        )
        connected = bool(self.station.isconnected())
        self._wifi_connected = connected
        if connected:
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
                self._configure_wifi_performance()
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

    def _warm_microphone_callback(self, _):
        # Keep the IRQ allocation-free; the cooperative loop copies the block
        # and explicitly rearms I2S1.
        if self._warm_microphone is None:
            return
        self._warm_count = self.MICROPHONE_BLOCK_BYTES
        self._warm_ready_index = self._warm_active_index
        self._warm_ready = True
        self._warm_pending = False

    def _rearm_warm_microphone(self):
        if (
            self._warm_microphone is None
            or self._warm_ready
            or self._warm_pending
        ):
            return False
        try:
            self._warm_count = 0
            self._warm_microphone.readinto(
                self._warm_buffers[self._warm_active_index]
            )
            self._warm_pending = True
            return True
        except Exception as exc:
            self._warm_microphone_error = repr(exc)
            self._stop_warm_microphone(force=True)
            return False

    def _start_warm_microphone(self):
        if self._warm_microphone is not None or self.state != self.IDLE:
            return self._warm_microphone is not None
        try:
            microphone = I2S(
                self.MICROPHONE_I2S_ID,
                sck=Pin(self.MICROPHONE_SCK_PIN),
                ws=Pin(self.MICROPHONE_WS_PIN),
                sd=Pin(self.MICROPHONE_SD_PIN),
                mode=I2S.RX,
                bits=32,
                format=I2S.MONO,
                rate=self.SAMPLE_RATE,
                ibuf=self.MICROPHONE_I2S_BUFFER_BYTES,
            )
            self._warm_microphone = microphone
            self._warm_ready = False
            self._warm_pending = False
            self._warm_count = 0
            self._warm_active_index = 0
            self._warm_ready_index = -1
            self._warm_microphone_error = ""
            microphone.irq(self._warm_microphone_callback)
            self._rearm_warm_microphone()
            return True
        except Exception as exc:
            self._warm_microphone_error = repr(exc)
            self._stop_warm_microphone(force=True)
            return False

    def _take_warm_microphone_block(self, rearm=True):
        if self._warm_microphone is None or not self._warm_ready:
            return None
        ready_index = self._warm_ready_index
        self._warm_ready = False
        self._warm_ready_index = -1
        completed = self._warm_buffers[ready_index], self._warm_count
        if rearm:
            # Queue DMA into the other buffer before Python analyses the block.
            # This removes the speech gaps caused by one-buffer processing.
            self._warm_active_index = 1 - ready_index
            self._rearm_warm_microphone()
        return completed

    def _stop_warm_microphone(self, force=False):
        if self._warm_microphone is None:
            return True
        if self._warm_pending and not force:
            return False
        microphone = self._warm_microphone
        self._warm_microphone = None
        self._warm_ready = False
        self._warm_pending = False
        self._warm_count = 0
        self._warm_ready_index = -1
        try:
            microphone.irq(None)
        except Exception:
            pass
        try:
            microphone.deinit()
        except Exception:
            pass
        return True

    def _service_idle_microphone(self):
        if self._warm_microphone is None:
            self._start_warm_microphone()
            return
        completed = self._take_warm_microphone_block(rearm=True)
        if completed is None:
            return
        block, count = completed
        count -= count % 4
        if count > 0:
            count = min(count, len(self._pre_roll))
            write_at = self._pre_roll_write
            first = min(count, len(self._pre_roll) - write_at)
            self._pre_roll[write_at : write_at + first] = memoryview(block)[:first]
            remaining = count - first
            if remaining:
                self._pre_roll[:remaining] = memoryview(block)[first:count]
            self._pre_roll_write = (write_at + count) % len(self._pre_roll)
            self._pre_roll_count = min(
                len(self._pre_roll), self._pre_roll_count + count
            )

    def _consume_pre_roll(self):
        """Copy the circular idle history into the recording chronologically."""
        count = self._pre_roll_count
        if count <= 0:
            return
        start = (self._pre_roll_write - count) % len(self._pre_roll)
        first = min(count, len(self._pre_roll) - start)
        self._consume_microphone_block(
            memoryview(self._pre_roll)[start : start + first], first
        )
        remaining = count - first
        if remaining:
            self._consume_microphone_block(
                memoryview(self._pre_roll)[:remaining], remaining
            )
        self._pre_roll_count = 0

    def _start_recording(self, now_ms):
        self._cleanup_transfer()
        _safe_remove(self.RAW_PATH)
        _safe_remove(self.WAV_PATH)
        try:
            if self._recording_storage is None:
                gc.collect()
                self._recording_storage = bytearray(self.MAX_RAW_BYTES)
            self._raw_recording = self._recording_storage
            self._raw_recorded_bytes = 0
        except Exception as exc:
            self._fail(now_ms, exc)
            return
        self._recording_uses_warm_microphone = self._warm_microphone is not None
        if not self._recording_uses_warm_microphone:
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
        self._discard_blocks = 0 if self._recording_uses_warm_microphone else 1
        self._sample_count = 0
        self._statistics_count = 0
        self._sample_sum = 0
        self._minimum = 2_147_483_647
        self._maximum = -2_147_483_648
        if self._recording_uses_warm_microphone and self._pre_roll_count:
            self._consume_pre_roll()
        self._release_to_upload_ms = None
        self._release_to_first_audio_ms = None
        self.error = ""
        self._set_state(self.RECORDING, now_ms)

    def _consume_microphone_block(self, block, count):
        count -= count % 4
        if count <= 0:
            return
        if self._discard_blocks:
            self._discard_blocks -= 1
            return
        remaining = len(self._raw_recording) - self._raw_recorded_bytes
        count = min(count, remaining)
        count -= count % 4
        if count <= 0:
            return
        start = self._raw_recorded_bytes
        end = start + count
        self._raw_recording[start:end] = memoryview(block)[:count]
        self._raw_recorded_bytes = end
        self._sample_count += count // 4
        # One out of every four samples is enough to estimate DC offset and
        # peak gain, while leaving most CPU time available to keep DMA armed.
        for position in range(0, count, 16):
            sample = struct.unpack_from("<i", block, position)[0]
            self._statistics_count += 1
            self._sample_sum += sample
            if sample < self._minimum:
                self._minimum = sample
            if sample > self._maximum:
                self._maximum = sample

    def _step_recording(self, now_ms):
        pressed = bool(self.button.value())
        elapsed = time.ticks_diff(now_ms, self._record_started_at)
        if (not pressed or elapsed >= self.MAX_RECORD_MS) and self._released_at is None:
            self._released_at = now_ms
        should_stop = self._released_at is not None
        if self._recording_uses_warm_microphone:
            completed = self._take_warm_microphone_block(rearm=not should_stop)
        else:
            completed = self.audio.take_capture_block()
        if completed is not None:
            self._consume_microphone_block(completed[0], completed[1])

        if should_stop:
            # Let the in-flight DMA block complete before deinit.  With the
            # warm microphone this also preserves the final syllable.
            if completed is None:
                return
            if self._recording_uses_warm_microphone:
                if not self._stop_warm_microphone():
                    return
            self._begin_processing(now_ms)
            return
        if completed is not None:
            if self._recording_uses_warm_microphone:
                self._rearm_warm_microphone()
            else:
                self.audio.rearm_capture()

    def _begin_processing(self, now_ms):
        if not self._recording_uses_warm_microphone:
            self.audio.stop_capture()
        elapsed = time.ticks_diff(now_ms, self._record_started_at)
        if elapsed < self.MIN_RECORD_MS or self._sample_count < self.SAMPLE_RATE // 5:
            self._fail(now_ms, "recording shorter than 0.25 seconds")
            return
        try:
            self._process_mean = self._sample_sum // max(
                self._statistics_count, 1
            )
            self._process_peak = max(
                abs(self._minimum - self._process_mean),
                abs(self._maximum - self._process_mean),
                1,
            )
            # One division per recording, then only multiply/shift per sample.
            # The former flash converter divided every sample and was the main
            # source of the long pause after button release.
            self._process_scale_q20 = (27_000 << 20) // self._process_peak
            data_size = self._sample_count * 2
            self._wav_buffer = bytearray(44 + data_size)
            self._wav_buffer[:44] = _wav_header(data_size, self.SAMPLE_RATE)
            self._process_offset = 0
            self._converted = 0
            self._set_state(self.PROCESSING, now_ms)
        except Exception as exc:
            self._fail(now_ms, exc)

    def _step_processing(self, now_ms):
        try:
            start = self._process_offset
            end = min(start + self.PROCESS_BLOCK_BYTES, self._raw_recorded_bytes)
            end -= (end - start) % 4
            if end > start:
                output_position = 44 + self._converted * 2
                for position in range(start, end, 4):
                    sample = struct.unpack_from(
                        "<i", self._raw_recording, position
                    )[0]
                    value = (
                        (sample - self._process_mean) * self._process_scale_q20
                    ) >> 20
                    if value > 32_767:
                        value = 32_767
                    elif value < -32_768:
                        value = -32_768
                    struct.pack_into("<h", self._wav_buffer, output_position, value)
                    output_position += 2
                    self._converted += 1
                self._process_offset = end
                return

            self._wav_bytes = len(self._wav_buffer)
            self._raw_recording = None
            self._raw_recorded_bytes = 0
            self._next_connect_at = now_ms
            self._set_state(self.UPLOADING, now_ms)
            gc.collect()
        except Exception as exc:
            self._fail(now_ms, exc)

    def _close_connection(self):
        if self._cloud_request is not None:
            try:
                self._cloud_request.close()
            except Exception:
                pass
        self._cloud_request = None
        if self.connection is not None:
            try:
                self.connection.close()
            except Exception:
                pass
        self.connection = None

    def _make_cloud_request(
        self,
        body_source,
        *,
        accept="application/json",
        on_body=None,
        response_limit=65_536,
        timeout_ms=90_000,
    ):
        self._close_connection()
        self._cloud_request = HTTPSRequest(
            MIMO_API_HOST,
            MIMO_API_PORT,
            MIMO_API_PATH,
            MIMO_API_KEY,
            body_source,
            accept=accept,
            on_body=on_body,
            response_limit=response_limit,
            timeout_ms=timeout_ms,
            ca_path=MIMO_CA_PATH,
        )

    def _reset_cloud_retry(self):
        self._cloud_retry_count = 0
        self._cloud_retry_at = None

    def _schedule_cloud_retry(self, now_ms, error):
        transient = isinstance(error, OSError)
        if not transient:
            detail = str(error).lower()
            transient = (
                "timed out" in detail
                or "closed before" in detail
                or "closed during" in detail
                or "send made no progress" in detail
            )
        if (
            not transient
            or self._cloud_retry_count >= self.MAX_CLOUD_RETRIES
            or (self._cloud_phase == "TTS" and self._playback_started)
        ):
            return False
        self._close_connection()
        self._cloud_retry_count += 1
        self._cloud_retry_at = time.ticks_add(
            now_ms,
            self.CLOUD_RETRY_DELAY_MS * self._cloud_retry_count,
        )
        return True

    def _cloud_retry_ready(self, now_ms):
        if self._cloud_retry_at is None:
            return True
        if time.ticks_diff(now_ms, self._cloud_retry_at) < 0:
            return False
        self._cloud_retry_at = None
        return True

    def _ensure_tls_clock(self, now_ms):
        """Give certificate validation a real clock without a Mac host."""
        if self._tls_clock_ready or time.localtime()[0] >= 2024:
            self._tls_clock_ready = True
            self._clock_sync_started_at = None
            return True
        if time.ticks_diff(now_ms, self._next_clock_sync_at) < 0:
            return False
        if self._clock_sync_started_at is None:
            self._clock_sync_started_at = now_ms
        try:
            # ntptime sets UTC.  The existing application stores Beijing local
            # time in RTC for its clock display, so mirror that convention.
            ntptime.settime()
            shifted = time.localtime(time.time() + 8 * 3600)
            machine.RTC().datetime(
                (
                    shifted[0], shifted[1], shifted[2], shifted[6],
                    shifted[3], shifted[4], shifted[5], 0,
                )
            )
            self._tls_clock_ready = True
            self._clock_sync_started_at = None
            return True
        except Exception:
            if time.ticks_diff(now_ms, self._clock_sync_started_at) >= 20_000:
                raise RuntimeError("internet clock sync failed")
            self._next_clock_sync_at = time.ticks_add(now_ms, 1_500)
            return False

    def _start_asr_request(self, now_ms):
        if self._wav_buffer is None:
            source = open(self.WAV_PATH, "rb")
            try:
                self._wav_buffer = bytearray(source.read())
            finally:
                source.close()
        self._wav_bytes = len(self._wav_buffer)
        marker = "__ESP32_AUDIO_BASE64__"
        payload = {
            "model": MIMO_ASR_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": "data:audio/wav;base64," + marker,
                            },
                        }
                    ],
                }
            ],
            "asr_options": {"language": "zh"},
            "stream": False,
        }
        encoded = json.dumps(payload).encode()
        marker_bytes = marker.encode()
        marker_at = encoded.find(marker_bytes)
        if marker_at < 0:
            raise RuntimeError("ASR audio marker is missing")
        body = AudioBase64Body(
            self._wav_buffer,
            encoded[:marker_at],
            encoded[marker_at + len(marker_bytes) :],
        )
        self._make_cloud_request(
            body,
            response_limit=32_768,
            timeout_ms=25_000,
        )
        self._cloud_phase = "ASR"
        if self._release_to_upload_ms is None:
            self._release_to_upload_ms = time.ticks_diff(
                now_ms, self._released_at
            )
        self._write_state_file()

    def _start_solver_request(self, now_ms):
        instruction = (
            "你是儿童答疑老师。先在内部核对题意、数字、单位和计算，"
            "再用一到两句适合直接朗读的中文回答：先说结论，再说关键一步。"
            "不要Markdown。没听清就请孩子重说，不要猜。"
            "若要求背诵一首短古诗，请给出完整正文。\n孩子的问题："
        )
        payload = {
            "model": MIMO_SOLVER_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": instruction + self._cloud_transcript,
                },
            ],
            "thinking": {"type": "disabled"},
            "max_completion_tokens": 96,
            "stream": False,
        }
        self._make_cloud_request(
            BytesBody(json.dumps(payload).encode()),
            response_limit=32_768,
            timeout_ms=30_000,
        )
        self._cloud_phase = "SOLVER"
        self._set_state(self.THINKING, now_ms)

    def _on_cloud_audio(self, pcm):
        if len(self._playback_buffer) + len(pcm) > self.MAX_RESPONSE_PCM_BYTES:
            raise RuntimeError("MiMo TTS answer exceeds playback buffer")
        self._playback_buffer.extend(pcm)

    def _start_tts_request(self, now_ms):
        payload = {
            "model": MIMO_TTS_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": "请用温和、清晰的中文老师语气朗读，数字和单位读清楚。",
                },
                {"role": "assistant", "content": self._cloud_answer},
            ],
            "audio": {"format": "pcm16", "voice": MIMO_TTS_VOICE},
            "stream": True,
        }
        self._playback_buffer = bytearray()
        self._playback_offset = 0
        self._playback_feed_finished = False
        self._playback_started = False
        self._playback_sample_rate = self.TTS_SAMPLE_RATE
        self._cloud_tts_done = False
        self._cloud_tts_decoder = SSEAudioDecoder(
            self._on_cloud_audio,
            self.MAX_RESPONSE_PCM_BYTES,
        )
        self._make_cloud_request(
            BytesBody(json.dumps(payload).encode()),
            accept="text/event-stream",
            on_body=self._cloud_tts_decoder.feed,
            response_limit=16_384,
            timeout_ms=35_000,
        )
        self._cloud_phase = "TTS"
        self._set_state(self.THINKING, now_ms)

    def _finish_cloud_request(self):
        request = self._cloud_request
        if request is None:
            raise RuntimeError("MiMo cloud request is missing")
        request.ensure_success()
        body = bytes(request.response.body)
        request.close()
        self._cloud_request = None
        return body

    def _step_upload(self, now_ms):
        if not self.wifi_connected:
            return
        try:
            if not self._ensure_tls_clock(now_ms):
                return
            if not self._cloud_retry_ready(now_ms):
                return
            if not self._cloud_phase:
                self._reset_cloud_retry()
                self._start_asr_request(now_ms)
                return
            if self._cloud_phase != "ASR":
                raise RuntimeError("unexpected MiMo upload phase")
            if self._cloud_request is None:
                self._start_asr_request(now_ms)
                return
            if not self._cloud_request.step(now_ms):
                return
            body = self._finish_cloud_request()
            self._cloud_transcript = extract_message(body)
            self._wav_buffer = None
            gc.collect()
            self._reset_cloud_retry()
            self._start_solver_request(now_ms)
        except Exception as exc:
            if not self._schedule_cloud_retry(now_ms, exc):
                self._fail(now_ms, exc)

    def _start_cloud_playback(self, now_ms):
        if self._playback_started:
            return
        if not self._playback_buffer:
            raise RuntimeError("MiMo TTS returned no audio")
        if not self.audio.start_stream(self._playback_sample_rate):
            raise RuntimeError(self.audio.error or "speaker start failed")
        self._playback_started = True
        self._playback_offset = 0
        self._playback_feed_finished = False
        self._set_state(self.PLAYING, now_ms)

    def _pump_cloud_playback(self, now_ms):
        if not self._playback_started or self._playback_feed_finished:
            return
        available = len(self._playback_buffer) - self._playback_offset
        if available > 0:
            if available < self.PLAYBACK_FEED_BYTES and not self._cloud_tts_done:
                return
            end = min(
                self._playback_offset + self.PLAYBACK_FEED_BYTES,
                len(self._playback_buffer),
            )
            chunk = memoryview(self._playback_buffer)[self._playback_offset : end]
            if not self.audio.write_stream(chunk):
                raise RuntimeError(self.audio.error or "speaker stream failed")
            self._playback_offset = end
            if self._first_audio_at is None:
                self._first_audio_at = now_ms
                self._release_to_first_audio_ms = time.ticks_diff(
                    now_ms, self._released_at
                )
                self._write_state_file()
            return
        if self._cloud_tts_done:
            self._playback_feed_finished = True
            self.audio.finish_stream(time.ticks_ms(), self.PLAYBACK_DRAIN_MS)

    def _complete_cloud_question(self, now_ms):
        self.question_count += 1
        self._cleanup_transfer(keep_audio=True)
        self._button_armed = not bool(self.button.value())
        self._set_state(self.IDLE, now_ms)

    def _step_receive(self, now_ms):
        try:
            if not self._cloud_retry_ready(now_ms):
                return
            if self._cloud_phase == "SOLVER":
                if self._cloud_request is None:
                    self._start_solver_request(now_ms)
                    return
                if not self._cloud_request.step(now_ms):
                    return
                body = self._finish_cloud_request()
                content = extract_message(body)
                self._cloud_answer = extract_spoken_answer(content)
                self._reset_cloud_retry()
                self._start_tts_request(now_ms)
                return

            if self._cloud_phase != "TTS":
                raise RuntimeError("unexpected MiMo response phase")

            if not self._cloud_tts_done:
                if self._cloud_request is None:
                    self._start_tts_request(now_ms)
                    return
                request_complete = self._cloud_request.step(now_ms)
                if (
                    not self._playback_started
                    and len(self._playback_buffer) >= self.TTS_PREBUFFER_BYTES
                ):
                    self._start_cloud_playback(now_ms)
                if self._playback_started:
                    self._pump_cloud_playback(now_ms)
                if request_complete:
                    self._cloud_request.ensure_success()
                    self._cloud_tts_decoder.finish()
                    if self._cloud_tts_decoder.pcm_bytes <= 0:
                        raise RuntimeError("MiMo TTS returned no PCM")
                    self._cloud_request.close()
                    self._cloud_request = None
                    self._cloud_tts_done = True
                    self._server_finished = True
                    if not self._playback_started:
                        self._start_cloud_playback(now_ms)

            self._pump_cloud_playback(now_ms)
            if self._playback_feed_finished and not self.audio.playing:
                self._complete_cloud_question(now_ms)
        except Exception as exc:
            if not self._schedule_cloud_retry(now_ms, exc):
                self._fail(now_ms, exc)

    def _cleanup_transfer(self, keep_audio=False):
        if self._raw_file is not None:
            try:
                self._raw_file.close()
            except Exception:
                pass
        self._raw_file = None
        self._raw_recording = None
        self._raw_recorded_bytes = 0
        for source in (self._tx_source,):
            if source is not None:
                try:
                    source.close()
                except Exception:
                    pass
        self._tx_source = None
        self._wav_buffer = None
        self._process_offset = 0
        self._converted = 0
        self._close_connection()
        self._tx_buffer = None
        self._tx_offset = 0
        self._tx_audio_offset = 0
        self._tx_prefix_done = False
        self._rx_buffer = bytearray()
        self._response = {}
        self._rx_magic = None
        self._rx_header_size = None
        self._pcm_frame_size = None
        self._server_finished = False
        self._pcm_prebuffer = bytearray()
        self._playback_buffer = None
        self._playback_offset = 0
        self._playback_feed_finished = False
        self._playback_started = False
        self._playback_sample_rate = 16_000
        self._first_audio_at = None
        self._last_network_progress_at = None
        self._cloud_phase = ""
        self._cloud_transcript = ""
        self._cloud_answer = ""
        self._cloud_tts_decoder = None
        self._cloud_tts_done = False
        self._reset_cloud_retry()
        if not keep_audio:
            self.audio.stop()

    def _fail(self, now_ms, error):
        self._cleanup_transfer()
        self.error = repr(error)
        self._button_armed = False
        self._set_state(self.ERROR, now_ms, error)

    def update(self, now_ms):
        # Recording owns the fast path completely: no Wi-Fi polling, discovery,
        # telemetry, sensor rendering, or display rendering competes with I2S.
        if self.state == self.RECORDING:
            self._step_recording(now_ms)
            return

        if self.state == self.IDLE:
            self._service_idle_microphone()
        self._update_wifi(now_ms)
        # Direct MiMo mode has no LAN discovery or Mac dependency.

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

        if self.state == self.PROCESSING:
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
