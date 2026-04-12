# bodn/native_i2c.py — machine.I2C-compatible wrapper backed by _mcpinput
#
# When the _mcpinput C module owns the I2C bus, Python code (PCA9685,
# MCP23017 for MCP2, etc.) uses this shim instead of machine.I2C.
# All calls go through the C module's mutex-protected I2C functions.

import _mcpinput


class NativeI2C:
    """Drop-in replacement for machine.I2C backed by _mcpinput C module.

    Supports the subset of machine.I2C used by PCA9685 and MCP23017:
    writeto_mem(), readfrom_mem_into(), and scan().

    Also provides raw (non-register-addressed) I2C for devices like the
    PN532 that use a framed protocol: writeto() and readfrom_into().
    """

    def writeto_mem(self, addr, reg, data):
        _mcpinput.i2c_write(addr, reg, data)

    def readfrom_mem_into(self, addr, reg, buf):
        result = _mcpinput.i2c_read(addr, reg, len(buf))
        for i in range(len(buf)):
            buf[i] = result[i]

    def writeto(self, addr, data):
        _mcpinput.i2c_raw_write(addr, data)

    def readfrom_into(self, addr, buf):
        result = _mcpinput.i2c_raw_read(addr, len(buf))
        for i in range(len(buf)):
            buf[i] = result[i]

    def scan(self):
        return _mcpinput.i2c_scan()
