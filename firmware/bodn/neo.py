# bodn/neo.py — NeoPixel pattern engine wrapper
#
# Wraps the _neopixel C module with a convenience API.  If the C module
# is not available (stock MicroPython firmware), the module provides a
# minimal stub that returns False for `available`, letting callers
# fall back to the legacy Python NeoPixel path.
#
# Usage:
#   from bodn.neo import neo
#   if neo.available:
#       neo.init()
#       neo.zone_pattern(neo.ZONE_LID_RING, neo.PAT_RAINBOW, speed=3, brightness=32)

from bodn import config

try:
    import _neopixel

    _HAS_NATIVE = True
except ImportError:
    _HAS_NATIVE = False


class NeoEngine:
    """Convenience wrapper around _neopixel C module."""

    # Zone constants
    ZONE_STICK_A = 0
    ZONE_STICK_B = 1
    ZONE_LID_RING = 2

    # Pattern constants
    PAT_OFF = 0
    PAT_SOLID = 1
    PAT_RAINBOW = 2
    PAT_PULSE = 3
    PAT_CHASE = 4
    PAT_SPARKLE = 5
    PAT_BOUNCE = 6
    PAT_WAVE = 7
    PAT_SPLIT = 8
    PAT_FILL = 9

    # Override constants
    OVERRIDE_NONE = 0
    OVERRIDE_BLACK = 1
    OVERRIDE_SOLID = 2
    OVERRIDE_PULSE = 3
    OVERRIDE_FADE = 4

    def __init__(self):
        self._active = False

    @property
    def available(self):
        """True if the C engine is compiled into the firmware."""
        return _HAS_NATIVE

    @property
    def active(self):
        """True if init() has been called and the engine is running."""
        return self._active

    def init(self, pin=None):
        """Start the C pattern engine.  Call once at boot."""
        if not _HAS_NATIVE:
            return
        if pin is None:
            pin = config.NEOPIXEL_PIN
        _neopixel.init(pin=pin)
        self._active = True

    def deinit(self):
        """Stop the engine and release the RMT channel."""
        if self._active:
            _neopixel.deinit()
            self._active = False

    # --- Zone patterns ---

    def zone_pattern(
        self, zone, pattern, speed=3, colour=None, brightness=None, hue_offset=0
    ):
        """Set a zone's background pattern.

        brightness defaults to the config value for the zone if not given.
        """
        if not self._active:
            return
        if brightness is None:
            if zone == self.ZONE_LID_RING:
                brightness = config.NEOPIXEL_LID_BRIGHTNESS
            else:
                brightness = config.NEOPIXEL_BRIGHTNESS
        kw = {"speed": speed, "brightness": brightness, "hue_offset": hue_offset}
        if colour is not None:
            kw["colour"] = colour
        _neopixel.zone_pattern(zone, pattern, **kw)

    def zone_off(self, zone):
        if self._active:
            _neopixel.zone_off(zone)

    def zone_brightness(self, zone, brightness):
        if self._active:
            _neopixel.zone_brightness(zone, brightness)

    def all_off(self):
        """Turn off all zones."""
        if not self._active:
            return
        for z in range(3):
            _neopixel.zone_off(z)

    def sticks_pattern(self, pattern, **kw):
        """Set the same pattern on both stick zones."""
        self.zone_pattern(self.ZONE_STICK_A, pattern, **kw)
        self.zone_pattern(self.ZONE_STICK_B, pattern, **kw)

    def all_pattern(self, pattern, **kw):
        """Set the same pattern on all zones (sticks use config brightness)."""
        self.zone_pattern(self.ZONE_STICK_A, pattern, **kw)
        self.zone_pattern(self.ZONE_STICK_B, pattern, **kw)
        self.zone_pattern(self.ZONE_LID_RING, pattern, **kw)

    # --- Per-pixel overrides ---

    def set_pixel(self, index, r, g, b):
        if self._active:
            _neopixel.set_pixel(index, r, g, b)

    def set_pixels(self, start, data):
        """Bulk set pixels from bytes(r,g,b,r,g,b,...)."""
        if self._active:
            _neopixel.set_pixels(start, data)

    def clear_pixel(self, index):
        if self._active:
            _neopixel.clear_pixel(index)

    def clear_pixels(self, start, count):
        if self._active:
            _neopixel.clear_pixels(start, count)

    def clear_all_overrides(self):
        if self._active:
            _neopixel.clear_all_overrides()

    # --- Session overrides ---

    def set_override(self, mode, r=0, g=0, b=0):
        if self._active:
            _neopixel.set_override(mode, r=r, g=g, b=b)

    def clear_override(self):
        if self._active:
            _neopixel.clear_override()

    # --- Control ---

    def pause(self):
        if self._active:
            _neopixel.pause()

    def resume(self):
        if self._active:
            _neopixel.resume()

    # --- Query ---

    def frame(self):
        if self._active:
            return _neopixel.frame()
        return 0

    def stats(self):
        if self._active:
            return _neopixel.stats()
        return {}


# Module-level singleton
neo = NeoEngine()
