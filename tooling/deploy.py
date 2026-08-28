#!/usr/bin/env python3
"""Upload the desk-companion display app to the attached MicroPython board."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import base64
import fcntl
import sys
import time
import zlib


REPO_ROOT = Path(__file__).resolve().parents[1]
FIRMWARE_ROOT = REPO_ROOT / "firmware"
VOICE_ROOT = REPO_ROOT / "services" / "voice_ai"
RUNTIME_ROOT = REPO_ROOT / "runtime"
sys.path.insert(0, str(REPO_ROOT))

import mprepl  # noqa: E402
import serial  # noqa: E402
from services.voice_ai.build_device_voice_config import (  # noqa: E402
    build as build_voice_config,
)


DEPLOY_LOCK_PATH = "/tmp/tidb-esp32-deploy.lock"
BOARD = None


def board_run(code: str):
    """Use one persistent serial connection for the entire deployment."""
    global BOARD
    if BOARD is None:
        return mprepl.run(code)
    last_error = None
    for attempt in range(3):
        try:
            return BOARD.exec(code)
        except (serial.SerialException, OSError, TimeoutError) as error:
            last_error = error
            # A CH340 can briefly detach when the board resets or when macOS
            # re-enumerates the tty. Re-enter the startup recovery window and
            # retry the idempotent CRC/chunk operation.
            try:
                BOARD.close()
            except Exception:
                pass
            BOARD = None
            if attempt == 2:
                break
            time.sleep(0.4)
            hard_reset_into_recovery_window()
            BOARD = mprepl.Port()
    raise RuntimeError("serial operation failed after reconnects") from last_error


def acquire_deployment_lock():
    """Serialize board writes across concurrent local Codex tasks."""
    lock_file = open(DEPLOY_LOCK_PATH, "w")
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
    return lock_file


def hard_reset_into_recovery_window() -> None:
    """Reset before GPIO43/GPIO44 are reassigned from UART to the LCD."""
    last_error = None
    connection = None
    for _attempt in range(20):
        try:
            port = mprepl.detect_port()
            connection = serial.Serial(port, 115200, timeout=0.05)
            break
        except Exception as error:
            last_error = error
            time.sleep(0.15)
    if connection is None:
        raise RuntimeError("serial port did not re-enumerate") from last_error
    try:
        connection.dtr = False
        connection.rts = True
        time.sleep(0.2)
        connection.rts = False
    finally:
        connection.close()
    time.sleep(1.4)


def upload(local_name: str, remote_name: str) -> None:
    local_path = Path(local_name)
    if not local_path.is_absolute():
        local_path = REPO_ROOT / local_path
    data = local_path.read_bytes()
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
    stdout, stderr = board_run(inspect_code)
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
        stdout, stderr = board_run(
            "f=open(%r,'wb');f.close();print('READY')" % remote_name
        )
        if stderr or stdout.strip() != "READY":
            raise RuntimeError(stderr or stdout)
        written_total = 0
        for offset in range(0, len(data), 12_288):
            chunk = data[offset : offset + 12_288]
            encoded = base64.b64encode(chunk)
            # Base64 has fixed 4/3 expansion, unlike bytes repr which can grow
            # nearly fourfold.  A 12 KB raw chunk therefore stays near 16 KB.
            # Seek before writing so a retry overwrites rather than appends.
            command = (
                "import binascii;d=binascii.a2b_base64(%r);"
                "f=open(%r,'r+b');f.seek(%d);n=f.write(d);"
                "f.close();print(n)"
                % (encoded, remote_name, offset)
            )
            last_error = ""
            for attempt in range(3):
                try:
                    stdout, stderr = board_run(command)
                    if not stderr and stdout.strip() == str(len(chunk)):
                        last_error = ""
                        break
                    last_error = stderr or stdout
                except Exception as exc:
                    last_error = repr(exc)
                time.sleep(0.15)
            if last_error:
                raise RuntimeError(last_error)
            written_total = offset + len(chunk)
            print(
                "uploading", local_name,
                "%d/%d" % (written_total, len(data)),
            )
        stdout, stderr = board_run(
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
        stdout, stderr = board_run(code)
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
    generated_voice_config = build_voice_config()
    print("generated private board voice config:", generated_voice_config)
    deployment_lock = acquire_deployment_lock()
    hard_reset_into_recovery_window()
    BOARD = mprepl.Port()

    backup = RUNTIME_ROOT / "board_backups" / "main_previous.py"
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        # Preserve the currently installed application before replacing it.
        out, err = board_run("print(open('/main.py').read())")
        if err:
            raise RuntimeError(err)
        backup.write_text(out, encoding="utf-8")
        print("saved previous /main.py as main_board_previous.py")
    else:
        print("kept existing original backup main_board_previous.py")

    upload("firmware/st7789.py", "/st7789.py")
    upload("firmware/vl53l0x.py", "/vl53l0x.py")
    upload("firmware/fusion_tracker.py", "/fusion_tracker.py")
    upload("firmware/presence_tracker.py", "/presence_tracker.py")
    upload("firmware/pet_animation.py", "/pet_animation.py")
    upload("firmware/pet_growth.py", "/pet_growth.py")
    upload("firmware/study_reminder.py", "/study_reminder.py")
    upload("firmware/audio_manager.py", "/audio_manager.py")
    upload("firmware/voice_qa_client.py", "/voice_qa_client.py")
    upload(
        "services/voice_ai/generated/voice_qa_config.py",
        "/voice_qa_config.py",
    )
    upload("firmware/speaker_prompt.py", "/speaker_prompt.py")
    upload(
        "firmware/assets/audio/drink_water_16k_s16le.pcm",
        "/drink_water.pcm",
    )
    upload(
        "firmware/assets/audio/light_too_dark_16k_s16le.pcm",
        "/light_too_dark.pcm",
    )
    upload(
        "firmware/assets/pets/v2/lcd/normal.rgb565",
        "/normal.rgb565",
    )
    for animation_name, frame_count in (
        ("normal", 48), ("sick", 4), ("evolved", 4),
    ):
        for frame_number in range(frame_count):
            upload(
                "firmware/assets/pets/v2/lcd/%s_%d.rgb565"
                % (animation_name, frame_number),
                "/%s_%d.rgb565" % (animation_name, frame_number),
            )
    for frame_number in range(8):
        upload(
            "firmware/assets/pets/low_light/lcd/low_light_%d.rgb565"
            % frame_number,
            "/low_light_%d.rgb565" % frame_number,
        )
        upload(
            "firmware/assets/pets/rest_break/lcd/rest_break_%d.rgb565"
            % frame_number,
            "/rest_break_%d.rgb565" % frame_number,
        )
    upload("firmware/main.py", "/main.py")

    out, err = board_run(
        "compile(open('/st7789.py').read(), '/st7789.py', 'exec');"
        "compile(open('/vl53l0x.py').read(), '/vl53l0x.py', 'exec');"
        "compile(open('/fusion_tracker.py').read(), '/fusion_tracker.py', 'exec');"
        "compile(open('/presence_tracker.py').read(), '/presence_tracker.py', 'exec');"
        "compile(open('/pet_animation.py').read(), '/pet_animation.py', 'exec');"
        "compile(open('/pet_growth.py').read(), '/pet_growth.py', 'exec');"
        "compile(open('/study_reminder.py').read(), '/study_reminder.py', 'exec');"
        "compile(open('/audio_manager.py').read(), '/audio_manager.py', 'exec');"
        "compile(open('/voice_qa_client.py').read(), '/voice_qa_client.py', 'exec');"
        "compile(open('/voice_qa_config.py').read(), '/voice_qa_config.py', 'exec');"
        "compile(open('/speaker_prompt.py').read(), '/speaker_prompt.py', 'exec');"
        "compile(open('/main.py').read(), '/main.py', 'exec');"
        "import binascii;"
        "a=open('/normal.rgb565','rb').read();"
        "b=open('/normal_47.rgb565','rb').read();"
        "c=open('/drink_water.pcm','rb').read();"
        "d=open('/light_too_dark.pcm','rb').read();"
        "e=open('/low_light_0.rgb565','rb').read();"
        "f=open('/low_light_7.rgb565','rb').read();"
        "g=open('/rest_break_0.rgb565','rb').read();"
        "h=open('/rest_break_7.rgb565','rb').read();"
        "assert len(a)==30464 and len(b)==30464 and len(c)>0 and len(c)%2==0 and "
        "len(d)>0 and len(d)%2==0 and "
        "len(e)==30464 and len(f)==30464 and "
        "len(g)==30464 and len(h)==30464 and "
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
    BOARD.start(launch_code)
    BOARD.close()
    BOARD = None
    print("Beijing RTC set and display application started:", now.strftime("%F %T"))
