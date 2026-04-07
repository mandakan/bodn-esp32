# tests/test_battery.py — battery module pure-logic tests

import time
import pytest


@pytest.fixture(autouse=True)
def reset_battery_module():
    """Reset module-level state between tests."""
    from bodn import battery

    battery._cached_pct = None
    battery._cached_mv = 0
    battery._cached_charging = False
    # Force cache miss: set next_read to a past timestamp
    battery._next_read_ms = time.ticks_add(time.ticks_ms(), -1000)
    battery._adc = None
    battery._pwr_pin = None
    yield


class FakeADC:
    def __init__(self, raw_value=2000):
        self.raw = raw_value

    def atten(self, *a):
        pass

    def read(self):
        return self.raw


class FakePwrPin:
    def __init__(self, val=1):
        self._val = val

    def value(self):
        return self._val


class TestBatteryStatus:
    """Test status() classification against voltage thresholds."""

    def _setup(self, raw_adc, pwr_val=1):
        from bodn import battery

        battery._adc = FakeADC(raw_adc)
        battery._pwr_pin = FakePwrPin(pwr_val)

    def test_ok_battery(self):
        from bodn import battery

        # raw ~2800 → ~3530 mV (above warn threshold 3400)
        self._setup(raw_adc=2800)
        assert battery.status() == "ok"

    def test_warn_battery(self):
        from bodn import battery

        # raw ~2650 → ~3340 mV (below 3400 warn, above 3200 crit)
        self._setup(raw_adc=2650)
        assert battery.status() == "warn"

    def test_critical_battery(self):
        from bodn import battery

        # raw ~2500 → ~3150 mV (below 3200 crit, above 3100 shutdown)
        self._setup(raw_adc=2500)
        assert battery.status() == "critical"

    def test_shutdown_battery(self):
        from bodn import battery

        # raw ~2400 → ~3025 mV (below 3100 shutdown)
        self._setup(raw_adc=2400)
        assert battery.status() == "shutdown"

    def test_usb_powered(self):
        from bodn import battery

        # pwr_pin=0 means USB present, high voltage → charging
        self._setup(raw_adc=3200, pwr_val=0)
        assert battery.status() == "usb"

    def test_usb_no_battery(self):
        from bodn import battery

        # USB present + very low voltage → no battery
        self._setup(raw_adc=500, pwr_val=0)
        pct, charging = battery.read()
        assert pct is None
        assert charging is True
        assert battery.status() == "usb"


class TestBatteryVoltage:
    """Test voltage calculation from raw ADC values."""

    def test_voltage_conversion(self):
        from bodn import battery

        battery._adc = FakeADC(2000)
        battery._pwr_pin = FakePwrPin(1)
        battery.read()
        mv = battery.voltage_mv()
        # raw=2000 → 2000 * 5167 // 4095 ≈ 2523 mV
        assert 2520 <= mv <= 2530

    def test_full_charge_voltage(self):
        from bodn import battery

        # raw ~3330 → ~4200 mV (full charge)
        battery._adc = FakeADC(3330)
        battery._pwr_pin = FakePwrPin(1)
        battery.read()
        mv = battery.voltage_mv()
        assert 4190 <= mv <= 4210


class TestBatteryPercent:
    """Test percentage calculation."""

    def test_full_battery(self):
        from bodn import battery

        # ~4200 mV → 100%
        battery._adc = FakeADC(3330)
        battery._pwr_pin = FakePwrPin(1)
        pct, _ = battery.read()
        assert pct == 100

    def test_empty_battery(self):
        from bodn import battery

        # ~3000 mV → 0%
        battery._adc = FakeADC(2380)
        battery._pwr_pin = FakePwrPin(1)
        pct, _ = battery.read()
        assert pct == 0

    def test_percent_clamped_low(self):
        from bodn import battery

        # Below 3000 mV → still 0%, not negative
        battery._adc = FakeADC(1000)
        battery._pwr_pin = FakePwrPin(1)
        pct, _ = battery.read()
        assert pct == 0
