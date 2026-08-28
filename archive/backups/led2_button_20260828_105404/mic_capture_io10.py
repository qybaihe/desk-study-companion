"""Isolated one-shot microphone capture for the IO10 pulldown button.

This test intentionally does not import, initialize, clear, or update either
display.  It only uses IO10 and the board microphone I2S pins 41/42/2.
"""

import gc
import os
import struct
import time
from machine import I2S, Pin


BUTTON_PIN = 10
MIC_SCK_PIN = 41
MIC_WS_PIN = 42
MIC_SD_PIN = 2
SAMPLE_RATE = 16_000
MAX_RECORD_MS = 60_000
RAW_PATH = "/mic_recording_io10.raw32"
WAV_PATH = "/mic_recording_io10.wav"
INFO_PATH = "/mic_recording_io10.txt"


def remove_if_present(path):
    try:
        os.remove(path)
    except OSError:
        pass


def write_wav_header(output_file, data_size):
    output_file.write(b"RIFF")
    output_file.write(struct.pack("<I", 36 + data_size))
    output_file.write(b"WAVEfmt ")
    output_file.write(
        struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE,
                    SAMPLE_RATE * 2, 2, 16)
    )
    output_file.write(b"data")
    output_file.write(struct.pack("<I", data_size))


def convert_to_pcm16(sample_count, sample_sum, minimum, maximum):
    mean = sample_sum // sample_count
    peak = max(abs(minimum - mean), abs(maximum - mean), 1)
    target_peak = 27_000

    source = open(RAW_PATH, "rb")
    target = open(WAV_PATH, "wb")
    write_wav_header(target, sample_count * 2)
    source_buffer = bytearray(4096)
    target_buffer = bytearray(2048)
    converted = 0

    while converted < sample_count:
        count = source.readinto(source_buffer)
        if not count:
            break
        count -= count % 4
        output_position = 0
        for position in range(0, count, 4):
            sample = struct.unpack_from("<i", source_buffer, position)[0]
            value = ((sample - mean) * target_peak) // peak
            if value > 32767:
                value = 32767
            elif value < -32768:
                value = -32768
            struct.pack_into("<h", target_buffer, output_position, value)
            output_position += 2
            converted += 1
        target.write(memoryview(target_buffer)[:output_position])

    source.close()
    target.flush()
    target.close()
    return mean, peak, converted


def main():
    button = Pin(BUTTON_PIN, Pin.IN)
    remove_if_present(RAW_PATH)
    remove_if_present(WAV_PATH)
    remove_if_present(INFO_PATH)

    # Start the microphone before waiting for the button.  Keeping the DMA
    # stream drained here means the first saved block belongs to the press,
    # rather than losing the beginning while I2S is being initialized.
    audio = I2S(
        0,
        sck=Pin(MIC_SCK_PIN),
        ws=Pin(MIC_WS_PIN),
        sd=Pin(MIC_SD_PIN),
        mode=I2S.RX,
        bits=32,
        format=I2S.MONO,
        rate=SAMPLE_RATE,
        ibuf=32768,
    )
    buffer = bytearray(2048)
    audio.readinto(buffer)
    audio.readinto(buffer)

    # Require a fresh low-to-high transition after the recorder is ready.
    while button.value():
        audio.readinto(buffer)
    print("MIC_CAPTURE_READY IO10")
    pressed_at = None
    while True:
        # Continuously drain old samples.  One block is about 32 ms, so start
        # and release latency stay well below normal speech timing.
        audio.readinto(buffer)
        if button.value():
            now = time.ticks_ms()
            if pressed_at is None:
                pressed_at = now
            elif time.ticks_diff(now, pressed_at) >= 40:
                break
        else:
            pressed_at = None

    print("RECORDING_STARTED")
    raw_file = open(RAW_PATH, "wb")
    started_at = time.ticks_ms()
    sample_count = 0
    sample_sum = 0
    minimum = 2147483647
    maximum = -2147483648

    try:
        while button.value():
            if time.ticks_diff(time.ticks_ms(), started_at) >= MAX_RECORD_MS:
                break
            count = audio.readinto(buffer)
            if not count:
                continue
            count -= count % 4
            raw_file.write(memoryview(buffer)[:count])
            for position in range(0, count, 4):
                sample = struct.unpack_from("<i", buffer, position)[0]
                sample_count += 1
                sample_sum += sample
                if sample < minimum:
                    minimum = sample
                if sample > maximum:
                    maximum = sample
    finally:
        raw_file.flush()
        raw_file.close()
        audio.deinit()

    elapsed_ms = time.ticks_diff(time.ticks_ms(), started_at)
    if sample_count < SAMPLE_RATE // 5:
        remove_if_present(RAW_PATH)
        raise RuntimeError("recording shorter than 0.2 seconds")

    print("RECORDING_STOPPED", elapsed_ms)
    gc.collect()
    mean, peak, converted = convert_to_pcm16(
        sample_count, sample_sum, minimum, maximum
    )
    remove_if_present(RAW_PATH)
    wav_size = os.stat(WAV_PATH)[6]
    duration_ms = (converted * 1000) // SAMPLE_RATE
    with open(INFO_PATH, "w") as info_file:
        info_file.write(
            "path=%s\nrate=%d\nchannels=1\nbits=16\n"
            "samples=%d\nduration_ms=%d\nbytes=%d\nmean32=%d\npeak32=%d\n"
            % (WAV_PATH, SAMPLE_RATE, converted, duration_ms,
               wav_size, mean, peak)
        )
    try:
        os.sync()
    except AttributeError:
        pass
    print("RECORD_DONE", WAV_PATH, "bytes", wav_size,
          "duration_ms", duration_ms)


main()
