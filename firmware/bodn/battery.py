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
from micropython import const
from machine import ADC, Pin
from bodn import config

# Integer-scaled constants to avoid float math:
#   V_bat = V_adc × (470+150)/150 = V_adc × 4.1333
#   V_adc = raw × 1.25 / 4095
#   V_bat_mV = raw × 1250 × 4133 / (4095 × 1000) ≈ raw × 5167 / 4095
#   Simplified: V_bat_mV = raw * 5167 // 4095
_VBAT_MV_NUM = const(5167)  # 1250 * 4133 // 1000
_ADC_MAX = const(4095)
_VBAT_FULL_MV = const(4200)  # LiPo 100 %
_VBAT_EMPTY_MV = const(3000)  # LiPo 0 %
_VBAT_RANGE_MV = const(1200)  # 4200 - 3000

_SAMPLES = const(4)  # ADC readings to average per measurement
_CACHE_MS = const(30_000)  # re-read at most once every 30 s

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

    raw = 0
    for _ in range(_SAMPLES):
        raw += _adc.read()
    raw //= _SAMPLES
    v_bat_mv = raw * _VBAT_MV_NUM // _ADC_MAX
    pct = (v_bat_mv - _VBAT_EMPTY_MV) * 100 // _VBAT_RANGE_MV
    pct = max(0, min(100, pct))

    # PWR_SENS is high-Z (reads high via internal pull-down on the board)
    # when on battery, and driven low when USB power / charger is active.
    charging = _pwr_pin.value() == 0

    _cached_pct = pct
    _cached_charging = charging
    _next_read_ms = time.ticks_add(now, _CACHE_MS)
    return pct, charging
