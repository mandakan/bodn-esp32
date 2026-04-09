"""Tests for the ArcadeButtons driver (switch input + LED output)."""

from bodn.mcp23017 import MCP23017
from bodn.pca9685 import PCA9685
from bodn.arcade import ArcadeButtons


class FakeI2C:
    """Minimal I2C stub that records writes and returns preset reads."""

    def __init__(self):
        self.writes = []
        self.regs = {}

    def writeto_mem(self, addr, reg, data):
        val = data[0] if isinstance(data, (bytes, bytearray)) else data
        self.writes.append((addr, reg, val))
        self.regs[reg] = val

    def readfrom_mem_into(self, addr, reg, buf):
        for i in range(len(buf)):
            buf[i] = self.regs.get(reg + i, 0xFF)


def _make_arcade(i2c=None):
    """Create an ArcadeButtons instance with stubs."""
    i2c = i2c or FakeI2C()
    mcp = MCP23017(i2c, 0x20)
    pwm = PCA9685(i2c, 0x40)
    pins = [10, 11, 13, 14, 15]
    channels = [1, 2, 3, 4, 5]
    arc = ArcadeButtons(mcp, pins, pwm, channels)
    return arc, mcp, pwm, i2c


class TestArcadeButtons:
    def test_count(self):
        arc, _, _, _ = _make_arcade()
        assert arc.count == 5

    def test_pins_returns_list_of_mcppins(self):
        arc, _, _, _ = _make_arcade()
        pins = arc.pins
        assert len(pins) == 5
        # Each pin should have a value() method
        for p in pins:
            assert hasattr(p, "value")

    def test_pin_reads_from_mcp(self):
        arc, mcp, _, _ = _make_arcade()
        # Simulate button 0 (MCP pin 10 = port B bit 2) pressed (active low)
        mcp._portb = 0xFF & ~(1 << 2)  # bit 2 low = pressed
        assert arc.pin(0).value() == 0  # active low = pressed

    def test_pin_reads_not_pressed(self):
        arc, mcp, _, _ = _make_arcade()
        mcp._portb = 0xFF  # all high = not pressed
        assert arc.pin(0).value() == 1

    def test_set_led_brightness(self):
        i2c = FakeI2C()
        arc, _, pwm, _ = _make_arcade(i2c)
        i2c.writes.clear()
        arc.set_led(0, 255)  # full brightness
        assert arc.get_led_duty(0) == 4095

    def test_set_led_off(self):
        arc, _, _, _ = _make_arcade()
        arc.set_led(0, 0)
        assert arc.get_led_duty(0) == 0

    def test_set_led_half(self):
        arc, _, _, _ = _make_arcade()
        arc.set_led(2, 128)
        duty = arc.get_led_duty(2)
        # 128/255 * 4095 ≈ 2056
        assert 2040 <= duty <= 2060

    def test_set_all_leds(self):
        arc, _, _, _ = _make_arcade()
        arc.set_all_leds(100)
        for i in range(5):
            assert arc.get_led_duty(i) > 0

    def test_all_off(self):
        arc, _, _, _ = _make_arcade()
        arc.set_all_leds(200)
        arc.all_off()
        for i in range(5):
            assert arc.get_led_duty(i) == 0

    def test_set_led_duty_raw(self):
        arc, _, _, _ = _make_arcade()
        arc.set_led_duty(3, 2048)
        assert arc.get_led_duty(3) == 2048

    def test_pulse_led_varies(self):
        arc, _, _, _ = _make_arcade()
        duties = []
        for frame in range(0, 256, 32):
            arc.pulse_led(0, frame, speed=2)
            duties.append(arc.get_led_duty(0))
        # Pulse should produce varying values
        assert len(set(duties)) > 1

    def test_no_pwm_graceful(self):
        """ArcadeButtons works without PCA9685 (LEDs just don't light up)."""
        i2c = FakeI2C()
        mcp = MCP23017(i2c, 0x20)
        arc = ArcadeButtons(mcp, [10, 11, 13, 14, 15], pwm=None, pwm_channels=[])
        # Should not raise
        arc.set_led(0, 128)
        arc.set_all_leds(255)
        arc.all_off()
        assert arc.get_led_duty(0) == 0

    def test_flush_writes_only_changed(self):
        """flush() skips I2C when target matches current duty."""
        i2c = FakeI2C()
        arc, _, pwm, _ = _make_arcade(i2c)
        arc.set_led(0, 255)
        i2c.writes.clear()
        arc.flush()
        # First flush should write (target != duty)
        assert len(i2c.writes) > 0

        i2c.writes.clear()
        arc.flush()
        # Second flush with no changes — should NOT write
        assert len(i2c.writes) == 0

    def test_flush_batch_uniform(self):
        """flush() uses batch write when all targets are the same."""
        i2c = FakeI2C()
        arc, _, pwm, _ = _make_arcade(i2c)
        arc.all_on()
        i2c.writes.clear()
        arc.flush()
        # Should be a single batch write (1 I2C transaction)
        assert len(i2c.writes) == 1

    def test_pulse_starts_from_zero(self):
        """Each button starts its pulse from brightness 0 when first called."""
        arc, _, _, _ = _make_arcade()
        # Start pulsing button 0 at frame 100
        arc.pulse(0, 100, speed=2)
        duty_at_start = arc.get_led_duty(0)
        # Phase = (100-100)*2 = 0 → brightness 0
        assert duty_at_start == 0

    def test_pulse_per_button_offset(self):
        """Two buttons started at different frames pulse out of sync."""
        arc, _, _, _ = _make_arcade()
        # Start button 0 at frame 0, button 1 at frame 20
        arc.pulse(0, 0, speed=2)
        arc.pulse(1, 20, speed=2)
        # Now at frame 40, button 0 has been pulsing for 40 frames,
        # button 1 for 20 frames — different phase
        arc.pulse(0, 40, speed=2)
        arc.pulse(1, 40, speed=2)
        assert arc.get_led_duty(0) != arc.get_led_duty(1)

    def test_pulse_resets_on_off(self):
        """Pulse offset resets when button goes through a non-pulse state."""
        arc, _, _, _ = _make_arcade()
        arc.pulse(0, 10, speed=2)
        arc.off(0)
        # Restart pulsing at frame 50 — should start from zero again
        arc.pulse(0, 50, speed=2)
        # Phase = (50-50)*2 = 0
        assert arc.get_led_duty(0) == 0

    def test_wave_produces_different_duties(self):
        """wave() gives each button a different brightness."""
        arc, _, _, _ = _make_arcade()
        arc.wave(64, speed=2, spacing=32)
        duties = [arc.get_led_duty(i) for i in range(5)]
        # With spacing=32 and 5 buttons, there should be variation
        assert len(set(duties)) > 1

    def test_flush_no_pwm_safe(self):
        """flush() is a no-op without PCA9685."""
        i2c = FakeI2C()
        mcp = MCP23017(i2c, 0x20)
        arc = ArcadeButtons(mcp, [10, 11, 13, 14, 15], pwm=None, pwm_channels=[])
        arc.set_led(0, 255)
        arc.flush()  # should not raise


class TestInputStateArcade:
    """Test arcade button integration with InputState."""

    def test_arcade_scan(self):
        from bodn.ui.input import InputState

        i2c = FakeI2C()
        mcp = MCP23017(i2c, 0x20)
        arc = ArcadeButtons(mcp, [10, 11, 13, 14, 15])

        # Create minimal stubs for other inputs
        buttons = [mcp.pin(i) for i in range(8)]
        switches = [mcp.pin(8), mcp.pin(9)]

        class FakeEnc:
            def __init__(self):
                self.value = 0
                self.sw = type("", (), {"value": lambda self: 1})()

        encoders = [FakeEnc(), FakeEnc(), FakeEnc()]
        ms = [0]
        inp = InputState(
            buttons, switches, encoders, lambda: ms[0], arcade_pins=arc.pins
        )

        assert len(inp.arc_held) == 5
        assert len(inp.arc_just_pressed) == 5
        assert len(inp.arc_just_released) == 5

        # All not pressed initially
        i2c.regs[0x12] = 0xFF  # GPIOA
        i2c.regs[0x13] = 0xFF  # GPIOB
        mcp.refresh()
        inp.scan()
        inp.consume()
        assert not any(inp.arc_held)
        assert not any(inp.arc_just_pressed)

        # Press arcade button 0 (MCP pin 10 = port B bit 2)
        ms[0] = 50
        i2c.regs[0x13] = 0xFF & ~(1 << 2)  # GPIOB
        mcp.refresh()
        inp.scan()
        # Advance past debounce delay (15ms)
        ms[0] = 100
        mcp.refresh()
        inp.scan()
        inp.consume()
        assert inp.arc_held[0]
        assert inp.arc_just_pressed[0]
        assert not inp.arc_held[1]

    def test_first_arc_pressed(self):
        from bodn.ui.input import InputState

        i2c = FakeI2C()
        mcp = MCP23017(i2c, 0x20)
        arc = ArcadeButtons(mcp, [10, 11, 13, 14, 15])
        buttons = [mcp.pin(i) for i in range(8)]
        switches = [mcp.pin(8), mcp.pin(9)]

        class FakeEnc:
            def __init__(self):
                self.value = 0
                self.sw = type("", (), {"value": lambda self: 1})()

        encoders = [FakeEnc(), FakeEnc(), FakeEnc()]
        ms = [0]
        inp = InputState(
            buttons, switches, encoders, lambda: ms[0], arcade_pins=arc.pins
        )

        i2c.regs[0x12] = 0xFF  # GPIOA
        i2c.regs[0x13] = 0xFF  # GPIOB
        mcp.refresh()
        inp.scan()
        inp.consume()

        assert inp.first_arc_pressed() == -1

        # Press arcade button 2 (MCP pin 13 = port B bit 5)
        ms[0] = 50
        i2c.regs[0x13] = 0xFF & ~(1 << 5)  # GPIOB
        mcp.refresh()
        inp.scan()
        # Advance past debounce delay (15ms)
        ms[0] = 100
        mcp.refresh()
        inp.scan()
        inp.consume()
        assert inp.first_arc_pressed() == 2

    def test_arcade_activity_detected(self):
        from bodn.ui.input import InputState

        i2c = FakeI2C()
        mcp = MCP23017(i2c, 0x20)
        arc = ArcadeButtons(mcp, [10, 11, 13, 14, 15])
        buttons = [mcp.pin(i) for i in range(8)]
        switches = [mcp.pin(8), mcp.pin(9)]

        class FakeEnc:
            def __init__(self):
                self.value = 0
                self.sw = type("", (), {"value": lambda self: 1})()

        encoders = [FakeEnc(), FakeEnc(), FakeEnc()]
        ms = [0]
        inp = InputState(
            buttons, switches, encoders, lambda: ms[0], arcade_pins=arc.pins
        )

        i2c.regs[0x12] = 0xFF  # GPIOA
        i2c.regs[0x13] = 0xFF  # GPIOB
        mcp.refresh()
        inp.scan()
        inp.consume()
        assert not inp.has_activity()

        # Press arcade button
        ms[0] = 50
        i2c.regs[0x13] = 0xFF & ~(1 << 3)  # GPIOB, MCP pin 11 = bit 3
        mcp.refresh()
        inp.scan()
        # Advance past debounce delay (15ms)
        ms[0] = 100
        mcp.refresh()
        inp.scan()
        inp.consume()
        assert inp.has_activity()
