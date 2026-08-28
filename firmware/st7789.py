"""Small framebuffer-oriented ST7789 driver for the 240x240 kit display."""

import time


class ST7789:
    WIDTH = 240
    HEIGHT = 240

    def __init__(self, spi, dc, cs, rotation=0):
        self.spi = spi
        self.dc = dc
        self.cs = cs
        self.rotation = rotation % 4

        self.cs.value(1)
        self.dc.value(1)
        self._cmd(0x01)  # software reset
        time.sleep_ms(150)
        self._cmd(0x11)  # sleep out
        time.sleep_ms(120)
        self._cmd(0x3A, b"\x05")  # RGB565, 16 bits/pixel
        self._cmd(0x36, bytes((self._madctl(),)))
        self._cmd(0x21)  # inversion on (required by this IPS panel)
        self._cmd(0x13)  # normal display mode
        self._cmd(0x29)  # display on
        time.sleep_ms(20)

    def _madctl(self):
        # Values match the orientation mapping of this kit's 240x240 panel.
        return (0x00, 0xA0, 0xC0, 0x60)[self.rotation]

    def _offset(self):
        return ((0, 0), (80, 0), (0, 80), (0, 0))[self.rotation]

    def _cmd(self, command, data=None):
        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(bytes((command,)))
        if data:
            self.dc.value(1)
            self.spi.write(data)
        self.cs.value(1)

    def _window(self, x, y, width, height):
        ox, oy = self._offset()
        x0, x1 = ox + x, ox + x + width - 1
        y0, y1 = oy + y, oy + y + height - 1
        self._cmd(0x2A, bytes((x0 >> 8, x0 & 255, x1 >> 8, x1 & 255)))
        self._cmd(0x2B, bytes((y0 >> 8, y0 & 255, y1 >> 8, y1 & 255)))

    def show(self, buffer):
        self._window(0, 0, self.WIDTH, self.HEIGHT)
        self._cmd(0x2C, buffer)

    def show_region(self, buffer, x, y, width, height):
        """Update a rectangular RGB565 region without sending a full frame."""
        if len(buffer) != width * height * 2:
            raise ValueError("RGB565 region size does not match its window")
        if x < 0 or y < 0 or x + width > self.WIDTH or y + height > self.HEIGHT:
            raise ValueError("LCD region is outside the panel")
        self._window(x, y, width, height)
        self._cmd(0x2C, buffer)
