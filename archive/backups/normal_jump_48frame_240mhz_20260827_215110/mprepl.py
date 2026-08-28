#!/usr/bin/env python3
"""Minimal MicroPython raw-REPL transport for the attached ESP32-S3."""

from __future__ import annotations

import glob
import time

import serial


def detect_port() -> str:
    ports = sorted(glob.glob("/dev/cu.usbserial-*") + glob.glob("/dev/cu.wchusbserial*"))
    if not ports:
        raise RuntimeError("No CH340 serial port found")
    return ports[-1]


class Port:
    def __init__(self, port: str | None = None, baud: int = 115200):
        self.name = port or detect_port()
        self.ser = serial.Serial(
            self.name,
            baudrate=baud,
            timeout=0.05,
            write_timeout=2,
            inter_byte_timeout=0.1,
        )

    def close(self) -> None:
        self.ser.close()

    def _drain(self, quiet: float = 0.12) -> bytes:
        out = bytearray()
        deadline = time.monotonic() + quiet
        while time.monotonic() < deadline:
            chunk = self.ser.read(self.ser.in_waiting or 1)
            if chunk:
                out.extend(chunk)
                deadline = time.monotonic() + quiet
        return bytes(out)

    def _read_until(self, marker: bytes, timeout: float = 8.0) -> bytes:
        out = bytearray()
        deadline = time.monotonic() + timeout
        while marker not in out:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for {marker!r}; received {bytes(out)!r}")
            chunk = self.ser.read(self.ser.in_waiting or 1)
            if chunk:
                out.extend(chunk)
        return bytes(out)

    def enter_raw(self) -> bytes:
        self.ser.write(b"\r\x03\x03")
        self.ser.flush()
        time.sleep(0.25)
        self._drain()
        self.ser.write(b"\r\x01")
        self.ser.flush()
        # A CH340 can occasionally drop the final LF/prompt bytes of the raw
        # banner.  Sending Ctrl-A once more while already in raw mode elicits
        # the short ``\n\r>`` prompt, so accept either complete form without
        # confusing the normal ``>>>`` prompt for raw mode.
        banner = bytearray()
        deadline = time.monotonic() + 5
        retry_at = time.monotonic() + 0.65
        retried = False
        while True:
            if b"CTRL-B to exit\r\n>" in banner:
                break
            if banner.endswith(b"\r>") and b">>>" not in banner[-8:]:
                break
            if not retried and time.monotonic() >= retry_at:
                self.ser.write(b"\x01")
                self.ser.flush()
                retried = True
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "Timed out waiting for raw REPL prompt; received %r"
                    % bytes(banner)
                )
            chunk = self.ser.read(self.ser.in_waiting or 1)
            if chunk:
                banner.extend(chunk)
        banner = bytes(banner)
        # CH340 occasionally drops the first byte of the banner immediately
        # after a hardware reset ("rw REPL" instead of "raw REPL").  The
        # complete control hint and prompt still prove raw mode was entered.
        if (
            b"raw REPL" not in banner
            and b"REPL; CTRL-B to exit" not in banner
            and not (banner.endswith(b"\r>") and b">>>" not in banner[-8:])
        ):
            raise RuntimeError(f"Failed to enter raw REPL: {banner!r}")
        return banner

    def exec(self, code: str, timeout: float = 10.0) -> tuple[str, str]:
        self.enter_raw()
        payload = code.encode("utf-8")
        # Small chunks also work reliably with constrained UART RX buffers.
        for pos in range(0, len(payload), 256):
            self.ser.write(payload[pos : pos + 256])
            self.ser.flush()
            time.sleep(0.01)
        self.ser.write(b"\x04")
        self.ser.flush()
        ack = self._read_until(b"OK", timeout=3)
        after_ok = ack.split(b"OK", 1)[1]
        data = bytearray(after_ok)
        deadline = time.monotonic() + timeout
        while data.count(4) < 2:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Execution timed out; received {bytes(data)!r}")
            chunk = self.ser.read(self.ser.in_waiting or 1)
            if chunk:
                data.extend(chunk)
        stdout, rest = bytes(data).split(b"\x04", 1)
        stderr, _ = rest.split(b"\x04", 1)
        return stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace")

    def start(self, code: str) -> None:
        """Start non-returning code without closing/reopening this port."""
        self.enter_raw()
        payload = code.encode("utf-8")
        for pos in range(0, len(payload), 256):
            self.ser.write(payload[pos : pos + 256])
            self.ser.flush()
            time.sleep(0.01)
        self.ser.write(b"\x04")
        self.ser.flush()
        self._read_until(b"OK", timeout=3)

    def reset(self) -> None:
        try:
            self.enter_raw()
            self.ser.write(b"import machine; machine.reset()\x04")
            self.ser.flush()
        finally:
            time.sleep(0.5)
            self.close()


def run(code: str, port: str | None = None) -> tuple[str, str]:
    p = Port(port)
    try:
        return p.exec(code)
    finally:
        p.close()


def start(code: str, port: str | None = None) -> None:
    """Start non-returning code and disconnect after raw REPL acknowledges it."""
    p = Port(port)
    try:
        p.start(code)
    finally:
        p.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("code", nargs="?", default="print('MicroPython raw REPL OK')")
    parser.add_argument("--port")
    args = parser.parse_args()
    out, err = run(args.code, args.port)
    print(out, end="")
    if err:
        print(err, end="", file=__import__("sys").stderr)
