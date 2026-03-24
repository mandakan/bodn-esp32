# st7735.py — minimal framebuf-based ST7735 driver for MicroPython
#
# Usage:
#   from machine import Pin, SPI
#   from st7735 import ST7735
#
#   spi = SPI(1, baudrate=26_000_000, sck=Pin(12), mosi=Pin(11))
#   tft = ST7735(spi, cs=Pin(10, Pin.OUT), dc=Pin(8, Pin.OUT), rst=Pin(9, Pin.OUT))
#   tft.fill(0x0000)
#   tft.text("Hello", 10, 10, 0xFFFF)
#   tft.show()

import framebuf
import time

# ST7735 commands
_SWRESET = 0x01
_SLPOUT = 0x11
_FRMCTR1 = 0xB1
_MADCTL = 0x36
_COLMOD = 0x3A
_CASET = 0x2A
_RASET = 0x2B
_RAMWR = 0x2C
_INVON = 0x21
_DISPON = 0x29


class ST7735(framebuf.FrameBuffer):
    """Framebuf-based ST7735 driver. Draw with fill/text/rect/pixel/line, then call show()."""

    def __init__(
        self,
        spi,
        cs,
        dc,
        rst,
        width=128,
        height=160,
        col_offset=0,
        row_offset=0,
        madctl=0x00,
        skip_reset=False,
    ):
        self.spi = spi
        self.cs = cs
        self.dc = dc
        self.rst = rst
        self.width = width
        self.height = height
        self._col_offset = col_offset
        self._row_offset = row_offset
        self._madctl = madctl
        self._buf = bytearray(width * height * 2)
        super().__init__(self._buf, width, height, framebuf.RGB565)
        self._init_display(skip_reset=skip_reset)

    def _cmd(self, cmd, data=None):
        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(bytes([cmd]))
        if data:
            self.dc.value(1)
            self.spi.write(data)
        self.cs.value(1)

    def _init_display(self, skip_reset=False):
        if not skip_reset:
            # Hardware reset (affects all displays sharing this RST pin)
            self.rst.value(1)
            time.sleep_ms(50)
            self.rst.value(0)
            time.sleep_ms(50)
            self.rst.value(1)
            time.sleep_ms(150)

        # These commands are shared by ST7735, ST7789, and ILI9341,
        # so this driver works on real hardware and in Wokwi (ILI9341).
        self._cmd(_SWRESET)
        time.sleep_ms(150)
        self._cmd(_SLPOUT)
        time.sleep_ms(150)
        self._cmd(_COLMOD, b"\x05")  # 16-bit RGB565
        self._cmd(_MADCTL, bytes([self._madctl]))
        self._cmd(_DISPON)
        time.sleep_ms(100)

    def show(self):
        """Push the framebuffer to the display."""
        x0 = self._col_offset
        x1 = x0 + self.width - 1
        y0 = self._row_offset
        y1 = y0 + self.height - 1
        self._cmd(_CASET, bytes([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF]))
        self._cmd(_RASET, bytes([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF]))
        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(bytes([_RAMWR]))
        self.dc.value(1)
        self.spi.write(self._buf)
        self.cs.value(1)

    def show_rect(self, x, y, w, h):
        """Push a sub-rectangle of the framebuffer to the display.

        Falls back to show() when the region covers more than half the screen.
        Coordinates are in logical (post-rotation) framebuffer space.
        """
        # Clamp to screen bounds
        if x < 0:
            w += x
            x = 0
        if y < 0:
            h += y
            y = 0
        if x + w > self.width:
            w = self.width - x
        if y + h > self.height:
            h = self.height - y
        if w <= 0 or h <= 0:
            return
        # Fallback for large regions
        if w * h > self.width * self.height // 2:
            self.show()
            return
        # Set address window
        x0 = self._col_offset + x
        x1 = x0 + w - 1
        y0 = self._row_offset + y
        y1 = y0 + h - 1
        self._cmd(_CASET, bytes([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF]))
        self._cmd(_RASET, bytes([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF]))
        # Begin RAMWR
        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(bytes([_RAMWR]))
        self.dc.value(1)
        # Push pixel data from framebuffer
        mv = memoryview(self._buf)
        stride = self.width * 2
        if w == self.width:
            # Full-width: contiguous slice, single write
            start = y * stride
            self.spi.write(mv[start : start + h * stride])
        else:
            # Partial-width: one write per row
            row_bytes = w * 2
            for row in range(h):
                start = (y + row) * stride + x * 2
                self.spi.write(mv[start : start + row_bytes])
        self.cs.value(1)

    @staticmethod
    def rgb(r, g, b):
        """Convert 8-bit RGB to byte-swapped RGB565 for framebuf."""
        c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        return ((c & 0xFF) << 8) | (c >> 8)
