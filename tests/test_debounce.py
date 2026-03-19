from bodn.debounce import Debouncer


class TestDebouncer:
    def test_initial_state_is_released(self):
        d = Debouncer(delay_ms=50)
        assert not d.pressed

    def test_short_glitch_ignored(self):
        d = Debouncer(delay_ms=50)
        # Button goes low for 10ms then back high — should be ignored
        d.update(0, now_ms=0)
        d.update(1, now_ms=10)
        d.update(1, now_ms=100)
        assert not d.pressed

    def test_stable_press_detected(self):
        d = Debouncer(delay_ms=50)
        d.update(0, now_ms=0)
        d.update(0, now_ms=50)
        assert d.pressed

    def test_stable_release_detected(self):
        d = Debouncer(delay_ms=50)
        # Press
        d.update(0, now_ms=0)
        d.update(0, now_ms=50)
        assert d.pressed
        # Release
        d.update(1, now_ms=100)
        d.update(1, now_ms=150)
        assert not d.pressed

    def test_fell_fires_once(self):
        d = Debouncer(delay_ms=20)
        assert not d.fell(0, now_ms=0)
        assert d.fell(0, now_ms=20)  # transition happens here
        assert not d.fell(0, now_ms=40)  # already pressed, no new edge

    def test_rose_fires_once(self):
        d = Debouncer(delay_ms=20)
        # Press first
        d.update(0, now_ms=0)
        d.update(0, now_ms=20)
        # Release
        assert not d.rose(1, now_ms=40)
        assert d.rose(1, now_ms=60)
        assert not d.rose(1, now_ms=80)

    def test_custom_delay(self):
        d = Debouncer(delay_ms=100)
        d.update(0, now_ms=0)
        d.update(0, now_ms=99)
        assert not d.pressed  # not yet
        d.update(0, now_ms=100)
        assert d.pressed

    def test_bounce_during_press(self):
        """Simulate noisy contact: 0, 1, 0, 0 — should still detect press."""
        d = Debouncer(delay_ms=30)
        d.update(0, now_ms=0)
        d.update(1, now_ms=5)   # bounce
        d.update(0, now_ms=10)  # settles low again
        d.update(0, now_ms=40)  # 30ms since last change at t=10
        assert d.pressed


class TestConfig:
    """Smoke test: config.py can be imported on the host."""

    def test_config_imports(self):
        from bodn import config

        assert isinstance(config.BTN_PINS, list)
        assert len(config.BTN_PINS) == 8

    def test_pin_numbers_are_ints(self):
        from bodn import config

        for pin in config.BTN_PINS:
            assert isinstance(pin, int)
