# bodn/mcp23017.py — MCP23017 I2C GPIO expander driver
#
# Provides Pin-compatible objects so buttons/toggles on the expander
# can be used with InputState without any code changes.

from micropython import const

_IODIRA = const(0x00)
_IODIRB = const(0x01)
_GPINTENA = const(0x04)
_GPINTENB = const(0x05)
_INTCONA = const(0x08)
_INTCONB = const(0x09)
_IOCONA = const(0x0A)
_GPPUA = const(0x0C)
_GPPUB = const(0x0D)
_INTCAPA = const(0x10)
_INTCAPB = const(0x11)
_GPIOA = const(0x12)
_GPIOB = const(0x13)


class MCP23017:
    """Minimal MCP23017 driver over I2C.

    Args:
        i2c: machine.I2C (or SoftI2C) instance.
        addr: 7-bit I2C address (default 0x20).
    """

    def __init__(self, i2c, addr=0x20):
        self._i2c = i2c
        self._addr = addr
        self._buf1 = bytearray(1)
        # Cache the last-read port values to avoid redundant I2C reads
        # when multiple pins are read in the same scan cycle.
        self._porta = 0xFF
        self._portb = 0xFF
        self._dirty = True
        # Default: all 16 pins as inputs with pull-ups enabled
        self._write_reg(_IODIRA, 0xFF)
        self._write_reg(_IODIRB, 0xFF)
        self._write_reg(_GPPUA, 0xFF)
        self._write_reg(_GPPUB, 0xFF)

    def _write_reg(self, reg, value):
        self._i2c.writeto_mem(self._addr, reg, bytes([value]))

    def _read_reg(self, reg):
        self._i2c.readfrom_mem_into(self._addr, reg, self._buf1)
        return self._buf1[0]

    def read_port_a(self):
        return self._read_reg(_GPIOA)

    def read_port_b(self):
        return self._read_reg(_GPIOB)

    def refresh(self):
        """Read both ports in one go. Call once per scan cycle."""
        self._porta = self.read_port_a()
        self._portb = self.read_port_b()
        self._dirty = False

    def pin_value(self, pin):
        """Read a single pin (0-15). 0-7 = port A, 8-15 = port B.

        Returns 0 or 1 (matching machine.Pin.value() convention).
        """
        if pin < 8:
            return (self._porta >> pin) & 1
        else:
            return (self._portb >> (pin - 8)) & 1

    def enable_interrupts(self):
        """Enable interrupt-on-change for all pins on both ports.

        Configures MIRROR=1 (INTA+INTB OR'd), ODR=1 (open-drain),
        INTPOL=0 (active-low). Compares to previous value (not DEFVAL).
        """
        # IOCON: MIRROR=1 (bit6), ODR=1 (bit2) → 0x44
        self._write_reg(_IOCONA, 0x44)
        # Compare to previous pin value
        self._write_reg(_INTCONA, 0x00)
        self._write_reg(_INTCONB, 0x00)
        # Enable interrupts on all pins
        self._write_reg(_GPINTENA, 0xFF)
        self._write_reg(_GPINTENB, 0xFF)
        # Clear any pending interrupts
        self._read_reg(_INTCAPA)
        self._read_reg(_INTCAPB)

    def disable_interrupts(self):
        """Disable all MCP23017 interrupts."""
        self._write_reg(_GPINTENA, 0x00)
        self._write_reg(_GPINTENB, 0x00)

    def clear_interrupts(self):
        """Clear pending interrupts by reading capture registers."""
        self._read_reg(_INTCAPA)
        self._read_reg(_INTCAPB)

    def pin(self, pin_num):
        """Return a Pin-like object for the given MCP23017 pin.

        The returned object has a .value() method compatible with
        machine.Pin, so it works with Debouncer and InputState.
        """
        return MCPPin(self, pin_num)


class MCPPin:
    """Pin-compatible wrapper for a single MCP23017 I/O pin."""

    def __init__(self, mcp, pin):
        self._mcp = mcp
        self._pin = pin

    def value(self):
        return self._mcp.pin_value(self._pin)


class _StubPin:
    """Fallback pin that always reads 1 (not pressed).

    Used when MCP2 is unavailable so encoder objects remain functional.
    """

    def value(self):
        return 1
