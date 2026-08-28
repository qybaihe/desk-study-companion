#!/usr/bin/env python3
"""Upload the desk-companion display app to the attached MicroPython board."""

from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import mprepl


ROOT = Path(__file__).resolve().parent


def upload(local_name: str, remote_name: str) -> None:
    data = (ROOT / local_name).read_bytes()
    code = (
        "import os\n"
        "f=open(%r, 'wb')\n"
        "n=f.write(%r)\n"
        "f.flush()\n"
        "f.close()\n"
        "try:\n os.sync()\nexcept AttributeError:\n pass\n"
        "print(n)"
    ) % (remote_name, data)
    stdout, stderr = mprepl.run(code)
    if stderr:
        raise RuntimeError(stderr)
    print("uploaded", local_name, "->", remote_name, len(data), "bytes", stdout.strip())


if __name__ == "__main__":
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
    upload("main_board.py", "/main.py")

    out, err = mprepl.run(
        "compile(open('/st7789.py').read(), '/st7789.py', 'exec');"
        "compile(open('/vl53l0x.py').read(), '/vl53l0x.py', 'exec');"
        "compile(open('/fusion_tracker.py').read(), '/fusion_tracker.py', 'exec');"
        "compile(open('/main.py').read(), '/main.py', 'exec');"
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
