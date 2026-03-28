# bodn/encoder.py — IRQ-based rotary encoder reader
from machine import Pin
import time


class Encoder:
    """Reads a KY-040 rotary encoder using hardware interrupts.

    value increments/decrements on each detent. Read it from the main loop.
    Uses a 2ms debounce window to reject contact bounce.

    Args:
        clk_pin: GPIO number for CLK (hardware IRQ).
        dt_pin:  GPIO number for DT.
        sw_pin:  GPIO number for SW, or a pin-like object with .value().
                 Pass an MCPPin to route the push button through MCP23017.
    """

    def __init__(self, clk_pin, dt_pin, sw_pin):
        self.clk = Pin(clk_pin, Pin.IN, Pin.PULL_UP)
        self.dt = Pin(dt_pin, Pin.IN, Pin.PULL_UP)
        if isinstance(sw_pin, int):
            self.sw = Pin(sw_pin, Pin.IN, Pin.PULL_UP)
        else:
            self.sw = sw_pin  # MCPPin or any object with .value()
        self.value = 0
        self._last_clk = self.clk.value()
        self._last_us = time.ticks_us()
        self.clk.irq(
            trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING,
            handler=self._on_clk,
        )

    def _on_clk(self, pin):
        now = time.ticks_us()
        if time.ticks_diff(now, self._last_us) < 4000:  # 4ms debounce
            return
        clk_val = self.clk.value()
        if clk_val != self._last_clk:
            if clk_val != self.dt.value():
                self.value += 1
            else:
                self.value -= 1
            self._last_clk = clk_val
            self._last_us = now

    def pressed(self):
        """Return True if the encoder button is currently pressed."""
        return self.sw.value() == 0
