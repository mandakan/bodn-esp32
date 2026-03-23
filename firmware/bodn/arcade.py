# bodn/arcade.py — Arcade button driver (switch input + LED output)
#
# Combines MCP23017 switch reads with PCA9685 LED PWM control.
# Each arcade button has an active-low switch and an independently
# controllable LED (12-bit PWM for smooth dimming/pulsing/fading).

from micropython import const

_N_BUTTONS = const(5)
_MAX_DUTY = const(4095)


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

    # --- LED control ---

    def set_led(self, index, brightness):
        """Set LED brightness for one arcade button.

        Args:
            index: button index (0–4).
            brightness: 0 (off) to 255 (full on).
        """
        duty = (brightness * _MAX_DUTY) // 255 if brightness > 0 else 0
        self._duty[index] = duty
        if self._pwm and index < len(self._channels):
            self._pwm.set_duty(self._channels[index], duty)

    def set_all_leds(self, brightness):
        """Set all 5 arcade LEDs to the same brightness (0–255)."""
        for i in range(_N_BUTTONS):
            self.set_led(i, brightness)

    def set_led_duty(self, index, duty):
        """Set raw 12-bit PWM duty for one arcade LED (0–4095).

        Use this for precise control (e.g. smooth fading in a game loop).
        """
        self._duty[index] = duty
        if self._pwm and index < len(self._channels):
            self._pwm.set_duty(self._channels[index], duty)

    def get_led_duty(self, index):
        """Return the last-set duty for an arcade LED."""
        return self._duty[index]

    def all_off(self):
        """Turn off all arcade LEDs."""
        self.set_all_leds(0)

    def pulse_led(self, index, frame, speed=2):
        """Smooth triangle-wave pulse on one LED, driven by frame counter.

        Call every frame for animation. Speed controls pulse rate
        (higher = faster, 1–8 typical).
        """
        phase = (frame * speed) & 0xFF
        v = phase if phase < 128 else 255 - phase
        self.set_led(index, v)
