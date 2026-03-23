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
        buf[0] = self.regs.get(reg, 0xFF)


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
        # Should have written to PCA9685 channel 1
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
        assert not any(inp.arc_held)
        assert not any(inp.arc_just_pressed)

        # Press arcade button 0 (MCP pin 10 = port B bit 2)
        ms[0] = 50
        i2c.regs[0x13] = 0xFF & ~(1 << 2)  # GPIOB
        mcp.refresh()
        inp.scan()
        # Advance past debounce delay (30ms)
        ms[0] = 100
        mcp.refresh()
        inp.scan()
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

        assert inp.first_arc_pressed() == -1

        # Press arcade button 2 (MCP pin 13 = port B bit 5)
        ms[0] = 50
        i2c.regs[0x13] = 0xFF & ~(1 << 5)  # GPIOB
        mcp.refresh()
        inp.scan()
        # Advance past debounce delay (30ms)
        ms[0] = 100
        mcp.refresh()
        inp.scan()
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
        assert not inp.has_activity()

        # Press arcade button
        ms[0] = 50
        i2c.regs[0x13] = 0xFF & ~(1 << 3)  # GPIOB, MCP pin 11 = bit 3
        mcp.refresh()
        inp.scan()
        # Advance past debounce delay (30ms)
        ms[0] = 100
        mcp.refresh()
        inp.scan()
        assert inp.has_activity()
