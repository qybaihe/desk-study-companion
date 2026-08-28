"""Single owner for the ESP32-S3 microphone and speaker I2S peripheral."""

import time
from machine import I2S, Pin


class AudioManager:
    """Arbitrate local prompts, streamed answers, and microphone capture."""

    IDLE = "IDLE"
    LOCAL = "LOCAL"
    STREAM = "STREAM"
    CAPTURE = "CAPTURE"

    def __init__(
        self,
        default_path="/drink_water.pcm",
        speaker_rate=16_000,
        speaker_data_pin=38,
        speaker_clock_pin=39,
        speaker_word_select_pin=40,
        microphone_clock_pin=41,
        microphone_word_select_pin=42,
        microphone_data_pin=2,
        i2s_id=0,
        playback_buffer_size=65_536,
        local_chunk_size=16_384,
    ):
        self.path = default_path
        self.speaker_rate = int(speaker_rate)
        self.speaker_data_pin = speaker_data_pin
        self.speaker_clock_pin = speaker_clock_pin
        self.speaker_word_select_pin = speaker_word_select_pin
        self.microphone_clock_pin = microphone_clock_pin
        self.microphone_word_select_pin = microphone_word_select_pin
        self.microphone_data_pin = microphone_data_pin
        self.i2s_id = i2s_id
        self.playback_buffer_size = playback_buffer_size
        self.local_buffer = bytearray(local_chunk_size)

        self.mode = self.IDLE
        self.audio = None
        self.source = None
        self.playing = False
        self.draining = False
        self.drain_started_at = None
        self.drain_ms = 0
        self.play_count = 0
        self.error = ""

        self.capture_buffer = None
        self.capture_count = 0
        self.capture_ready = False
        self.capture_pending = False

    @property
    def busy(self):
        return self.mode != self.IDLE

    @property
    def capturing(self):
        return self.mode == self.CAPTURE

    def _close_source(self):
        if self.source is not None:
            try:
                self.source.close()
            except Exception:
                pass
            self.source = None

    def _deinit_audio(self):
        if self.audio is not None:
            try:
                if self.mode == self.CAPTURE:
                    self.audio.irq(None)
            except Exception:
                pass
            try:
                self.audio.deinit()
            except Exception:
                pass
            self.audio = None

    def stop(self):
        self._close_source()
        self._deinit_audio()
        self.mode = self.IDLE
        self.playing = False
        self.draining = False
        self.drain_started_at = None
        self.capture_buffer = None
        self.capture_count = 0
        self.capture_ready = False
        self.capture_pending = False

    def _start_speaker(self, sample_rate):
        self.audio = I2S(
            self.i2s_id,
            sck=Pin(self.speaker_clock_pin),
            ws=Pin(self.speaker_word_select_pin),
            sd=Pin(self.speaker_data_pin),
            mode=I2S.TX,
            bits=16,
            format=I2S.MONO,
            rate=int(sample_rate),
            ibuf=self.playback_buffer_size,
        )

    def start(self, path=None):
        """Compatibility entry point for the existing local reminder queue."""
        if path is None:
            path = self.path
        return self.start_local(path, self.speaker_rate)

    def start_local(self, path, sample_rate=16_000, drain_ms=2_300):
        if self.busy:
            return False
        self.stop()
        self.error = ""
        self.path = path
        try:
            self.source = open(path, "rb")
            self._start_speaker(sample_rate)
            self.mode = self.LOCAL
            self.playing = True
            self.draining = False
            self.drain_ms = int(drain_ms)
            self.play_count += 1
            return True
        except Exception as exc:
            self.error = repr(exc)
            self.stop()
            return False

    def start_stream(self, sample_rate=24_000):
        """Take I2S ownership for a PCM16 network answer."""
        self.stop()
        self.error = ""
        self.path = "@voice_qa"
        try:
            self._start_speaker(sample_rate)
            self.mode = self.STREAM
            self.playing = True
            self.draining = False
            self.drain_ms = 1_200
            self.play_count += 1
            return True
        except Exception as exc:
            self.error = repr(exc)
            self.stop()
            return False

    def _write_all(self, data):
        view = memoryview(data)
        offset = 0
        while offset < len(view):
            written = self.audio.write(view[offset:])
            if written is None:
                written = len(view) - offset
            if written <= 0:
                raise RuntimeError("I2S write made no progress")
            offset += written
        return offset

    def write_stream(self, data):
        if self.mode != self.STREAM or self.draining:
            return False
        try:
            self._write_all(data)
            return True
        except Exception as exc:
            self.error = repr(exc)
            self.stop()
            return False

    def finish_stream(self, now_ms, drain_ms=1_200):
        if self.mode != self.STREAM:
            return
        self.draining = True
        self.drain_started_at = now_ms
        self.drain_ms = int(drain_ms)

    def _capture_callback(self, _):
        # Keep the IRQ callback allocation-free. The cooperative main loop
        # writes and analyses the completed block, then explicitly rearms it.
        if self.mode != self.CAPTURE or self.capture_buffer is None:
            return
        self.capture_count = len(self.capture_buffer)
        self.capture_ready = True
        self.capture_pending = False

    def start_capture(
        self,
        sample_rate=16_000,
        bits=32,
        block_size=4_096,
        i2s_buffer_size=32_768,
    ):
        """Start one-buffer-at-a-time asynchronous microphone capture."""
        self.stop()
        self.error = ""
        try:
            self.capture_buffer = bytearray(block_size)
            self.capture_count = 0
            self.capture_ready = False
            self.capture_pending = False
            self.audio = I2S(
                self.i2s_id,
                sck=Pin(self.microphone_clock_pin),
                ws=Pin(self.microphone_word_select_pin),
                sd=Pin(self.microphone_data_pin),
                mode=I2S.RX,
                bits=int(bits),
                format=I2S.MONO,
                rate=int(sample_rate),
                ibuf=i2s_buffer_size,
            )
            self.mode = self.CAPTURE
            self.audio.irq(self._capture_callback)
            self.rearm_capture()
            return True
        except Exception as exc:
            self.error = repr(exc)
            self.stop()
            return False

    def take_capture_block(self):
        if self.mode != self.CAPTURE or not self.capture_ready:
            return None
        self.capture_ready = False
        return self.capture_buffer, self.capture_count

    def rearm_capture(self):
        if (
            self.mode != self.CAPTURE
            or self.capture_ready
            or self.capture_pending
        ):
            return False
        try:
            self.capture_count = 0
            # In ESP32 non-blocking mode readinto() returns the queued buffer
            # length immediately.  Only the IRQ callback means DMA has really
            # filled it; treating the return value as completion can queue a
            # second read on the same buffer and wedge the I2S task.
            self.audio.readinto(self.capture_buffer)
            self.capture_pending = True
            return True
        except Exception as exc:
            self.error = repr(exc)
            self.stop()
            return False

    def stop_capture(self):
        if self.mode == self.CAPTURE:
            # ESP32's I2S worker must finish its queued application buffer
            # before deinit; tearing it down mid-read can deadlock the port.
            if self.capture_pending:
                return False
            self.stop()
        return True

    def update(self, now_ms):
        """Advance local playback/draining; network streaming is push-based."""
        if self.mode == self.IDLE or self.mode == self.CAPTURE:
            return self.playing

        if self.draining:
            if time.ticks_diff(now_ms, self.drain_started_at) >= self.drain_ms:
                self.stop()
            return self.playing

        if self.mode != self.LOCAL:
            return self.playing

        try:
            count = self.source.readinto(self.local_buffer)
            if count:
                self._write_all(memoryview(self.local_buffer)[:count])
            else:
                self._close_source()
                self.draining = True
                self.drain_started_at = now_ms
        except Exception as exc:
            self.error = repr(exc)
            self.stop()
        return self.playing
