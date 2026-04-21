# bodn/neo.py — NeoPixel pattern engine wrapper
#
# Wraps the _neopixel C module with a convenience API.
#
# Usage:
#   from bodn.neo import neo
#   neo.init()
#   neo.zone_pattern(neo.ZONE_LID_RING, neo.PAT_RAINBOW, speed=3, brightness=32)

from bodn import config

try:
    import _neopixel
except ImportError:
    _neopixel = None


def _cap(brightness):
    """Clamp a pattern brightness to config.NEOPIXEL_MAX_BRIGHTNESS."""
    m = config.NEOPIXEL_MAX_BRIGHTNESS
    return brightness if brightness <= m else m


def _scale_rgb(r, g, b):
    """Scale per-pixel RGB to honour NEOPIXEL_MAX_BRIGHTNESS."""
    m = config.NEOPIXEL_MAX_BRIGHTNESS
    if m >= 255:
        return r, g, b
    return (r * m) // 255, (g * m) // 255, (b * m) // 255


def _scale_bytes(data):
    """Scale an r,g,b,r,g,b,... buffer by NEOPIXEL_MAX_BRIGHTNESS."""
    m = config.NEOPIXEL_MAX_BRIGHTNESS
    if m >= 255:
        return data
    return bytes((b * m) // 255 for b in data)


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
    def active(self):
        """True if init() has been called and the engine is running."""
        return self._active

    def init(self, pin=None):
        """Start the C pattern engine.  Call once at boot."""
        if _neopixel is None:
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
        kw = {"speed": speed, "brightness": _cap(brightness), "hue_offset": hue_offset}
        if colour is not None:
            kw["colour"] = colour
        _neopixel.zone_pattern(zone, pattern, **kw)

    def zone_off(self, zone):
        if self._active:
            _neopixel.zone_off(zone)

    def zone_brightness(self, zone, brightness):
        if self._active:
            _neopixel.zone_brightness(zone, _cap(brightness))

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
            r, g, b = _scale_rgb(r, g, b)
            _neopixel.set_pixel(index, r, g, b)

    def set_pixels(self, start, data):
        """Bulk set pixels from bytes(r,g,b,r,g,b,...)."""
        if self._active:
            _neopixel.set_pixels(start, _scale_bytes(data))

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
            r, g, b = _scale_rgb(r, g, b)
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
