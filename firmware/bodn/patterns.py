# bodn/patterns.py — shared LED buffer and helpers
#
# LED zones (defined in config.py):
#   Stick A  — indices 0..7    (8 LEDs)
#   Stick B  — indices 8..15   (8 LEDs)
#   Lid Ring — indices 16..107 (92 LEDs, 144 LED/m strip around lid)
#
# Pattern generators (rainbow/pulse/chase/sparkle/bounce/wave/split/fill) now
# live in the native _neopixel C module (see cmodules/neopixel/patterns.c).
# Drive them from Python via `from bodn.neo import neo; neo.zone_pattern(...)`.
#
# What remains here is only what game-rule modules still need to compose their
# own per-frame LED state in Python: the shared scratch buffer, the brightness
# scaler, and LED-count constants.

from micropython import const

N_LEDS = const(108)  # config.NEOPIXEL_COUNT
N_STICKS = const(16)  # config.LED_STICKS[1]

# Pre-allocated LED buffer — reused by game rules to avoid creating a new list
# every frame.  Callers must treat the returned list as read-only (or copy it)
# since the next call will overwrite it.
_led_buf = [(0, 0, 0)] * N_LEDS
_BLACK = (0, 0, 0)

# Human-readable names for the C engine's PAT_* ids, in the same order as
# _PAT_MAP in bodn/ui/demo.py.  Kept here so the demo UI can show a label
# without pulling a string table out of C.
PATTERN_NAMES = [
    "Rainbow",
    "Pulse",
    "Chase",
    "Sparkle",
    "Bounce",
    "Wave",
    "Split",
    "Fill",
]


def scale(rgb, bright):
    """Scale an RGB tuple by brightness (0-255)."""
    return ((rgb[0] * bright) >> 8, (rgb[1] * bright) >> 8, (rgb[2] * bright) >> 8)
