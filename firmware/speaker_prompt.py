"""Stream a signed 16-bit mono PCM prompt to the desk kit's I2S speaker."""

import time
from machine import I2S, Pin


class PCMVoicePlayer:
    """Small streaming player that keeps the PCM clip out of Python RAM."""

    def __init__(
        self,
        path,
        sample_rate=16000,
        i2s_id=0,
        data_pin=38,
        clock_pin=39,
        word_select_pin=40,
        chunk_size=16384,
        i2s_buffer_size=65536,
        drain_ms=2300,
    ):
        self.path = path
        self.sample_rate = sample_rate
        self.i2s_id = i2s_id
        self.data_pin = data_pin
        self.clock_pin = clock_pin
        self.word_select_pin = word_select_pin
        self.buffer = bytearray(chunk_size)
        self.i2s_buffer_size = i2s_buffer_size
        self.drain_ms = drain_ms

        self.audio = None
        self.source = None
        self.playing = False
        self.draining = False
        self.drain_started_at = None
        self.error = ""
        self.play_count = 0

    def _close_source(self):
        if self.source is not None:
            try:
                self.source.close()
            except Exception:
                pass
            self.source = None

    def stop(self):
        self._close_source()
        if self.audio is not None:
            try:
                self.audio.deinit()
            except Exception:
                pass
            self.audio = None
        self.playing = False
        self.draining = False
        self.drain_started_at = None

    def start(self, path=None):
        if self.playing:
            return False
        self.stop()
        self.error = ""
        if path is not None:
            self.path = path
        try:
            self.source = open(self.path, "rb")
            self.audio = I2S(
                self.i2s_id,
                sck=Pin(self.clock_pin),
                ws=Pin(self.word_select_pin),
                sd=Pin(self.data_pin),
                mode=I2S.TX,
                bits=16,
                format=I2S.MONO,
                rate=self.sample_rate,
                ibuf=self.i2s_buffer_size,
            )
            self.playing = True
            self.play_count += 1
            return True
        except Exception as exc:
            self.error = repr(exc)
            self.stop()
            return False

    def pump(self, now_ms):
        """Queue one PCM block; return True while playback is active."""
        if not self.playing:
            return False

        if self.draining:
            if time.ticks_diff(now_ms, self.drain_started_at) >= self.drain_ms:
                self.stop()
            return self.playing

        try:
            count = self.source.readinto(self.buffer)
            if count:
                view = memoryview(self.buffer)[:count]
                offset = 0
                while offset < count:
                    written = self.audio.write(view[offset:])
                    if written is None:
                        written = count - offset
                    if written <= 0:
                        raise RuntimeError("I2S write made no progress")
                    offset += written
            else:
                # I2S.write returns after copying into its DMA buffer. Leave
                # the peripheral alive briefly so the final queued syllable is
                # not truncated when the file reaches EOF.
                self._close_source()
                self.draining = True
                self.drain_started_at = now_ms
        except Exception as exc:
            self.error = repr(exc)
            self.stop()
        return self.playing
