# bodn/encoder.py — IRQ-based rotary encoder reader
from machine import Pin


class Encoder:
    """Reads a KY-040 rotary encoder using hardware interrupts.

    value increments/decrements on each detent. Read it from the main loop.
    """

    def __init__(self, clk_pin, dt_pin, sw_pin):
        self.clk = Pin(clk_pin, Pin.IN, Pin.PULL_UP)
        self.dt = Pin(dt_pin, Pin.IN, Pin.PULL_UP)
        self.sw = Pin(sw_pin, Pin.IN, Pin.PULL_UP)
        self.value = 0
        self._last_clk = self.clk.value()
        self.clk.irq(
            trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING,
            handler=self._on_clk,
        )

    def _on_clk(self, pin):
        clk_val = self.clk.value()
        if clk_val != self._last_clk:
            if clk_val != self.dt.value():
                self.value += 1
            else:
                self.value -= 1
            self._last_clk = clk_val

    def pressed(self):
        """Return True if the encoder button is currently pressed."""
        return self.sw.value() == 0
