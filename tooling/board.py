"""板端会话：复位 -> 抢占 UART0 -> raw REPL。

main.py 在启动 3 秒后把 GPIO43/44 从 UART0 改成 LCD 的 DC/CS，
串口从那一刻起就哑了。所以每次连接都必须先硬复位再抢窗口。
"""
import sys, time, serial

PORT = "/dev/cu.usbserial-210"


class Board:
    def __init__(self, port=PORT, baud=115200, spam=3.6):
        self.ser = serial.Serial(port, baud, timeout=0.05, write_timeout=3)
        self.ser.setDTR(False)
        self.ser.setRTS(True)
        time.sleep(0.15)
        self.ser.reset_input_buffer()
        self.ser.setRTS(False)
        t0 = time.monotonic()
        while time.monotonic() - t0 < spam:
            self.ser.write(b"\x03"); self.ser.flush()
            time.sleep(0.02)
            self.ser.read(self.ser.in_waiting or 1)
        self._enter_raw()

    def _drain(self, quiet=0.15):
        out = bytearray()
        deadline = time.monotonic() + quiet
        while time.monotonic() < deadline:
            c = self.ser.read(self.ser.in_waiting or 1)
            if c:
                out.extend(c); deadline = time.monotonic() + quiet
        return bytes(out)

    def _enter_raw(self):
        self.ser.write(b"\r\x03\x03"); self.ser.flush()
        time.sleep(0.2); self._drain()
        self.ser.write(b"\r\x01"); self.ser.flush()
        banner = bytearray()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            c = self.ser.read(self.ser.in_waiting or 1)
            if c:
                banner.extend(c)
            if b"CTRL-B to exit\r\n>" in banner or banner.endswith(b"\r>"):
                return bytes(banner)
        raise RuntimeError("raw REPL failed: %r" % bytes(banner)[-200:])

    def exec(self, code, timeout=30.0):
        payload = code.encode()
        for i in range(0, len(payload), 256):
            self.ser.write(payload[i:i + 256]); self.ser.flush()
            time.sleep(0.01)
        self.ser.write(b"\x04"); self.ser.flush()
        data = bytearray()
        deadline = time.monotonic() + 3
        while b"OK" not in data:
            if time.monotonic() > deadline:
                raise TimeoutError("no OK: %r" % bytes(data)[-200:])
            c = self.ser.read(self.ser.in_waiting or 1)
            if c: data.extend(c)
        data = bytearray(bytes(data).split(b"OK", 1)[1])
        deadline = time.monotonic() + timeout
        while data.count(4) < 2:
            if time.monotonic() > deadline:
                raise TimeoutError("exec timeout: %r" % bytes(data)[-400:])
            c = self.ser.read(self.ser.in_waiting or 1)
            if c: data.extend(c)
        out, rest = bytes(data).split(b"\x04", 1)
        err, _ = rest.split(b"\x04", 1)
        return out.decode("utf-8", "replace"), err.decode("utf-8", "replace")

    def put(self, remote_path, local_path):
        """分块写文件，避免大 payload 撑爆 UART RX。"""
        with open(local_path, "rb") as f:
            blob = f.read()
        self.exec("f=open(%r,'wb')" % remote_path)
        for i in range(0, len(blob), 512):
            self.exec("f.write(%r)" % blob[i:i + 512], timeout=15)
        self.exec("f.close()")
        o, _ = self.exec("import os;print(os.stat(%r)[6])" % remote_path)
        return int(o.strip()), len(blob)

    def close(self):
        try: self.ser.close()
        except Exception: pass


def run(code, timeout=30.0):
    b = Board()
    try:
        return b.exec(code, timeout)
    finally:
        b.close()


if __name__ == "__main__":
    code = sys.argv[1] if len(sys.argv) > 1 else "print('board ok')"
    o, e = run(code, timeout=float(sys.argv[2]) if len(sys.argv) > 2 else 30.0)
    sys.stdout.write(o)
    if e.strip(): sys.stderr.write("\n[stderr]\n" + e)
