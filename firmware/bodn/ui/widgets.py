# bodn/ui/widgets.py — stateless draw helper functions


import framebuf
from bodn.ui.font_ext import GLYPHS as _EXT_GLYPHS

# Pre-allocated buffer for scaled text rendering (8×8 RGB565 = 128 bytes)
_char_buf = bytearray(8 * 8 * 2)
_char_fb = framebuf.FrameBuffer(_char_buf, 8, 8, framebuf.RGB565)


# ── Sprite support ──────────────────────────────────────────────
# Pre-render scaled icons/text into a FrameBuffer once, then blit
# each frame. One blit() call replaces hundreds of fill_rect() calls.
#
# Usage:
#   # In enter() — render once:
#   sprite = make_icon_sprite(MODE_ICONS["chord"], 16, 16, theme.CYAN, scale=4)
#   label  = make_label_sprite("CHORD", theme.CYAN, scale=2)
#
#   # In render() — blit per frame (fast, single call):
#   blit_sprite(tft, sprite, x, y)

# Transparent key colour — must not appear in actual content.
# 0x0000 (black) doesn't work as transparent since we draw on black bg.
# Use a distinctive magenta (R=31, G=0, B=31 in RGB565 byte-swapped).
_TRANSPARENT = 0x1FF8


def make_icon_sprite(data, w, h, color, scale=1):
    """Pre-render a 1-bit bitmap at the given scale into a FrameBuffer.

    Returns (framebuf, pixel_width, pixel_height).
    """
    pw = w * scale
    ph = h * scale
    buf = bytearray(pw * ph * 2)
    fb = framebuf.FrameBuffer(buf, pw, ph, framebuf.RGB565)
    fb.fill(_TRANSPARENT)

    byte_idx = 0
    bit_idx = 7
    for row in range(h):
        for col in range(w):
            if data[byte_idx] & (1 << bit_idx):
                if scale <= 1:
                    fb.pixel(col, row, color)
                else:
                    fb.fill_rect(col * scale, row * scale, scale, scale, color)
            bit_idx -= 1
            if bit_idx < 0:
                bit_idx = 7
                byte_idx += 1

    return (fb, pw, ph)


def make_label_sprite(text, color, scale=1):
    """Pre-render scaled text into a FrameBuffer.

    Returns (framebuf, pixel_width, pixel_height).
    """
    char_w = 8 * scale
    pw = len(text) * char_w
    ph = 8 * scale
    buf = bytearray(pw * ph * 2)
    fb = framebuf.FrameBuffer(buf, pw, ph, framebuf.RGB565)
    fb.fill(_TRANSPARENT)

    cx = 0
    for ch in text:
        glyph = _EXT_GLYPHS.get(ch)
        if glyph:
            for row in range(8):
                byte = glyph[row]
                if byte == 0:
                    continue
                for col in range(8):
                    if byte & (0x80 >> col):
                        if scale <= 1:
                            fb.pixel(cx + col, row, color)
                        else:
                            fb.fill_rect(
                                cx + col * scale, row * scale, scale, scale, color
                            )
        else:
            # Render via temp buffer + pixel read-back
            _char_fb.fill(0)
            _char_fb.text(ch, 0, 0, 0xFFFF)
            for py in range(8):
                for px in range(8):
                    if _char_fb.pixel(px, py) != 0:
                        if scale <= 1:
                            fb.pixel(cx + px, py, color)
                        else:
                            fb.fill_rect(
                                cx + px * scale, py * scale, scale, scale, color
                            )
        cx += char_w

    return (fb, pw, ph)


def blit_sprite(tft, sprite, x, y):
    """Blit a pre-rendered sprite onto the display framebuffer.

    sprite: (framebuf, width, height) tuple from make_*_sprite().
    Transparent pixels (_TRANSPARENT colour) are skipped.
    """
    fb, pw, ph = sprite
    tft.blit(fb, x, y, _TRANSPARENT)
    tft.mark_dirty(x, y, pw, ph)


# ── Emoji sprite loading (OpenMoji BDF from SD) ──────────────────
# Pre-converted BDF sprites with full RGB565+alpha, rendered via the
# native _draw module. Falls back gracefully if _draw or SD not available.

_emoji_cache = {}


def load_emoji(name, size=48):
    """Load an OpenMoji BDF sprite from the SD card.

    Returns (asset_handle, width, height) or None if not available.
    Results (including None) are cached to avoid repeated file I/O.
    """
    key = (name, size)
    if key in _emoji_cache:
        return _emoji_cache[key]

    result = None
    try:
        from bodn.ui.draw import load, info
        from bodn.assets import resolve

        path = resolve("/sprites/emoji_{}_{}.bdf".format(name, size))
        with open(path, "rb") as f:
            data = f.read()
        asset = load(data)
        if asset is not None:
            meta = info(asset)
            if meta is not None:
                result = (asset, meta["max_width"], meta["height"])
    except (OSError, ImportError):
        pass

    _emoji_cache[key] = result
    return result


_emoji_sprite_cache = {}

# Background pad colour for emoji (light grey-blue, byte-swapped RGB565)
_EMOJI_PAD_COLOR = 0xEF7D


def make_emoji_sprite(name, size=48, pad=4):
    """Pre-render an OpenMoji emoji into a FrameBuffer sprite with background pad.

    Returns (framebuf, width, height) tuple like make_icon_sprite(),
    or None if the emoji is not available.
    Results are cached.
    """
    key = (name, size, pad)
    if key in _emoji_sprite_cache:
        return _emoji_sprite_cache[key]

    emoji = load_emoji(name, size)
    if emoji is None:
        _emoji_sprite_cache[key] = None
        return None

    asset, ew, eh = emoji
    try:
        import _draw

        pw = ew + pad * 2
        ph = eh + pad * 2
        buf = bytearray(pw * ph * 2)
        fb = framebuf.FrameBuffer(buf, pw, ph, framebuf.RGB565)
        # Fill with background pad colour
        fb.fill(_EMOJI_PAD_COLOR)
        # Render emoji into the padded framebuffer via the C draw module
        _draw.sprite(buf, pw, pad, pad, asset, 0, 0xFFFF)
        result = (fb, pw, ph)
    except (ImportError, Exception):
        result = None

    _emoji_sprite_cache[key] = result
    return result


def blit_centered(tft, sprite, y, w):
    """Blit a sprite horizontally centered within width w."""
    _, pw, _ = sprite
    blit_sprite(tft, sprite, (w - pw) // 2, y)


def _draw_ext_char(tft, glyph, x, y, color, scale):
    """Draw an 8×8 extended glyph (bytes, 1bpp row-major, MSB-first)."""
    for row in range(8):
        byte = glyph[row]
        if byte == 0:
            continue
        for col in range(8):
            if byte & (0x80 >> col):
                if scale <= 1:
                    tft.pixel(x + col, y + row, color)
                else:
                    tft.fill_rect(x + col * scale, y + row * scale, scale, scale, color)


def draw_label(tft, text, x, y, color, scale=1):
    """Draw text at (x, y). scale=1 uses built-in font, scale>1 enlarges.

    Supports Swedish characters (å ä ö Å Ä Ö) via extended font glyphs.
    """
    if scale <= 1:
        # Fast path: render ASCII spans with built-in font, extended chars individually
        cx = x
        ascii_start = cx
        ascii_buf = []
        for ch in text:
            glyph = _EXT_GLYPHS.get(ch)
            if glyph:
                # Flush any pending ASCII characters
                if ascii_buf:
                    tft.text("".join(ascii_buf), ascii_start, y, color)
                    ascii_buf = []
                _draw_ext_char(tft, glyph, cx, y, color, 1)
                cx += 8
                ascii_start = cx
            else:
                ascii_buf.append(ch)
                cx += 8
        if ascii_buf:
            tft.text("".join(ascii_buf), ascii_start, y, color)
        return

    # Scale > 1: draw each character enlarged via fill_rect per pixel.
    # MicroPython framebuf font is 8×8.  We render into a tiny 1-char
    # buffer and read pixels back to scale them up.
    cx = x
    for ch in text:
        glyph = _EXT_GLYPHS.get(ch)
        if glyph:
            _draw_ext_char(tft, glyph, cx, y, color, scale)
        else:
            _char_fb.fill(0)
            _char_fb.text(ch, 0, 0, 0xFFFF)
            for py in range(8):
                for px in range(8):
                    if _char_fb.pixel(px, py) != 0:
                        tft.fill_rect(
                            cx + px * scale, y + py * scale, scale, scale, color
                        )
        cx += 8 * scale


def draw_centered(tft, text, y, color, w, scale=1):
    """Draw text horizontally centered within width w."""
    char_w = 8 * scale
    text_w = len(text) * char_w
    x = (w - text_w) // 2
    draw_label(tft, text, x, y, color, scale)


def draw_progress_bar(tft, x, y, w, h, value, max_val, fg, bg, border=None):
    """Draw a horizontal progress bar."""
    if border is not None:
        tft.rect(x, y, w, h, border)
    fill_w = 0
    if max_val > 0:
        fill_w = max(0, min(w, w * value // max_val))
    if fill_w > 0:
        tft.fill_rect(x, y, fill_w, h, fg)
    unfill_w = w - fill_w
    if unfill_w > 0:
        tft.fill_rect(x + fill_w, y, unfill_w, h, bg)


def draw_button_grid(tft, theme, names, held, cols=4, x0=0, y0=0, cell_w=32, cell_h=16):
    """Draw button indicators in a grid layout."""
    n = min(len(names), len(held))
    for i in range(n):
        col = i % cols
        row = i // cols
        x = x0 + col * cell_w
        y = y0 + row * cell_h
        bw = cell_w - 4
        bh = cell_h - 4
        if held[i]:
            tft.fill_rect(x, y, bw, bh, theme.BTN_565[i])
            tft.text(names[i], x + 2, y + 2, theme.BLACK)
        else:
            tft.fill_rect(x, y, bw, bh, theme.BLACK)
            tft.rect(x, y, bw, bh, theme.BTN_565[i])


def draw_status_bar(tft, theme, y, left, right=None, color=None):
    """Draw a single-line status bar with left and optional right text."""
    c = color or theme.WHITE
    tft.text(left, 0, y, c)
    if right:
        x = theme.width - len(right) * 8
        tft.text(right, x, y, c)


def draw_hold_bar(tft, theme, progress, w):
    """Draw a thin hold-to-pause progress bar at the top of the screen.

    progress: 0.0 to 1.0. Only draws when progress > 0.
    """
    if progress <= 0:
        return
    bar_h = 4
    fill_w = max(1, int(w * progress))
    # Gradient from cyan to white as it fills
    tft.fill_rect(0, 0, fill_w, bar_h, theme.CYAN)
    if progress >= 1.0:
        tft.fill_rect(0, 0, w, bar_h, theme.WHITE)


def draw_battery_icon(tft, x, y, w, h, percent, fg, bg, border):
    """Draw a battery icon (w×h px) at (x, y) filled to percent (0–100).

    Layout: main body (w-2 wide) + a 2-px terminal nub on the right.
    """
    nub_h = max(2, h // 2)
    nub_y = y + (h - nub_h) // 2
    body_w = w - 2

    # Terminal nub
    tft.fill_rect(x + body_w, nub_y, 2, nub_h, border)

    # Body outline
    tft.rect(x, y, body_w, h, border)

    # Fill interior
    inner_w = body_w - 4
    fill_w = max(0, inner_w * percent // 100)
    if fill_w > 0:
        tft.fill_rect(x + 2, y + 2, fill_w, h - 4, fg)
    unfill_w = inner_w - fill_w
    if unfill_w > 0:
        tft.fill_rect(x + 2 + fill_w, y + 2, unfill_w, h - 4, bg)


def draw_icon(tft, data, x, y, w, h, color, scale=1):
    """Draw a 1-bit bitmap (row-major, MSB-first)."""
    byte_idx = 0
    bit_idx = 7
    for row in range(h):
        for col in range(w):
            if data[byte_idx] & (1 << bit_idx):
                if scale <= 1:
                    tft.pixel(x + col, y + row, color)
                else:
                    tft.fill_rect(
                        x + col * scale,
                        y + row * scale,
                        scale,
                        scale,
                        color,
                    )
            bit_idx -= 1
            if bit_idx < 0:
                bit_idx = 7
                byte_idx += 1
