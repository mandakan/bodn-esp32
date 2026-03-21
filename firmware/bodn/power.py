# bodn/power.py — power-save mode with light sleep
#
# IdleTracker: pure logic, testable on host.
# PowerManager: hardware orchestration, device-only.

import time
from micropython import const

_DEFAULT_TIMEOUT_S = const(300)


class IdleTracker:
    """Tracks inactivity and decides when the device should sleep.

    Pure logic — inject time_fn for testability.
    """

    def __init__(self, timeout_s=_DEFAULT_TIMEOUT_S, time_fn=None):
        self._timeout_s = timeout_s
        self._time = time_fn or time.time
        self._last_activity = self._time()
        self._sleeping = False

    @property
    def timeout_s(self):
        return self._timeout_s

    @timeout_s.setter
    def timeout_s(self, val):
        self._timeout_s = max(0, val)

    @property
    def sleeping(self):
        return self._sleeping

    def poke(self):
        """Reset the inactivity timer. Call on any user input."""
        self._last_activity = self._time()
        self._sleeping = False

    def tick(self):
        """Check if we should sleep. Returns True once on transition."""
        if self._sleeping or self._timeout_s == 0:
            return False
        if self._time() - self._last_activity >= self._timeout_s:
            self._sleeping = True
            return True
        return False

    def seconds_until_sleep(self):
        """Seconds remaining until sleep, or 0 if sleeping/disabled."""
        if self._sleeping or self._timeout_s == 0:
            return 0
        elapsed = self._time() - self._last_activity
        return max(0, self._timeout_s - elapsed)

    def wake(self):
        """Call after waking from sleep to reset state."""
        self._last_activity = self._time()
        self._sleeping = False


class PowerManager:
    """Orchestrates light sleep entry and exit.

    Hardware-facing — not testable on host without stubs.
    """

    def __init__(self, tft, tft2, np, mcp):
        self._tft = tft
        self._tft2 = tft2
        self._np = np
        self._mcp = mcp
        self._bl_pin = None

    def pre_sleep(self):
        """Turn off power-hungry peripherals before entering light sleep."""
        from machine import Pin
        from bodn import config

        # Turn off NeoPixels
        for i in range(config.NEOPIXEL_COUNT):
            self._np[i] = (0, 0, 0)
        self._np.write()

        # Turn off display backlight
        self._bl_pin = Pin(config.TFT_BL, Pin.OUT)
        self._bl_pin.value(0)

        # Put displays into sleep mode (SLPIN saves ~5 mA each)
        self._tft._cmd(0x10)
        self._tft2._cmd(0x10)

    def enter_light_sleep(self):
        """Configure wake sources and enter machine.lightsleep()."""
        import machine
        from machine import Pin
        import esp32
        from bodn import config

        # Enable MCP23017 interrupts (any button/toggle change pulls INT low)
        self._mcp.enable_interrupts()

        # Wake sources: MCP INT + encoder buttons (all active-low)
        wake_pins = [
            config.MCP_INT_PIN,
            config.ENC1_SW,
            config.ENC2_SW,
            config.ENC3_SW,
        ]
        for pin_num in wake_pins:
            p = Pin(pin_num, Pin.IN, Pin.PULL_UP)
            esp32.gpio_wakeup(p, esp32.WAKEUP_ANY_LOW)

        # Clear pending MCP interrupts before sleeping
        self._mcp.clear_interrupts()

        print("POWER: entering light sleep")
        machine.lightsleep()
        print("POWER: woke up")

    def post_wake(self):
        """Restore peripherals after waking from light sleep."""
        from machine import Pin
        from bodn import config

        # Clear MCP23017 interrupt state and disable interrupts
        self._mcp.clear_interrupts()
        self._mcp.disable_interrupts()

        # Wake displays (SLPOUT)
        self._tft._cmd(0x11)
        self._tft2._cmd(0x11)
        time.sleep_ms(120)  # displays need ~120 ms after SLPOUT

        # Restore backlight
        self._bl_pin = Pin(config.TFT_BL, Pin.OUT)
        self._bl_pin.value(1)

    def master_switch_off(self):
        """Return True if the master switch is in the OFF position (high = off)."""
        from bodn import config

        self._mcp.refresh()
        return self._mcp.pin_value(config.MCP_MASTER_SW_PIN) == 1

    def sleep_and_wake(self):
        """Full sleep cycle: pre_sleep → lightsleep → post_wake."""
        self.pre_sleep()
        self.enter_light_sleep()
        self.post_wake()

    def sleep_until_master_on(self):
        """Sleep in a loop until the master switch is flipped ON.

        Any wake source (button, encoder) will briefly wake the CPU.
        If the master switch is still OFF, we go right back to sleep.
        """
        self.pre_sleep()
        while True:
            self.enter_light_sleep()
            # Check master switch — if ON now, break out and restore
            if not self.master_switch_off():
                break
            # Still off — clear interrupts and sleep again
            self._mcp.clear_interrupts()
        self.post_wake()
