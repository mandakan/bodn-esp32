# st7735.py — minimal framebuf-based ST7735 driver for MicroPython
#
# Supports two backends:
#   - machine.SPI (blocking) — pass SPI object as first arg
#   - _spidma DMA (non-blocking) — pass slot ID (int) as first arg
#
# Usage (blocking):
#   spi = SPI(1, baudrate=26_000_000, sck=Pin(12), mosi=Pin(11))
#   tft = ST7735(spi, cs=Pin(10, Pin.OUT), dc=Pin(8, Pin.OUT), rst=Pin(9, Pin.OUT))
#
# Usage (DMA):
#   import _spidma
#   _spidma.init(sck=12, mosi=11, baudrate=26_000_000)
#   _spidma.add_display(slot=0, cs=10, dc=8, width=320, height=240)
#   tft = ST7735(0, rst=Pin(9, Pin.OUT), width=320, height=240, ...)

import framebuf
import time

try:
    import _spidma
except ImportError:
    _spidma = None

# Reusable 8×8 glyph buffer for extended character blit
_glyph_buf = bytearray(8 * 8 * 2)
_glyph_fb = framebuf.FrameBuffer(_glyph_buf, 8, 8, framebuf.RGB565)

try:
    from bodn.ui.font_ext import GLYPHS as _EXT_GLYPHS
except ImportError:
    _EXT_GLYPHS = {}

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
        spi_or_slot,
        cs=None,
        dc=None,
        rst=None,
        width=128,
        height=160,
        col_offset=0,
        row_offset=0,
        madctl=0x00,
        skip_reset=False,
    ):
        if _spidma is not None and isinstance(spi_or_slot, int):
            # Native DMA mode — slot ID from _spidma.add_display()
            self._slot = spi_or_slot
            self._native = True
            self.spi = None
            self.cs = None
            self.dc = None
        else:
            # Legacy blocking mode — machine.SPI object
            self._slot = -1
            self._native = False
            self.spi = spi_or_slot
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
        # Dirty rect tracking: (x0, y0, x1, y1) bounding box of all draws
        # None = clean, call mark_dirty() to expand the box
        self._drect = None
        self._init_display(skip_reset=skip_reset)

    def _cmd(self, cmd, data=None):
        if self._native:
            _spidma.cmd(self._slot, cmd, data or b"")
            return
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

    # --- Dirty rect tracking ---
    # Automatically tracks the bounding box of all draw operations.
    # Call show_dirty() instead of show() to push only the changed region.

    def mark_dirty(self, x, y, w, h):
        """Expand the dirty bounding box to include (x, y, w, h)."""
        x1 = x + w
        y1 = y + h
        if self._drect is None:
            self._drect = [x, y, x1, y1]
        else:
            d = self._drect
            if x < d[0]:
                d[0] = x
            if y < d[1]:
                d[1] = y
            if x1 > d[2]:
                d[2] = x1
            if y1 > d[3]:
                d[3] = y1

    def reset_dirty(self):
        """Clear the dirty rect. Call after show/show_dirty."""
        self._drect = None

    @property
    def dirty_rect(self):
        """Return (x, y, w, h) of dirty region, or None if clean."""
        d = self._drect
        if d is None:
            return None
        return (d[0], d[1], d[2] - d[0], d[3] - d[1])

    def show_dirty(self):
        """Push only the dirty region to the display, then reset.

        Falls back to show() if the dirty region is large or covers
        the full screen. If nothing is dirty, does nothing.
        """
        if self._drect is None:
            return
        d = self._drect
        self._drect = None
        x, y = d[0], d[1]
        w, h = d[2] - x, d[3] - y
        # Clamp
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
        # Full screen? Use show() for efficiency (single contiguous write)
        if w >= self.width and h >= self.height:
            self.show()
            return
        self.show_rect(x, y, w, h)

    # --- Draw method overrides for dirty tracking ---

    def fill(self, color):
        """Fill entire screen and mark fully dirty."""
        super().fill(color)
        self._drect = [0, 0, self.width, self.height]

    def fill_rect(self, x, y, w, h, color):
        super().fill_rect(x, y, w, h, color)
        self.mark_dirty(x, y, w, h)

    def rect(self, x, y, w, h, color):
        super().rect(x, y, w, h, color)
        self.mark_dirty(x, y, w, h)

    def pixel(self, x, y, color):
        super().pixel(x, y, color)
        self.mark_dirty(x, y, 1, 1)

    def hline(self, x, y, w, color):
        super().hline(x, y, w, color)
        self.mark_dirty(x, y, w, 1)

    def vline(self, x, y, h, color):
        super().vline(x, y, h, color)
        self.mark_dirty(x, y, 1, h)

    def line(self, x0, y0, x1, y1, color):
        super().line(x0, y0, x1, y1, color)
        lx = min(x0, x1)
        ly = min(y0, y1)
        self.mark_dirty(lx, ly, abs(x1 - x0) + 1, abs(y1 - y0) + 1)

    def text(self, text, x, y, color=0xFFFF):
        """Draw text with extended glyph support (å ä ö Å Ä Ö)."""
        # Track dirty for all text regardless of glyph path
        self.mark_dirty(x, y, len(text) * 8, 8)
        if not _EXT_GLYPHS:
            super().text(text, x, y, color)
            return
        cx = x
        ascii_start = cx
        ascii_buf = []
        for ch in text:
            glyph = _EXT_GLYPHS.get(ch)
            if glyph:
                if ascii_buf:
                    super().text("".join(ascii_buf), ascii_start, y, color)
                    ascii_buf = []
                # Render into tiny framebuf and blit — one call instead of
                # up to 64 pixel() calls with mark_dirty() each.
                _glyph_fb.fill(0)
                for row in range(8):
                    byte = glyph[row]
                    if byte == 0:
                        continue
                    for col in range(8):
                        if byte & (0x80 >> col):
                            _glyph_fb.pixel(col, row, color)
                super().blit(_glyph_fb, cx, y, 0)
                self.mark_dirty(cx, y, 8, 8)
                cx += 8
                ascii_start = cx
            else:
                ascii_buf.append(ch)
                cx += 8
        if ascii_buf:
            super().text("".join(ascii_buf), ascii_start, y, color)

    def busy(self):
        """True if a DMA transfer is in progress (native mode only)."""
        if self._native:
            return _spidma.busy(self._slot)
        return False

    def wait(self):
        """Block until any in-progress DMA transfer completes."""
        if self._native:
            _spidma.wait(self._slot)

    def show(self):
        """Push the framebuffer to the display."""
        if self._native:
            _spidma.push(self._slot, self._buf)
            return
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

        Coordinates are in logical (post-rotation) framebuffer space.
        With DMA, partial pushes are always more efficient than full-screen
        since they transfer fewer bytes through the same pipeline.
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
        if self._native:
            _spidma.push_rect(self._slot, self._buf, x, y, w, h)
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
