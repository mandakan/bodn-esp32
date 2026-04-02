# bodn/arcade.py — Arcade button driver (switch input + LED output)
#
# Combines MCP23017 switch reads with PCA9685 LED PWM control.
# Each arcade button has an active-low switch and an independently
# controllable LED (12-bit PWM for smooth dimming/pulsing/fading).
#
# Game modes use semantic LED states instead of raw brightness values:
#   off()       — LED dark (not relevant in current context)
#   glow()      — dim standby (available but not needed now)
#   on()        — bright solid (active / pressed feedback)
#   pulse()     — smooth breathing ("press me" / awaiting input)
#   blink()     — fast flash (alert / urgent attention)
#   flash()     — single bright burst that auto-decays over N frames

from micropython import const

_N_BUTTONS = const(5)
_MAX_DUTY = const(4095)

# Brightness presets (0–255)
_GLOW = const(12)
_ON = const(255)


class ArcadeButtons:
    """Driver for 5 illuminated arcade buttons.

    Switch inputs come from MCPPin objects (active-low with pull-ups).
    LED outputs go through PCA9685 PWM channels.

    Args:
        mcp: MCP23017 instance.
        mcp_pins: list of 5 MCP23017 pin numbers for switch contacts.
        pwm: PCA9685 instance (or None if PWM board not found).
        pwm_channels: list of 5 PCA9685 channel numbers for LEDs.
    """

    def __init__(self, mcp, mcp_pins, pwm=None, pwm_channels=None):
        self._pins = [mcp.pin(p) for p in mcp_pins]
        self._pwm = pwm
        self._channels = pwm_channels or []
        self._duty = [0] * _N_BUTTONS
        # Flash state per button: frames remaining (0 = inactive)
        self._flash_ttl = [0] * _N_BUTTONS

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

    # --- Raw LED control (low-level) ---

    def set_led(self, index, brightness):
        """Set LED brightness for one arcade button (0–255)."""
        duty = (brightness * _MAX_DUTY) // 255 if brightness > 0 else 0
        self._duty[index] = duty
        if self._pwm and index < len(self._channels):
            self._pwm.set_duty(self._channels[index], duty)

    def set_all_leds(self, brightness):
        """Set all 5 arcade LEDs to the same brightness (0–255)."""
        for i in range(_N_BUTTONS):
            self.set_led(i, brightness)

    def set_led_duty(self, index, duty):
        """Set raw 12-bit PWM duty for one arcade LED (0–4095)."""
        self._duty[index] = duty
        if self._pwm and index < len(self._channels):
            self._pwm.set_duty(self._channels[index], duty)

    def get_led_duty(self, index):
        """Return the last-set duty for an arcade LED."""
        return self._duty[index]

    # --- Semantic LED states ---
    # Game modes should prefer these over raw set_led calls.
    # Animated states (pulse, blink, flash) must be called every frame.

    def off(self, index):
        """LED dark — button not relevant in current context."""
        self.set_led(index, 0)

    def all_off(self):
        """Turn off all arcade LEDs."""
        self.set_all_leds(0)

    def glow(self, index):
        """Dim standby — button available but not actively needed."""
        self.set_led(index, _GLOW)

    def all_glow(self):
        """All LEDs to dim standby."""
        self.set_all_leds(_GLOW)

    def on(self, index):
        """Bright solid — active / pressed / selected."""
        self.set_led(index, _ON)

    def all_on(self):
        """All LEDs bright solid."""
        self.set_all_leds(_ON)

    def pulse(self, index, frame, speed=2):
        """Smooth triangle-wave breathing — "press me" / awaiting input.

        Call every frame for animation. Speed 1=slow, 4=fast, 8=urgent.
        """
        phase = (frame * speed) & 0xFF
        v = phase if phase < 128 else 255 - phase
        self.set_led(index, v)

    def all_pulse(self, frame, speed=2):
        """Pulse all LEDs in unison."""
        phase = (frame * speed) & 0xFF
        v = phase if phase < 128 else 0xFF - phase
        self.set_all_leds(v)

    def blink(self, index, frame, speed=4):
        """Fast on/off flash — alert / urgent attention.

        Call every frame. Speed controls blink rate (higher = faster).
        """
        on = ((frame * speed) >> 5) & 1
        self.set_led(index, _ON if on else 0)

    def all_blink(self, frame, speed=4):
        """Blink all LEDs in unison."""
        on = ((frame * speed) >> 5) & 1
        self.set_all_leds(_ON if on else 0)

    def flash(self, index, duration=9):
        """Start a single bright burst that decays over `duration` frames.

        Call tick_flash() every frame to animate the decay.
        """
        self._flash_ttl[index] = duration
        self.set_led(index, _ON)

    def tick_flash(self):
        """Advance flash decay for all buttons. Call once per frame.

        Returns True if any flash is still active.
        """
        active = False
        for i in range(_N_BUTTONS):
            ttl = self._flash_ttl[i]
            if ttl > 0:
                ttl -= 1
                self._flash_ttl[i] = ttl
                if ttl > 0:
                    self.set_led(i, (ttl * _ON) // 9)
                    active = True
                else:
                    self.set_led(i, 0)
        return active

    # Legacy alias
    def pulse_led(self, index, frame, speed=2):
        """Alias for pulse() — kept for backward compatibility."""
        self.pulse(index, frame, speed)
