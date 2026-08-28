"""Standalone ESP32-S3 IO10 voice client; does not access either display."""

import gc
import json
import os
import socket
import struct
import time
from machine import I2S, Pin
import network

from voice_qa_wifi_config import MAC_HOST, MAC_PORT, WIFI_PASSWORD, WIFI_SSID


BUTTON_PIN = 10
MIC_SCRIPT = "/mic_capture_io10.py"
WAV_PATH = "/mic_recording_io10.wav"
SPEAKER_RATE = 24_000


def recv_exact(connection, size):
    data = bytearray()
    while len(data) < size:
        chunk = connection.recv(size - len(data))
        if not chunk:
            raise RuntimeError("Mac disconnected")
        data.extend(chunk)
    return bytes(data)


def send_all(connection, data):
    view = memoryview(data)
    offset = 0
    while offset < len(data):
        sent = connection.send(view[offset:])
        if not sent:
            raise RuntimeError("Wi-Fi send stopped")
        offset += sent


def connect_wifi():
    station = network.WLAN(network.STA_IF)
    station.active(True)
    if station.isconnected():
        return station
    station.connect(WIFI_SSID, WIFI_PASSWORD)
    started = time.ticks_ms()
    while not station.isconnected():
        if time.ticks_diff(time.ticks_ms(), started) >= 25_000:
            raise RuntimeError("Wi-Fi timeout status=%s" % station.status())
        time.sleep_ms(200)
    return station


def capture_one_question():
    namespace = {"__name__": "__main__"}
    exec(open(MIC_SCRIPT).read(), namespace)
    return os.stat(WAV_PATH)[6]


def ask_mac(audio_bytes):
    connection = socket.socket()
    connection.settimeout(180)
    connection.connect((MAC_HOST, MAC_PORT))
    header = json.dumps(
        {"audio_bytes": audio_bytes, "format": "wav", "rate": 16_000}
    ).encode()
    send_all(connection, b"VQW1" + struct.pack(">I", len(header)) + header)
    source = open(WAV_PATH, "rb")
    try:
        while True:
            chunk = source.read(16_384)
            if not chunk:
                break
            send_all(connection, chunk)
    finally:
        source.close()

    magic = recv_exact(connection, 4)
    header_size = struct.unpack(">I", recv_exact(connection, 4))[0]
    response = json.loads(recv_exact(connection, header_size).decode())
    if magic != b"VA01":
        connection.close()
        raise RuntimeError(response.get("error", "Mac processing failed"))
    print("VOICE_TRANSCRIPT", response.get("transcript", ""))
    print("VOICE_ANSWER", response.get("short_answer", ""))

    speaker = I2S(
        0,
        sck=Pin(39),
        ws=Pin(40),
        sd=Pin(38),
        mode=I2S.TX,
        bits=16,
        format=I2S.MONO,
        rate=int(response.get("sample_rate", SPEAKER_RATE)),
        ibuf=32_768,
    )
    total = 0
    first_audio = None
    try:
        while True:
            chunk_size = struct.unpack(">I", recv_exact(connection, 4))[0]
            if chunk_size == 0:
                break
            chunk = recv_exact(connection, chunk_size)
            if first_audio is None:
                first_audio = time.ticks_ms()
                print("VOICE_PLAYBACK_STARTED")
            view = memoryview(chunk)
            offset = 0
            while offset < len(chunk):
                written = speaker.write(view[offset:])
                if written is None:
                    written = len(chunk) - offset
                if written <= 0:
                    raise RuntimeError("speaker write stopped")
                offset += written
            total += len(chunk)
        time.sleep_ms(1200)
    finally:
        speaker.deinit()
        connection.close()
    print("VOICE_PLAYBACK_DONE", total)


def main():
    station = connect_wifi()
    print("VOICE_WIFI_READY", station.ifconfig()[0], MAC_HOST, MAC_PORT)
    sequence = 0
    while True:
        sequence += 1
        print("VOICE_QUESTION_READY", sequence)
        try:
            size = capture_one_question()
            print("VOICE_UPLOAD_START", size)
            ask_mac(size)
        except Exception as error:
            print("VOICE_QUESTION_ERROR", repr(error))
            time.sleep_ms(1000)
            try:
                station = connect_wifi()
            except Exception as wifi_error:
                print("VOICE_WIFI_ERROR", repr(wifi_error))
        gc.collect()


main()
