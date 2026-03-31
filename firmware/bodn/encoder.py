# bodn/encoder.py — hardware PCNT rotary encoder reader
#
# Uses the ESP32-S3 Pulse Counter (PCNT) peripheral for quadrature
# decoding in hardware. Zero CPU overhead, atomic pin reads, built-in
# glitch filter — no IRQ handler, no bounce issues.
from machine import Encoder as _HWEncoder, Pin


class Encoder:
    """Reads a KY-040 rotary encoder using the hardware PCNT peripheral.

    value increments/decrements on each detent. Read it from the main loop.

    Args:
        clk_pin: GPIO number for CLK (phase A).
        dt_pin:  GPIO number for DT (phase B).
        sw_pin:  GPIO number for SW, or a pin-like object with .value().
                 Pass an MCPPin to route the push button through MCP23017.
        pcnt_id: PCNT unit number (0–7). Each encoder needs its own unit.
        filter_ns: Glitch filter in nanoseconds (rejects pulses shorter than this).
    """

    _next_id = 0  # auto-assign PCNT unit IDs

    def __init__(self, clk_pin, dt_pin, sw_pin, pcnt_id=None, filter_ns=1000):
        if pcnt_id is None:
            pcnt_id = Encoder._next_id
            Encoder._next_id += 1
        self.clk = Pin(clk_pin, Pin.IN, Pin.PULL_UP)
        self.dt = Pin(dt_pin, Pin.IN, Pin.PULL_UP)
        self._hw = _HWEncoder(
            pcnt_id,
            phase_a=self.clk,
            phase_b=self.dt,
            filter_ns=filter_ns,
        )
        if isinstance(sw_pin, int):
            self.sw = Pin(sw_pin, Pin.IN, Pin.PULL_UP)
        else:
            self.sw = sw_pin  # MCPPin or any object with .value()
        self._offset = 0

    @property
    def value(self):
        return self._hw.value() + self._offset

    @value.setter
    def value(self, v):
        self._offset = v - self._hw.value()

    def deinit(self):
        """Release the PCNT unit."""
        self._hw.deinit()

    def pressed(self):
        """Return True if the encoder button is currently pressed."""
        return self.sw.value() == 0
