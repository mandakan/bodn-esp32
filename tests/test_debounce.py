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
        d.update(1, now_ms=5)  # bounce
        d.update(0, now_ms=10)  # settles low again
        d.update(0, now_ms=40)  # 30ms since last change at t=10
        assert d.pressed


class TestConfig:
    """Smoke test: config.py can be imported on the host."""

    def test_config_imports(self):
        from bodn import config

        assert isinstance(config.MCP_BTN_PINS, list)
        assert len(config.MCP_BTN_PINS) == 8

    def test_pin_numbers_are_ints(self):
        from bodn import config

        for pin in config.MCP_BTN_PINS:
            assert isinstance(pin, int)

    def test_no_psram_pins_used(self):
        """GPIO 35, 36, 37 are reserved by OSPI PSRAM on N8R8."""
        from bodn import config

        psram_pins = {35, 36, 37}
        # Check all native GPIO assignments
        native_pins = [
            config.TFT_SCK, config.TFT_MOSI, config.TFT_CS,
            config.TFT_DC, config.TFT_RST, config.TFT_BL,
            config.TFT2_CS,
            config.I2S_MIC_SCK, config.I2S_MIC_WS, config.I2S_MIC_SD,
            config.I2S_SPK_BCK, config.I2S_SPK_WS, config.I2S_SPK_DIN,
            config.ENC1_CLK, config.ENC1_DT, config.ENC1_SW,
            config.ENC2_CLK, config.ENC2_DT, config.ENC2_SW,
            config.ENC3_CLK, config.ENC3_DT, config.ENC3_SW,
            config.NEOPIXEL_PIN,
            config.I2C_SCL, config.I2C_SDA,
        ]
        for pin in native_pins:
            assert pin not in psram_pins, f"GPIO {pin} is reserved by PSRAM"

    def test_no_duplicate_native_pins(self):
        """Each native GPIO should be assigned only once."""
        from bodn import config

        native_pins = [
            config.TFT_SCK, config.TFT_MOSI, config.TFT_CS,
            config.TFT_DC, config.TFT_RST, config.TFT_BL,
            config.TFT2_CS,
            config.I2S_MIC_SCK, config.I2S_MIC_WS, config.I2S_MIC_SD,
            config.I2S_SPK_BCK, config.I2S_SPK_WS, config.I2S_SPK_DIN,
            config.ENC1_CLK, config.ENC1_DT, config.ENC1_SW,
            config.ENC2_CLK, config.ENC2_DT, config.ENC2_SW,
            config.ENC3_CLK, config.ENC3_DT, config.ENC3_SW,
            config.NEOPIXEL_PIN,
            config.I2C_SCL, config.I2C_SDA,
        ]
        seen = {}
        for pin in native_pins:
            assert pin not in seen, f"GPIO {pin} used twice"
            seen[pin] = True
