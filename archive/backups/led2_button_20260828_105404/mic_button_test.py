"""One-shot board microphone test controlled by Button-Pulldown1 on IO10.

Hold the button to record.  Release it to stop.  The resulting standard
16 kHz/16-bit/mono WAV file is written to /mic_recording.wav.
"""

import framebuf
import gc
import os
import struct
import time
from machine import I2S, Pin, SoftI2C


BUTTON_PIN = 10
MIC_SCK_PIN = 41
MIC_WS_PIN = 42
MIC_SD_PIN = 2

SAMPLE_RATE = 16_000
RAW_BITS = 32
MAX_RECORD_MS = 15_000
DEBOUNCE_MS = 40

RAW_PATH = "/mic_recording.raw32"
WAV_PATH = "/mic_recording.wav"
INFO_PATH = "/mic_recording.txt"


class SSD1306(framebuf.FrameBuffer):
    def __init__(self, i2c, width=128, height=64, address=0x3C):
        self.i2c = i2c
        self.width = width
        self.height = height
        self.address = address
        self.pages = height // 8
        self.buffer = bytearray(self.pages * width)
        super().__init__(self.buffer, width, height, framebuf.MONO_VLSB)
        for command in (
            0xAE, 0x20, 0x00, 0x40, 0xA1, 0xA8, height - 1, 0xC8,
            0xD3, 0x00, 0xDA, 0x12, 0xD5, 0x80, 0xD9, 0xF1, 0xDB,
            0x30, 0x81, 0xFF, 0xA4, 0xA6, 0x8D, 0x14, 0xAF,
        ):
            self._command(command)
        self.fill(0)
        self.show()

    def _command(self, command):
        self.i2c.writeto(self.address, bytes((0x80, command)))

    def show(self):
        for command, value in ((0x21, self.width - 1), (0x22, self.pages - 1)):
            self._command(command)
            self._command(0)
            self._command(value)
        self.i2c.writeto(self.address, b"\x40" + self.buffer)


def show_lines(oled, *lines):
    if oled is None:
        return
    try:
        oled.fill(0)
        for row, line in enumerate(lines[:4]):
            oled.text(str(line)[:16], 0, row * 16, 1)
        oled.show()
    except Exception:
        pass


def remove_if_present(path):
    try:
        os.remove(path)
    except OSError:
        pass


def write_wav_header(output_file, data_size):
    byte_rate = SAMPLE_RATE * 2
    output_file.write(b"RIFF")
    output_file.write(struct.pack("<I", 36 + data_size))
    output_file.write(b"WAVEfmt ")
    output_file.write(struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE,
                                  byte_rate, 2, 16))
    output_file.write(b"data")
    output_file.write(struct.pack("<I", data_size))


def stable_pressed(button):
    if button.value() == 0:
        return False
    time.sleep_ms(DEBOUNCE_MS)
    return button.value() == 1


def convert_raw_to_wav(raw_path, wav_path, sample_count, sample_sum,
                       minimum, maximum):
    """Remove DC and normalize the captured 32-bit samples to PCM16."""
    if sample_count <= 0:
        raise RuntimeError("no microphone samples captured")

    mean = sample_sum // sample_count
    peak = max(abs(minimum - mean), abs(maximum - mean), 1)
    # Leave headroom for occasional plosives while keeping the test audible.
    target_peak = 27_000

    raw_file = open(raw_path, "rb")
    wav_file = open(wav_path, "wb")
    write_wav_header(wav_file, sample_count * 2)

    input_buffer = bytearray(4096)
    output_buffer = bytearray(2048)
    converted = 0
    while converted < sample_count:
        read_count = raw_file.readinto(input_buffer)
        if not read_count:
            break
        read_count -= read_count % 4
        output_position = 0
        for position in range(0, read_count, 4):
            sample = struct.unpack_from("<i", input_buffer, position)[0]
            value = ((sample - mean) * target_peak) // peak
            if value > 32767:
                value = 32767
            elif value < -32768:
                value = -32768
            struct.pack_into("<h", output_buffer, output_position, value)
            output_position += 2
            converted += 1
        wav_file.write(memoryview(output_buffer)[:output_position])

    raw_file.close()
    wav_file.flush()
    wav_file.close()
    return mean, peak, converted


def main():
    oled = None
    try:
        oled = SSD1306(SoftI2C(scl=Pin(5), sda=Pin(4), freq=400_000))
    except Exception as exc:
        print("OLED_ERROR", repr(exc))

    # Button-Pulldown1 is externally pulled low and goes high while pressed.
    button = Pin(BUTTON_PIN, Pin.IN)
    remove_if_present(RAW_PATH)
    remove_if_present(WAV_PATH)
    remove_if_present(INFO_PATH)

    show_lines(oled, "MIC TEST READY", "HOLD DOWN-1", "IO10 TO RECORD",
               "RELEASE=STOP")
    print("MIC_TEST_READY button=IO10 active_high")

    # Do not treat a button held during startup as a clean new press.
    while button.value():
        time.sleep_ms(20)
    while not stable_pressed(button):
        time.sleep_ms(20)

    show_lines(oled, "RECORDING...", "KEEP HOLDING", "RELEASE TO STOP")
    print("RECORDING_STARTED")

    audio = I2S(
        0,
        sck=Pin(MIC_SCK_PIN),
        ws=Pin(MIC_WS_PIN),
        sd=Pin(MIC_SD_PIN),
        mode=I2S.RX,
        bits=RAW_BITS,
        format=I2S.MONO,
        rate=SAMPLE_RATE,
        ibuf=32768,
    )
    raw_buffer = bytearray(4096)

    # Discard the first DMA blocks while the I2S peripheral settles.
    audio.readinto(raw_buffer)
    audio.readinto(raw_buffer)

    raw_file = open(RAW_PATH, "wb")
    started_at = time.ticks_ms()
    last_display_at = started_at
    sample_count = 0
    sample_sum = 0
    minimum = 2147483647
    maximum = -2147483648

    try:
        while button.value() and time.ticks_diff(time.ticks_ms(), started_at) < MAX_RECORD_MS:
            read_count = audio.readinto(raw_buffer)
            if not read_count:
                continue
            read_count -= read_count % 4
            raw_file.write(memoryview(raw_buffer)[:read_count])
            for position in range(0, read_count, 4):
                sample = struct.unpack_from("<i", raw_buffer, position)[0]
                sample_sum += sample
                sample_count += 1
                if sample < minimum:
                    minimum = sample
                if sample > maximum:
                    maximum = sample

            now = time.ticks_ms()
            if time.ticks_diff(now, last_display_at) >= 250:
                elapsed_ms = time.ticks_diff(now, started_at)
                show_lines(oled, "RECORDING...", "%02d.%01d sec" % (
                    elapsed_ms // 1000, (elapsed_ms % 1000) // 100
                ), "RELEASE TO STOP")
                last_display_at = now
    finally:
        raw_file.flush()
        raw_file.close()
        audio.deinit()

    elapsed_ms = time.ticks_diff(time.ticks_ms(), started_at)
    show_lines(oled, "PROCESSING...", "PLEASE WAIT")
    gc.collect()

    mean, peak, converted = convert_raw_to_wav(
        RAW_PATH, WAV_PATH, sample_count, sample_sum, minimum, maximum
    )
    remove_if_present(RAW_PATH)

    try:
        wav_size = os.stat(WAV_PATH)[6]
    except Exception:
        wav_size = 44 + converted * 2

    info = (
        "path=%s\nrate=%d\nchannels=1\nbits=16\n"
        "samples=%d\nduration_ms=%d\nbytes=%d\nmean32=%d\npeak32=%d\n"
        % (WAV_PATH, SAMPLE_RATE, converted, elapsed_ms, wav_size, mean, peak)
    )
    with open(INFO_PATH, "w") as info_file:
        info_file.write(info)
    try:
        os.sync()
    except AttributeError:
        pass

    seconds = converted // SAMPLE_RATE
    tenths = ((converted % SAMPLE_RATE) * 10) // SAMPLE_RATE
    show_lines(oled, "RECORDING SAVED", "/mic_recording", ".wav", "%d.%d sec" % (
        seconds, tenths
    ))
    print("RECORD_DONE", WAV_PATH, "samples", converted, "bytes", wav_size,
          "duration_ms", elapsed_ms, "mean32", mean, "peak32", peak)


main()
