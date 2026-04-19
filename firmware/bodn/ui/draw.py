# bodn/ui/draw.py — thin wrapper around _draw C module
#
# Provides text(), text_width(), sprite(), and load() with automatic
# fallback to existing Python rendering when the C module isn't available
# (e.g. running on stock MicroPython without custom firmware).

try:
    import _draw

    _HAS_NATIVE = True
except ImportError:
    _draw = None
    _HAS_NATIVE = False

_builtin_font = None


def get_builtin_font():
    """Return the built-in 8x8 font asset handle (or None)."""
    global _builtin_font
    if _builtin_font is None and _HAS_NATIVE:
        _builtin_font = _draw.BUILTIN_8X8
    return _builtin_font


def load(data_bytes):
    """Load an asset from binary data.  Returns an opaque handle."""
    if _HAS_NATIVE:
        return _draw.load(data_bytes)
    return None


def text(tft, x, y, string, color, asset=None, bg=None):
    """Draw text into tft's framebuffer.

    Uses the fast C path when available, otherwise falls back to
    the existing Python draw_label() from widgets.py.
    """
    if asset is None:
        asset = get_builtin_font()

    if _HAS_NATIVE and asset is not None:
        bbox = _draw.text(tft._buf, tft.width, x, y, string, asset, color, bg)
        if bbox[2] > 0 and bbox[3] > 0:
            tft.mark_dirty(*bbox)
        return

    # Fallback: existing Python path
    from bodn.ui.widgets import draw_label

    draw_label(tft, string, x, y, color)


def text_width(string, asset=None):
    """Measure text width in pixels without drawing."""
    if asset is None:
        asset = get_builtin_font()
    if _HAS_NATIVE and asset is not None:
        return _draw.text_width(string, asset)
    return len(string) * 8


def sprite(tft, x, y, asset, frame_id, color):
    """Draw a sprite frame from an asset into tft's framebuffer."""
    if _HAS_NATIVE and asset is not None:
        bbox = _draw.sprite(tft._buf, tft.width, x, y, asset, frame_id, color)
        if bbox[2] > 0 and bbox[3] > 0:
            tft.mark_dirty(*bbox)


def info(asset):
    """Return asset metadata dict, or None."""
    if _HAS_NATIVE and asset is not None:
        return _draw.info(asset)
    return None


def waveform(tft, x, y, w, h, samples, fg, bg, gain_q8=256):
    """Render a scope-style waveform from int16 PCM samples.

    `samples` is a bytes-like object of int16 little-endian samples.  The
    entire buffer is stretched across `w` pixels.  `gain_q8` is an 8.8
    fixed-point amplitude multiplier (256 = unity).  Falls back to a flat
    centre-line when _draw isn't available.
    """
    if _HAS_NATIVE:
        bbox = _draw.waveform(tft._buf, tft.width, x, y, w, h, samples, fg, bg, gain_q8)
        if bbox[2] > 0 and bbox[3] > 0:
            tft.mark_dirty(*bbox)
        return
    # Fallback: flat line
    tft.fill_rect(x, y, w, h, bg)
    tft.hline(x, y + h // 2, w, fg)
