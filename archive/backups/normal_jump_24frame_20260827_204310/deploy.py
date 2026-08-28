#!/usr/bin/env python3
"""Upload the desk-companion display app to the attached MicroPython board."""

from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import time
import zlib

import mprepl
import serial


ROOT = Path(__file__).resolve().parent


def hard_reset_into_recovery_window() -> None:
    """Reset before GPIO43/GPIO44 are reassigned from UART to the LCD."""
    port = mprepl.detect_port()
    connection = serial.Serial(port, 115200, timeout=0.05)
    try:
        connection.dtr = False
        connection.rts = True
        time.sleep(0.2)
        connection.rts = False
    finally:
        connection.close()
    time.sleep(1.0)


def upload(local_name: str, remote_name: str) -> None:
    data = (ROOT / local_name).read_bytes()
    expected_crc = zlib.crc32(data) & 0xFFFFFFFF

    # Make deployment resumable: a prior interrupted run no longer requires
    # rewriting every 30 KB animation frame.
    inspect_code = (
        "import binascii\n"
        "try:\n"
        " f=open(%r,'rb'); d=f.read(); f.close(); "
        "print(len(d),binascii.crc32(d)&0xffffffff)\n"
        "except Exception:\n print('MISSING')"
    ) % remote_name
    stdout, stderr = mprepl.run(inspect_code)
    if stderr:
        raise RuntimeError(stderr)
    if stdout.strip() == "%d %d" % (len(data), expected_crc):
        print(
            "verified", local_name, "->", remote_name,
            len(data), "bytes", "crc32=%08x" % expected_crc,
        )
        return

    # Raw REPL has a finite command buffer. Stream larger binary assets in
    # small append commands instead of embedding the complete file in one
    # Python statement.
    if len(data) > 24_000:
        stdout, stderr = mprepl.run(
            "f=open(%r,'wb');f.close();print('READY')" % remote_name
        )
        if stderr or stdout.strip() != "READY":
            raise RuntimeError(stderr or stdout)
        written_total = 0
        for offset in range(0, len(data), 16_384):
            chunk = data[offset : offset + 16_384]
            stdout, stderr = mprepl.run(
                "f=open(%r,'ab');n=f.write(%r);f.close();print(n)"
                % (remote_name, chunk)
            )
            if stderr or stdout.strip() != str(len(chunk)):
                raise RuntimeError(stderr or stdout)
            written_total += len(chunk)
            print(
                "uploading", local_name,
                "%d/%d" % (written_total, len(data)),
            )
        stdout, stderr = mprepl.run(
            "import os,binascii\n"
            "try:\n os.sync()\nexcept AttributeError:\n pass\n"
            "f=open(%r,'rb');d=f.read();f.close();"
            "print(len(d),binascii.crc32(d)&0xffffffff)" % remote_name
        )
    else:
        code = (
            "import os,binascii\n"
            "f=open(%r, 'wb')\n"
            "n=f.write(%r)\n"
            "f.flush()\n"
            "f.close()\n"
            "try:\n os.sync()\nexcept AttributeError:\n pass\n"
            "f=open(%r,'rb'); d=f.read(); f.close()\n"
            "print(n,binascii.crc32(d)&0xffffffff)"
        ) % (remote_name, data, remote_name)
        stdout, stderr = mprepl.run(code)
    if stderr:
        raise RuntimeError(stderr)
    if stdout.strip() != "%d %d" % (len(data), expected_crc):
        raise RuntimeError(
            "read-back verification failed for %s: %s"
            % (remote_name, stdout.strip())
        )
    print(
        "uploaded", local_name, "->", remote_name,
        len(data), "bytes", "crc32=%08x" % expected_crc,
    )


if __name__ == "__main__":
    hard_reset_into_recovery_window()

    # Preserve the currently installed application before replacing it.
    out, err = mprepl.run("print(open('/main.py').read())")
    if err:
        raise RuntimeError(err)
    backup = ROOT / "main_board_previous.py"
    if not backup.exists():
        backup.write_text(out, encoding="utf-8")
        print("saved previous /main.py as main_board_previous.py")
    else:
        print("kept existing original backup main_board_previous.py")

    upload("st7789.py", "/st7789.py")
    upload("vl53l0x.py", "/vl53l0x.py")
    upload("fusion_tracker.py", "/fusion_tracker.py")
    upload("pet_animation.py", "/pet_animation.py")
    upload("pet_growth.py", "/pet_growth.py")
    upload("study_reminder.py", "/study_reminder.py")
    upload("speaker_prompt.py", "/speaker_prompt.py")
    upload(
        "assets/audio/drink_water_16k_s16le.pcm",
        "/drink_water.pcm",
    )
    upload(
        "assets/pets/v2/lcd/normal.rgb565",
        "/normal.rgb565",
    )
    for animation_name, frame_count in (
        ("normal", 8), ("sick", 4), ("evolved", 4),
    ):
        for frame_number in range(frame_count):
            upload(
                "assets/pets/v2/lcd/%s_%d.rgb565"
                % (animation_name, frame_number),
                "/%s_%d.rgb565" % (animation_name, frame_number),
            )
    upload("main_board.py", "/main.py")

    out, err = mprepl.run(
        "compile(open('/st7789.py').read(), '/st7789.py', 'exec');"
        "compile(open('/vl53l0x.py').read(), '/vl53l0x.py', 'exec');"
        "compile(open('/fusion_tracker.py').read(), '/fusion_tracker.py', 'exec');"
        "compile(open('/pet_animation.py').read(), '/pet_animation.py', 'exec');"
        "compile(open('/pet_growth.py').read(), '/pet_growth.py', 'exec');"
        "compile(open('/study_reminder.py').read(), '/study_reminder.py', 'exec');"
        "compile(open('/speaker_prompt.py').read(), '/speaker_prompt.py', 'exec');"
        "compile(open('/main.py').read(), '/main.py', 'exec');"
        "import binascii;"
        "a=open('/normal.rgb565','rb').read();"
        "b=open('/normal_7.rgb565','rb').read();"
        "c=open('/drink_water.pcm','rb').read();"
        "assert len(a)==30464 and len(b)==30464 and len(c)>0 and len(c)%2==0 and "
        "binascii.crc32(a)==binascii.crc32(b);"
        "print('COMPILE_OK')"
    )
    if err or "COMPILE_OK" not in out:
        raise RuntimeError(err or out)
    print("board-side compile check: OK")

    # The board currently has no configured Wi-Fi/NTP. Seed its RTC from the
    # host's Asia/Shanghai clock so the OLED can immediately show Beijing time.
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    weekday = now.weekday()
    rtc_tuple = (
        now.year, now.month, now.day, weekday,
        now.hour, now.minute, now.second, 0,
    )
    launch_code = (
        "import machine\n"
        "machine.RTC().datetime(%r)\n"
        "exec(open('/main.py').read(), {'__name__':'__main__'})"
    ) % (rtc_tuple,)
    mprepl.start(launch_code)
    print("Beijing RTC set and display application started:", now.strftime("%F %T"))
