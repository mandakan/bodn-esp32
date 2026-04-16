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

    def test_flush_is_noop(self):
        """flush() is a no-op since C engine handles I2C writes."""
        arc, _, _, _ = _make_arcade()
        arc.flush()  # should not raise

    def test_semantic_methods_dont_raise(self):
        """All semantic LED methods delegate to C stub without errors."""
        arc, _, _, _ = _make_arcade()
        arc.off(0)
        arc.all_off()
        arc.glow(0)
        arc.all_glow()
        arc.on(0)
        arc.all_on()
        arc.pulse(0, 10, speed=2)
        arc.all_pulse(10, speed=2)
        arc.blink(0, 10, speed=4)
        arc.all_blink(10, speed=4)
        arc.wave(10, speed=2, spacing=32)
        arc.flash(0, duration=9)
        arc.tick_flash()
        arc.pulse_led(0, 10, speed=2)

    def test_no_pwm_graceful(self):
        """ArcadeButtons works without PCA9685."""
        i2c = FakeI2C()
        mcp = MCP23017(i2c, 0x20)
        arc = ArcadeButtons(mcp, [10, 11, 13, 14, 15], pwm=None, pwm_channels=[])
        # Should not raise
        arc.off(0)
        arc.all_off()
        arc.flush()


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
