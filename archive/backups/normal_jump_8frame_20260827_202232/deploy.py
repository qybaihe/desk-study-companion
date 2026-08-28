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
    upload(
        "assets/pets/v2/lcd/normal.rgb565",
        "/normal.rgb565",
    )
    for animation_name in ("normal", "sick", "evolved"):
        for frame_number in range(4):
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
        "compile(open('/main.py').read(), '/main.py', 'exec');"
        "import binascii;"
        "a=open('/normal.rgb565','rb').read();"
        "b=open('/normal_3.rgb565','rb').read();"
        "assert len(a)==30464 and len(b)==30464 and "
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
