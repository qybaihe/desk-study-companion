import framebuf, time
from machine import Pin, SoftI2C, ADC

# --- grace window: Ctrl-C here drops to REPL before any pin takeover ---
time.sleep(3)


class SSD1306(framebuf.FrameBuffer):
    def __init__(self, i2c, w=128, h=64, addr=0x3C):
        self.i2c, self.w, self.h, self.addr = i2c, w, h, addr
        self.pages = h // 8
        self.buf = bytearray(self.pages * w)
        super().__init__(self.buf, w, h, framebuf.MONO_VLSB)
        for c in (0xAE, 0x20, 0x00, 0x40, 0xA1, 0xA8, h - 1, 0xC8, 0xD3, 0x00,
                  0xDA, 0x12, 0xD5, 0x80, 0xD9, 0xF1, 0xDB, 0x30, 0x81, 0xFF,
                  0xA4, 0xA6, 0x8D, 0x14, 0xAF):
            self.cmd(c)
        self.fill(0); self.show()

    def cmd(self, c):
        self.i2c.writeto(self.addr, bytes([0x80, c]))

    def show(self):
        for a, b in ((0x21, self.w - 1), (0x22, self.pages - 1)):
            self.cmd(a); self.cmd(0); self.cmd(b)
        self.i2c.writeto(self.addr, b'\x40' + self.buf)


def big(fb, text, x, y, s=2):
    tw = len(text) * 8
    tmp = framebuf.FrameBuffer(bytearray(tw), tw, 8, framebuf.MONO_HLSB)
    tmp.fill(0); tmp.text(text, 0, 0, 1)
    for px in range(tw):
        for py in range(8):
            if tmp.pixel(px, py):
                fb.fill_rect(x + px * s, y + py * s, s, s, 1)


def bar(fb, x, y, w, h, frac):
    fb.rect(x, y, w, h, 1)
    n = int((w - 2) * max(0.0, min(1.0, frac)))
    if n:
        fb.fill_rect(x + 1, y + 1, n, h - 2, 1)


def read12(a):
    try:
        return a.read_u16() >> 4
    except AttributeError:
        return a.read()


i2c = SoftI2C(scl=Pin(5), sda=Pin(4), freq=400000)
oled = SSD1306(i2c)
a1, a2 = ADC(Pin(6)), ADC(Pin(7))
for a in (a1, a2):
    try:
        a.atten(ADC.ATTN_11DB)
    except Exception:
        pass
pir = Pin(16, Pin.IN)

lo1, hi1 = 4095, 0
lo2, hi2 = 4095, 0
state = {}

while True:
    v1 = sum(read12(a1) for _ in range(8)) // 8
    v2 = sum(read12(a2) for _ in range(8)) // 8
    lo1, hi1 = min(lo1, v1), max(hi1, v1)
    lo2, hi2 = min(lo2, v2), max(hi2, v2)
    p = pir.value()
    state["v1"], state["v2"] = v1, v2
    state["lo1"], state["hi1"] = lo1, hi1
    state["lo2"], state["hi2"] = lo2, hi2
    state["pir"] = p
    try:
        f = open("/state.txt", "w")
        f.write("v1=%d v2=%d lo1=%d hi1=%d lo2=%d hi2=%d pir=%d\n"
                % (v1, v2, lo1, hi1, lo2, hi2, p))
        f.close()
    except Exception:
        pass

    oled.fill(0)
    big(oled, "L1 %4d" % v1, 2, 0, 2)
    bar(oled, 2, 16, 124, 8, v1 / 4095)
    oled.text("lo%4d hi%4d" % (lo1, hi1), 2, 26, 1)
    oled.text("L2 %4d" % v2, 2, 35, 1)
    bar(oled, 66, 35, 60, 8, v2 / 4095)
    oled.text("PIR %s" % ("MOTION" if p else "-"), 2, 47, 1)
    oled.text("cover L1 to test", 2, 56, 1)
    oled.show()
    time.sleep_ms(120)
