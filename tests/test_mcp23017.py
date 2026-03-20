"""Tests for the MCP23017 GPIO expander driver (pure logic, no hardware)."""

from bodn.mcp23017 import MCP23017, MCPPin


class FakeI2C:
    """Minimal I2C stub that records writes and returns preset reads."""

    def __init__(self):
        self.writes = []
        self.regs = {}  # reg -> value

    def writeto_mem(self, addr, reg, data):
        self.writes.append((addr, reg, data[0]))
        self.regs[reg] = data[0]

    def readfrom_mem_into(self, addr, reg, buf):
        buf[0] = self.regs.get(reg, 0xFF)


class TestMCP23017:
    def test_init_sets_inputs_and_pullups(self):
        i2c = FakeI2C()
        MCP23017(i2c, 0x20)
        # Should set IODIRA, IODIRB, GPPUA, GPPUB all to 0xFF
        assert (0x20, 0x00, 0xFF) in i2c.writes  # IODIRA
        assert (0x20, 0x01, 0xFF) in i2c.writes  # IODIRB
        assert (0x20, 0x0C, 0xFF) in i2c.writes  # GPPUA
        assert (0x20, 0x0D, 0xFF) in i2c.writes  # GPPUB

    def test_refresh_reads_both_ports(self):
        i2c = FakeI2C()
        mcp = MCP23017(i2c, 0x20)
        # Simulate port A = 0b11111110 (pin 0 low), port B = 0xFF
        i2c.regs[0x12] = 0xFE
        i2c.regs[0x13] = 0xFF
        mcp.refresh()
        assert mcp.pin_value(0) == 0  # pin 0 is low
        assert mcp.pin_value(1) == 1  # pin 1 is high
        assert mcp.pin_value(7) == 1
        assert mcp.pin_value(8) == 1  # port B pin 0

    def test_pin_value_port_b(self):
        i2c = FakeI2C()
        mcp = MCP23017(i2c, 0x20)
        i2c.regs[0x12] = 0xFF
        i2c.regs[0x13] = 0b11110111  # pin 11 (GPB3) low
        mcp.refresh()
        assert mcp.pin_value(11) == 0
        assert mcp.pin_value(10) == 1

    def test_mcp_pin_has_value_method(self):
        i2c = FakeI2C()
        mcp = MCP23017(i2c, 0x20)
        i2c.regs[0x12] = 0b11111101  # pin 1 low
        i2c.regs[0x13] = 0xFF
        mcp.refresh()
        pin = mcp.pin(1)
        assert isinstance(pin, MCPPin)
        assert pin.value() == 0

    def test_multiple_pins_same_refresh(self):
        """All pins read from the same cached port data."""
        i2c = FakeI2C()
        mcp = MCP23017(i2c, 0x20)
        i2c.regs[0x12] = 0b10101010
        i2c.regs[0x13] = 0b01010101
        mcp.refresh()
        pins_a = [mcp.pin(i).value() for i in range(8)]
        pins_b = [mcp.pin(i + 8).value() for i in range(8)]
        assert pins_a == [0, 1, 0, 1, 0, 1, 0, 1]
        assert pins_b == [1, 0, 1, 0, 1, 0, 1, 0]

    def test_custom_address(self):
        i2c = FakeI2C()
        MCP23017(i2c, 0x27)
        assert any(addr == 0x27 for addr, _, _ in i2c.writes)
