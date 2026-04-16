# bodn/arcade.py — Arcade button driver (switch input + LED output)
#
# Combines MCP23017 switch reads with PCA9685 LED PWM control.
# Each arcade button has an active-low switch and an independently
# controllable LED (12-bit PWM for smooth dimming/pulsing/fading).
#
# All animation is computed at 500 Hz by the _mcpinput C scan task
# on core 0.  Python sets the animation mode per channel; C handles
# the math and I2C writes.  Game modes call semantic methods
# (on, off, glow, pulse, wave, flash, etc.).

from micropython import const

import _mcpinput

_N_BUTTONS = const(5)


class ArcadeButtons:
    """Driver for 5 illuminated arcade buttons.

    Switch inputs come from MCPPin objects (active-low with pull-ups).
    LED outputs go through the _mcpinput C engine driving PCA9685 PWM.
    """

    def __init__(self, mcp, mcp_pins, pwm=None, pwm_channels=None):
        self._pins = [mcp.pin(p) for p in mcp_pins]
        self._channels = pwm_channels or []
        self._ch_start = self._channels[0] if self._channels else 0
        if self._channels:
            addr = pwm._addr if pwm else 0x40
            _mcpinput.led_init(
                addr=addr,
                start_ch=self._ch_start,
                n_channels=len(self._channels),
            )

    @property
    def count(self):
        return _N_BUTTONS

    def pin(self, index):
        """Return the MCPPin for arcade button `index` (for InputState)."""
        return self._pins[index]

    @property
    def pins(self):
        """Return all MCPPin objects as a list (for InputState)."""
        return self._pins

    # --- Flush (call once per frame after all LED updates) ---

    def flush(self):
        """No-op — the C scan task writes I2C at 500 Hz automatically."""
        pass

    # --- Semantic LED states ---

    def off(self, index):
        """LED dark — button not relevant in current context."""
        _mcpinput.led_anim(index, _mcpinput.ANIM_OFF)

    def all_off(self):
        """Turn off all arcade LEDs."""
        _mcpinput.led_anim_all(_mcpinput.ANIM_OFF)

    def glow(self, index):
        """Dim standby — button available but not actively needed."""
        _mcpinput.led_anim(index, _mcpinput.ANIM_GLOW)

    def all_glow(self):
        """All LEDs to dim standby."""
        _mcpinput.led_anim_all(_mcpinput.ANIM_GLOW)

    def on(self, index):
        """Bright solid — active / pressed / selected."""
        _mcpinput.led_anim(index, _mcpinput.ANIM_ON)

    def all_on(self):
        """All LEDs bright solid."""
        _mcpinput.led_anim_all(_mcpinput.ANIM_ON)

    def pulse(self, index, frame, speed=2):
        """Smooth triangle-wave breathing — "press me" / awaiting input."""
        _mcpinput.led_anim(index, _mcpinput.ANIM_PULSE, speed)

    def all_pulse(self, frame, speed=2):
        """Pulse all LEDs in unison."""
        _mcpinput.led_anim_all(_mcpinput.ANIM_PULSE, speed)

    def blink(self, index, frame, speed=4):
        """Fast on/off flash — alert / urgent attention."""
        _mcpinput.led_anim(index, _mcpinput.ANIM_BLINK, speed)

    def all_blink(self, frame, speed=4):
        """Blink all LEDs in unison."""
        _mcpinput.led_anim_all(_mcpinput.ANIM_BLINK, speed)

    def wave(self, frame, speed=2, spacing=32):
        """Staggered pulse across all buttons — ripple/wave effect."""
        _mcpinput.led_anim_all(_mcpinput.ANIM_WAVE, speed)

    def flash(self, index, duration=9):
        """Start a single bright burst that auto-decays over `duration` frames.

        Call tick_flash() every frame to animate the decay.
        """
        _mcpinput.led_flash(index, duration)

    def tick_flash(self):
        """Advance flash decay for all buttons. Call once per frame.

        Returns True if any flash is still active.
        """
        return _mcpinput.led_tick_flash()

    # Legacy alias
    def pulse_led(self, index, frame, speed=2):
        """Alias for pulse() — kept for backward compatibility."""
        self.pulse(index, frame, speed)
