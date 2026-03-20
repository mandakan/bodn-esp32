# bodn/ui/widgets.py — stateless draw helper functions


import framebuf

# Pre-allocated buffer for scaled text rendering (8×8 RGB565 = 128 bytes)
_char_buf = bytearray(8 * 8 * 2)
_char_fb = framebuf.FrameBuffer(_char_buf, 8, 8, framebuf.RGB565)


def draw_label(tft, text, x, y, color, scale=1):
    """Draw text at (x, y). scale=1 uses built-in font, scale>1 enlarges."""
    if scale <= 1:
        tft.text(text, x, y, color)
        return
    # Scale > 1: draw each character enlarged via fill_rect per pixel.
    # MicroPython framebuf font is 8×8.  We render into a tiny 1-char
    # buffer and read pixels back to scale them up.
    cx = x
    for ch in text:
        _char_fb.fill(0)
        _char_fb.text(ch, 0, 0, 0xFFFF)
        for py in range(8):
            for px in range(8):
                if _char_fb.pixel(px, py) != 0:
                    tft.fill_rect(cx + px * scale, y + py * scale, scale, scale, color)
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


def draw_button_grid(tft, theme, names, held, cols=4, x0=0, y0=0, cell_w=32, cell_h=16):
    """Draw button indicators in a grid layout."""
    for i in range(len(names)):
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
