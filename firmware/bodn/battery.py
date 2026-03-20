# bodn/battery.py — LiPo battery level via the DevKit-Lipo on-board ADC circuit
#
# Hardware (Olimex ESP32-S3-DevKit-Lipo Rev B):
#   BAT_SENS (GPIO 6): battery voltage via R6/R7 voltage divider (470 kΩ / 150 kΩ)
#     V_bat = V_adc × (470 + 150) / 150 = V_adc × 4.133
#   PWR_SENS (GPIO 5): high-Z when on battery; driven low when USB power present
#
# ADC attenuation: ATTN_2_5DB gives ~0–1.25 V full scale, which covers the
# divided LiPo range of 0.73 V (3.0 V empty) to 1.02 V (4.2 V full).

import time
from machine import ADC, Pin
from bodn import config

_DIVIDER = (470 + 150) / 150  # R6+R7 / R7 = 4.133
_ADC_VREF = 1.25  # ATTN_2_5DB full-scale voltage (V) — may need calibration
_ADC_MAX = 4095
_VBAT_FULL = 4.2  # LiPo 100 %
_VBAT_EMPTY = 3.0  # LiPo 0 %

_SAMPLES = 4  # ADC readings to average per measurement
_CACHE_MS = 30_000  # re-read at most once every 30 s

_adc = None
_pwr_pin = None
_cached_pct = 0
_cached_charging = False
_next_read_ms = 0


def _init():
    global _adc, _pwr_pin
    if _adc is None:
        _adc = ADC(Pin(config.BAT_SENS_PIN))
        _adc.atten(ADC.ATTN_2_5DB)
    if _pwr_pin is None:
        _pwr_pin = Pin(config.PWR_SENS_PIN, Pin.IN)


def read():
    """Return (percent: int, charging: bool).

    percent  — battery charge level 0–100.
    charging — True when USB / charger power is detected.

    Results are cached for 30 s to avoid hammering the ADC.
    """
    global _cached_pct, _cached_charging, _next_read_ms
    now = time.ticks_ms()
    if time.ticks_diff(now, _next_read_ms) < 0:
        return _cached_pct, _cached_charging

    _init()

    raw = sum(_adc.read() for _ in range(_SAMPLES)) // _SAMPLES
    v_adc = raw * _ADC_VREF / _ADC_MAX
    v_bat = v_adc * _DIVIDER
    pct = int((v_bat - _VBAT_EMPTY) / (_VBAT_FULL - _VBAT_EMPTY) * 100)
    pct = max(0, min(100, pct))

    # PWR_SENS is high-Z (reads high via internal pull-down on the board)
    # when on battery, and driven low when USB power / charger is active.
    charging = _pwr_pin.value() == 0

    _cached_pct = pct
    _cached_charging = charging
    _next_read_ms = time.ticks_add(now, _CACHE_MS)
    return pct, charging
