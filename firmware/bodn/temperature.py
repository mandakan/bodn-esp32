# bodn/temperature.py — DS18B20 1-Wire temperature monitoring
#
# Two DS18B20 sensors on a single 1-Wire bus (GPIO 20):
#   - Battery sensor: thermal-taped to the LiPo pouch
#   - Enclosure sensor: inside the box near electronics
#
# Sensors are identified by their ROM address after first scan.
# Conversion takes ~750 ms at 12-bit resolution; we poll every 30 s
# and cache the results to avoid blocking the main loop.

import time
from micropython import const
from machine import Pin
import onewire
import ds18x20
from bodn import config

_CACHE_MS = const(30_000)  # re-read at most every 30 s
_CONV_MS = const(750)  # 12-bit conversion time

_ds = None
_roms = []
_temps = {}  # rom → temperature (°C) as float, or None if read failed
_next_read_ms = 0
_conv_pending = False
_conv_start_ms = 0


def _init():
    global _ds, _roms
    if _ds is None:
        pin = Pin(config.ONEWIRE_PIN, Pin.IN)
        _ds = ds18x20.DS18X20(onewire.OneWire(pin))
        _roms = _ds.scan()


def scan():
    """Scan the bus and return the number of sensors found."""
    _init()
    global _roms
    _roms = _ds.scan()
    return len(_roms)


def sensor_count():
    """Return number of sensors discovered on last scan."""
    return len(_roms)


def read():
    """Return dict of {index: temp_c} for all sensors.

    Index 0 is the first sensor found, 1 the second, etc.
    Values are float °C or None if the sensor failed to read.
    Results are cached for 30 s.
    """
    global _next_read_ms, _conv_pending, _conv_start_ms

    now = time.ticks_ms()

    # Return cached results if fresh
    if time.ticks_diff(now, _next_read_ms) < 0 and not _conv_pending:
        return {i: _temps.get(rom) for i, rom in enumerate(_roms)}

    _init()

    if not _roms:
        return {}

    # Start conversion if not already pending
    if not _conv_pending:
        _ds.convert_temp()
        _conv_pending = True
        _conv_start_ms = now
        # Return stale data while conversion runs
        return {i: _temps.get(rom) for i, rom in enumerate(_roms)}

    # Check if conversion is done
    if time.ticks_diff(now, _conv_start_ms) < _CONV_MS:
        # Still converting — return stale data
        return {i: _temps.get(rom) for i, rom in enumerate(_roms)}

    # Read results
    _conv_pending = False
    for rom in _roms:
        try:
            _temps[rom] = _ds.read_temp(rom)
        except Exception:
            _temps[rom] = None

    _next_read_ms = time.ticks_add(now, _CACHE_MS)
    return {i: _temps.get(rom) for i, rom in enumerate(_roms)}


def max_temp():
    """Return the highest temperature across all sensors, or None."""
    temps = read()
    valid = [t for t in temps.values() if t is not None]
    return max(valid) if valid else None


def is_warning():
    """True if any sensor exceeds the warning threshold."""
    t = max_temp()
    return t is not None and t >= config.TEMP_WARN_C


def is_critical():
    """True if any sensor exceeds the critical threshold."""
    t = max_temp()
    return t is not None and t >= config.TEMP_CRIT_C


def is_emergency():
    """True if any sensor exceeds the emergency threshold (forced shutdown)."""
    t = max_temp()
    return t is not None and t >= config.TEMP_EMERGENCY_C


def status():
    """Return temperature status string: 'emergency', 'critical', 'warn', or 'ok'.

    Returns 'ok' when no sensors are present (fail-open).
    """
    if sensor_count() == 0:
        return "ok"
    if is_emergency():
        return "emergency"
    if is_critical():
        return "critical"
    if is_warning():
        return "warn"
    return "ok"
