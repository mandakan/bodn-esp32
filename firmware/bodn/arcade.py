# bodn/arcade.py — Arcade button driver (switch input + LED output)
#
# Combines MCP23017 switch reads with PCA9685 LED PWM control.
# Each arcade button has an active-low switch and an independently
# controllable LED (12-bit PWM for smooth dimming/pulsing/fading).
#
# When the native _mcpinput C module is available with led_anim(),
# all animation is computed at 500 Hz by the scan task on core 0.
# Python sets the animation mode per channel; C handles the math
# and I2C writes.  Game modes need no changes — they call the same
# semantic methods (on, off, glow, pulse, wave, flash, etc.).
#
# Without the C module, the fallback computes duties in Python and
# writes via PCA9685 I2C (same as before the C engine existed).

from micropython import const

_N_BUTTONS = const(5)
_MAX_DUTY = const(4095)

# Brightness presets (pre-computed as 12-bit duty)
_GLOW_DUTY = const(192)  # 12/255 * 4095 ≈ 192

# Try to detect C LED engine
try:
    import _mcpinput

    _native = hasattr(_mcpinput, "led_anim")
except ImportError:
    _native = False


class ArcadeButtons:
    """Driver for 5 illuminated arcade buttons.

    Switch inputs come from MCPPin objects (active-low with pull-ups).
    LED outputs go through PCA9685 PWM channels (or C engine when available).
    """

    def __init__(self, mcp, mcp_pins, pwm=None, pwm_channels=None):
        self._pins = [mcp.pin(p) for p in mcp_pins]
        self._pwm = pwm
        self._channels = pwm_channels or []
        self._ch_start = self._channels[0] if self._channels else 0
        # Native C engine flag — when True, all animation runs in C
        self._native = _native
        # Python-fallback state (only used when _native is False)
        self._duty = [0] * _N_BUTTONS
        self._target = [0] * _N_BUTTONS
        self._flash_ttl = [0] * _N_BUTTONS
        self._pulse_start = [-1] * _N_BUTTONS

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
        """Write changed LED duties to PCA9685.

        When C engine is active, this is a no-op — the scan task
        writes I2C at 500 Hz automatically.
        """
        if self._native or not self._pwm:
            return
        duty = self._duty
        target = self._target
        channels = self._channels
        n_ch = len(channels)
        dirty = False
        for i in range(_N_BUTTONS):
            if target[i] != duty[i]:
                dirty = True
                break
        if not dirty:
            return
        t0 = target[0]
        uniform = True
        for i in range(1, _N_BUTTONS):
            if target[i] != t0:
                uniform = False
                break
        if uniform and n_ch == _N_BUTTONS:
            self._pwm.set_duty_batch(self._ch_start, target)
        else:
            for i in range(_N_BUTTONS):
                if target[i] != duty[i] and i < n_ch:
                    self._pwm.set_duty(channels[i], target[i])
        for i in range(_N_BUTTONS):
            duty[i] = target[i]

    # --- Semantic LED states ---

    def off(self, index):
        """LED dark — button not relevant in current context."""
        if self._native:
            _mcpinput.led_anim(index, _mcpinput.ANIM_OFF)
        else:
            self._target[index] = 0
            self._pulse_start[index] = -1

    def all_off(self):
        """Turn off all arcade LEDs."""
        if self._native:
            _mcpinput.led_anim_all(_mcpinput.ANIM_OFF)
        else:
            for i in range(_N_BUTTONS):
                self._target[i] = 0
                self._pulse_start[i] = -1

    def glow(self, index):
        """Dim standby — button available but not actively needed."""
        if self._native:
            _mcpinput.led_anim(index, _mcpinput.ANIM_GLOW)
        else:
            self._target[index] = _GLOW_DUTY
            self._pulse_start[index] = -1

    def all_glow(self):
        """All LEDs to dim standby."""
        if self._native:
            _mcpinput.led_anim_all(_mcpinput.ANIM_GLOW)
        else:
            for i in range(_N_BUTTONS):
                self._target[i] = _GLOW_DUTY
                self._pulse_start[i] = -1

    def on(self, index):
        """Bright solid — active / pressed / selected."""
        if self._native:
            _mcpinput.led_anim(index, _mcpinput.ANIM_ON)
        else:
            self._target[index] = _MAX_DUTY
            self._pulse_start[index] = -1

    def all_on(self):
        """All LEDs bright solid."""
        if self._native:
            _mcpinput.led_anim_all(_mcpinput.ANIM_ON)
        else:
            for i in range(_N_BUTTONS):
                self._target[i] = _MAX_DUTY
                self._pulse_start[i] = -1

    def pulse(self, index, frame, speed=2):
        """Smooth triangle-wave breathing — "press me" / awaiting input."""
        if self._native:
            _mcpinput.led_anim(index, _mcpinput.ANIM_PULSE, speed)
        else:
            ps = self._pulse_start
            if ps[index] < 0:
                ps[index] = frame
            phase = ((frame - ps[index]) * speed) & 0xFF
            v = phase if phase < 128 else 255 - phase
            self._target[index] = (v * _MAX_DUTY) // 255

    def all_pulse(self, frame, speed=2):
        """Pulse all LEDs in unison."""
        if self._native:
            _mcpinput.led_anim_all(_mcpinput.ANIM_PULSE, speed)
        else:
            phase = (frame * speed) & 0xFF
            v = phase if phase < 128 else 0xFF - phase
            duty = (v * _MAX_DUTY) // 255
            for i in range(_N_BUTTONS):
                self._target[i] = duty
                self._pulse_start[i] = -1

    def blink(self, index, frame, speed=4):
        """Fast on/off flash — alert / urgent attention."""
        if self._native:
            _mcpinput.led_anim(index, _mcpinput.ANIM_BLINK, speed)
        else:
            self._target[index] = _MAX_DUTY if ((frame * speed) >> 5) & 1 else 0
            self._pulse_start[index] = -1

    def all_blink(self, frame, speed=4):
        """Blink all LEDs in unison."""
        if self._native:
            _mcpinput.led_anim_all(_mcpinput.ANIM_BLINK, speed)
        else:
            duty = _MAX_DUTY if ((frame * speed) >> 5) & 1 else 0
            for i in range(_N_BUTTONS):
                self._target[i] = duty
                self._pulse_start[i] = -1

    def wave(self, frame, speed=2, spacing=32):
        """Staggered pulse across all buttons — ripple/wave effect."""
        if self._native:
            _mcpinput.led_anim_all(_mcpinput.ANIM_WAVE, speed)
        else:
            target = self._target
            for i in range(_N_BUTTONS):
                phase = ((frame * speed) - i * spacing) & 0xFF
                v = phase if phase < 128 else 255 - phase
                target[i] = (v * _MAX_DUTY) // 255

    def flash(self, index, duration=9):
        """Start a single bright burst that auto-decays over `duration` frames.

        Call tick_flash() every frame to animate the decay.
        """
        if self._native:
            _mcpinput.led_flash(index, duration)
        else:
            self._flash_ttl[index] = duration
            self._target[index] = _MAX_DUTY
            self._pulse_start[index] = -1

    def tick_flash(self):
        """Advance flash decay for all buttons. Call once per frame.

        Returns True if any flash is still active.
        """
        if self._native:
            return _mcpinput.led_tick_flash()
        active = False
        target = self._target
        for i in range(_N_BUTTONS):
            ttl = self._flash_ttl[i]
            if ttl > 0:
                ttl -= 1
                self._flash_ttl[i] = ttl
                if ttl > 0:
                    target[i] = (ttl * _MAX_DUTY) // 9
                    active = True
                else:
                    target[i] = 0
        return active

    # --- Raw LED control (low-level, Python fallback only) ---

    def set_led(self, index, brightness):
        """Set target LED brightness for one arcade button (0–255)."""
        self._target[index] = (brightness * _MAX_DUTY) // 255 if brightness > 0 else 0

    def set_all_leds(self, brightness):
        """Set all 5 arcade LEDs to the same target brightness (0–255)."""
        duty = (brightness * _MAX_DUTY) // 255 if brightness > 0 else 0
        for i in range(_N_BUTTONS):
            self._target[i] = duty

    def set_led_duty(self, index, duty):
        """Set target raw 12-bit PWM duty for one arcade LED (0–4095)."""
        self._target[index] = duty

    def get_led_duty(self, index):
        """Return the target duty for an arcade LED."""
        return self._target[index]

    # Legacy alias
    def pulse_led(self, index, frame, speed=2):
        """Alias for pulse() — kept for backward compatibility."""
        self.pulse(index, frame, speed)
