# bodn/patterns.py — LED animation patterns (extracted from main.py)
#
# LED zones (defined in config.py):
#   Stick A  — indices 0..7    (8 LEDs)
#   Stick B  — indices 8..15   (8 LEDs)
#   Lid Ring — indices 16..107 (92 LEDs, 144 LED/m strip around lid)
#
# Full-strip pattern functions (pattern_*) write the whole _led_buf.
# Zone-aware helpers (zone_fill, zone_pattern) operate on a (start, count) slice.

from bodn import config

N_LEDS = config.NEOPIXEL_COUNT
N_STICKS = config.LED_STICKS[1]  # 16 — total LEDs in both sticks

# Zone constants re-exported for convenience
ZONE_STICK_A = config.LED_STICK_A
ZONE_STICK_B = config.LED_STICK_B
ZONE_STICKS = config.LED_STICKS
ZONE_LID_RING = config.LED_LID_RING

# Pre-allocated LED buffer — reused by all pattern functions to avoid
# creating a new list every frame.  Callers must treat the returned list
# as read-only (or copy it) since the next call will overwrite it.
_led_buf = [(0, 0, 0)] * N_LEDS
_BLACK = (0, 0, 0)


def hsv_to_rgb(h, s, v):
    """Convert HSV (0-255 each) to RGB tuple."""
    if s == 0:
        return (v, v, v)
    region = (h * 6) >> 8
    remainder = (h * 6) - (region << 8)
    p = (v * (255 - s)) >> 8
    q = (v * (255 - ((s * remainder) >> 8))) >> 8
    t = (v * (255 - ((s * (255 - remainder)) >> 8))) >> 8
    if region == 0:
        return (v, t, p)
    if region == 1:
        return (q, v, p)
    if region == 2:
        return (p, v, t)
    if region == 3:
        return (p, q, v)
    if region == 4:
        return (t, p, v)
    return (v, p, q)


def scale(rgb, bright):
    """Scale an RGB tuple by brightness (0-255)."""
    return ((rgb[0] * bright) >> 8, (rgb[1] * bright) >> 8, (rgb[2] * bright) >> 8)


def pattern_rainbow(frame, speed, hue_off, bright):
    """Smooth rainbow flowing across the strip."""
    for i in range(N_LEDS):
        h = (hue_off + i * 255 // N_LEDS + frame * speed) & 0xFF
        _led_buf[i] = scale(hsv_to_rgb(h, 255, 255), bright)
    return _led_buf


def pattern_pulse(frame, speed, colour, bright):
    """All LEDs pulse together in one colour."""
    phase = (frame * speed) & 0xFF
    v = phase if phase < 128 else 255 - phase
    v = (v * bright) >> 7
    c = scale(colour, v)
    for i in range(N_LEDS):
        _led_buf[i] = c
    return _led_buf


def pattern_chase(frame, speed, colour, bright):
    """A bright dot chases around the strip, leaving a fading tail."""
    pos = (frame * speed // 2) % N_LEDS
    for i in range(N_LEDS):
        dist = (pos - i) % N_LEDS
        if dist == 0:
            _led_buf[i] = scale(colour, bright)
        elif dist < 4:
            _led_buf[i] = scale(colour, bright >> dist)
        else:
            _led_buf[i] = _BLACK
    return _led_buf


def pattern_sparkle(frame, speed, colour, bright):
    """Random-ish sparkle — deterministic from frame number."""
    for i in range(N_LEDS):
        v = ((frame * speed * 7 + i * 53) * 131) & 0xFF
        if v > 200:
            _led_buf[i] = scale(colour, bright)
        else:
            _led_buf[i] = _BLACK
    return _led_buf


def pattern_bounce(frame, speed, colour, bright):
    """A dot bounces back and forth."""
    cycle = (N_LEDS - 1) * 2
    pos = (frame * speed // 2) % cycle
    if pos >= N_LEDS:
        pos = cycle - pos
    for i in range(N_LEDS):
        dist = abs(i - pos)
        if dist == 0:
            _led_buf[i] = scale(colour, bright)
        elif dist == 1:
            _led_buf[i] = scale(colour, bright >> 1)
        else:
            _led_buf[i] = _BLACK
    return _led_buf


def pattern_wave(frame, speed, colour, bright):
    """Sine-like wave of brightness across the strip."""
    for i in range(N_LEDS):
        phase = (i * 255 // N_LEDS + frame * speed) & 0xFF
        v = phase if phase < 128 else 255 - phase
        v = (v * bright) >> 7
        _led_buf[i] = scale(colour, v)
    return _led_buf


def pattern_split(frame, speed, colour, bright):
    """Two dots start from center and expand outward, then collapse."""
    for i in range(N_LEDS):
        _led_buf[i] = _BLACK
    mid = N_LEDS // 2
    cycle = mid + 1
    pos = (frame * speed // 2) % (cycle * 2)
    if pos >= cycle:
        pos = cycle * 2 - pos - 1
    for offset in range(min(pos + 1, mid + 1)):
        v = bright if offset == pos else bright >> 2
        a = mid + offset
        b = mid - offset
        if 0 <= a < N_LEDS:
            _led_buf[a] = scale(colour, v)
        if 0 <= b < N_LEDS:
            _led_buf[b] = scale(colour, v)
    return _led_buf


def pattern_fill(frame, speed, colour, bright):
    """LEDs fill up one by one, then empty."""
    cycle = N_LEDS * 2
    pos = (frame * speed // 2) % cycle
    fill = pos if pos < N_LEDS else cycle - pos
    for i in range(N_LEDS):
        if i < fill:
            _led_buf[i] = scale(colour, bright)
        else:
            _led_buf[i] = _BLACK
    return _led_buf


# --- Zone-aware helpers ---


def zone_fill(zone, colour):
    """Fill a zone with a solid colour. zone = (start, count)."""
    start, count = zone
    for i in range(start, start + count):
        _led_buf[i] = colour


def zone_clear(zone):
    """Clear a zone to black. zone = (start, count)."""
    zone_fill(zone, _BLACK)


def zone_rainbow(zone, frame, speed, hue_off, bright):
    """Rainbow pattern within a zone."""
    start, count = zone
    for i in range(count):
        h = (hue_off + i * 255 // count + frame * speed) & 0xFF
        _led_buf[start + i] = scale(hsv_to_rgb(h, 255, 255), bright)


def zone_pulse(zone, frame, speed, colour, bright):
    """Pulse pattern within a zone."""
    phase = (frame * speed) & 0xFF
    v = phase if phase < 128 else 255 - phase
    v = (v * bright) >> 7
    c = scale(colour, v)
    start, count = zone
    for i in range(start, start + count):
        _led_buf[i] = c


def zone_chase(zone, frame, speed, colour, bright):
    """Chase pattern within a zone."""
    start, count = zone
    pos = (frame * speed // 2) % count
    for i in range(count):
        dist = (pos - i) % count
        if dist == 0:
            _led_buf[start + i] = scale(colour, bright)
        elif dist < 4:
            _led_buf[start + i] = scale(colour, bright >> dist)
        else:
            _led_buf[start + i] = _BLACK


PATTERNS = [
    ("Rainbow", pattern_rainbow),
    ("Pulse", pattern_pulse),
    ("Chase", pattern_chase),
    ("Sparkle", pattern_sparkle),
    ("Bounce", pattern_bounce),
    ("Wave", pattern_wave),
    ("Split", pattern_split),
    ("Fill", pattern_fill),
]

PATTERN_NAMES = [name for name, _ in PATTERNS]
