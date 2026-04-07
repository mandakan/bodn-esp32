# tests/test_temperature.py — temperature module pure-logic tests

import time
import pytest


@pytest.fixture(autouse=True)
def reset_temperature_module():
    """Reset module-level state between tests."""
    from bodn import temperature

    temperature._ds = None
    temperature._roms = []
    temperature._temps = {}
    # Force cache miss
    temperature._next_read_ms = time.ticks_add(time.ticks_ms(), -1000)
    temperature._conv_pending = False
    temperature._conv_start_ms = 0
    yield


class TestTemperatureStatus:
    """Test status classification against config thresholds."""

    def _inject_soc(self, temp_c, monkeypatch):
        """Override soc_temp() to return a fixed value."""
        from bodn import temperature

        monkeypatch.setattr(temperature, "soc_temp", lambda: temp_c)

    def test_status_ok(self, monkeypatch):
        from bodn import temperature

        self._inject_soc(35.0, monkeypatch)
        assert temperature.status() == "ok"

    def test_status_warn(self, monkeypatch):
        from bodn import temperature

        self._inject_soc(42.0, monkeypatch)
        assert temperature.status() == "warn"

    def test_status_critical(self, monkeypatch):
        from bodn import temperature

        self._inject_soc(52.0, monkeypatch)
        assert temperature.status() == "critical"

    def test_status_emergency(self, monkeypatch):
        from bodn import temperature

        self._inject_soc(62.0, monkeypatch)
        assert temperature.status() == "emergency"

    def test_status_at_boundary_warn(self, monkeypatch):
        from bodn import temperature

        self._inject_soc(40.0, monkeypatch)
        assert temperature.status() == "warn"

    def test_status_at_boundary_critical(self, monkeypatch):
        from bodn import temperature

        self._inject_soc(50.0, monkeypatch)
        assert temperature.status() == "critical"

    def test_status_at_boundary_emergency(self, monkeypatch):
        from bodn import temperature

        self._inject_soc(60.0, monkeypatch)
        assert temperature.status() == "emergency"


class TestMaxTemp:
    """Test max_temp() aggregation across sensors."""

    def test_soc_only(self, monkeypatch):
        from bodn import temperature

        monkeypatch.setattr(temperature, "soc_temp", lambda: 45.0)
        assert temperature.max_temp() == 45.0

    def test_soc_none(self, monkeypatch):
        from bodn import temperature

        monkeypatch.setattr(temperature, "soc_temp", lambda: None)
        # No external sensors either → None
        assert temperature.max_temp() is None

    def test_external_higher_than_soc(self, monkeypatch):
        from bodn import temperature

        # Inject an external sensor reading via _temps
        fake_rom = b"\x28\x01\x02\x03\x04\x05\x06\x07"
        temperature._roms = [fake_rom]
        temperature._temps = {fake_rom: 55.0}
        # Force cache to be fresh
        temperature._next_read_ms = time.ticks_add(time.ticks_ms(), 60_000)
        monkeypatch.setattr(temperature, "soc_temp", lambda: 40.0)
        assert temperature.max_temp() == 55.0

    def test_soc_higher_than_external(self, monkeypatch):
        from bodn import temperature

        fake_rom = b"\x28\x01\x02\x03\x04\x05\x06\x07"
        temperature._roms = [fake_rom]
        temperature._temps = {fake_rom: 30.0}
        temperature._next_read_ms = time.ticks_add(time.ticks_ms(), 60_000)
        monkeypatch.setattr(temperature, "soc_temp", lambda: 48.0)
        assert temperature.max_temp() == 48.0


class TestThresholdFunctions:
    """Test is_warning/is_critical/is_emergency helpers."""

    def test_is_warning_false(self, monkeypatch):
        from bodn import temperature

        monkeypatch.setattr(temperature, "soc_temp", lambda: 35.0)
        assert temperature.is_warning() is False

    def test_is_warning_true(self, monkeypatch):
        from bodn import temperature

        monkeypatch.setattr(temperature, "soc_temp", lambda: 41.0)
        assert temperature.is_warning() is True

    def test_is_critical_false(self, monkeypatch):
        from bodn import temperature

        monkeypatch.setattr(temperature, "soc_temp", lambda: 45.0)
        assert temperature.is_critical() is False

    def test_is_critical_true(self, monkeypatch):
        from bodn import temperature

        monkeypatch.setattr(temperature, "soc_temp", lambda: 51.0)
        assert temperature.is_critical() is True

    def test_is_emergency_false(self, monkeypatch):
        from bodn import temperature

        monkeypatch.setattr(temperature, "soc_temp", lambda: 55.0)
        assert temperature.is_emergency() is False

    def test_is_emergency_true(self, monkeypatch):
        from bodn import temperature

        monkeypatch.setattr(temperature, "soc_temp", lambda: 61.0)
        assert temperature.is_emergency() is True
