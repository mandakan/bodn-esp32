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

# Brightness presets (pre-computed as 12-bit duty)
_GLOW_DUTY = const(192)  # 12/255 * 4095 ≈ 192


class ArcadeButtons:
    """Driver for 5 illuminated arcade buttons.

    Switch inputs come from MCPPin objects (active-low with pull-ups).
    LED outputs go through PCA9685 PWM channels.

    LED writes are deferred: semantic methods update a target buffer,
    and flush() writes only the changed channels to I2C in a single
    batch transaction. Call flush() once per frame after all LED
    updates are done.

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
        # Current duty on hardware (last flushed)
        self._duty = [0] * _N_BUTTONS
        # Desired duty (set by semantic methods, flushed by flush())
        self._target = [0] * _N_BUTTONS
        # Flash state per button: frames remaining (0 = inactive)
        self._flash_ttl = [0] * _N_BUTTONS
        # Per-button pulse start frame (-1 = not pulsing)
        self._pulse_start = [-1] * _N_BUTTONS
        # First arcade channel (for batch writes)
        self._ch_start = self._channels[0] if self._channels else 0
        # When True, C code drives LEDs — flush() becomes a no-op
        self._c_driven = False

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

    def set_c_driven(self, active):
        """Enable/disable C-driven LED mode. When active, flush() is a no-op."""
        self._c_driven = active

    def flush(self):
        """Write changed LED duties to PCA9685 in a single I2C batch.

        Compares target buffer to current hardware state. Only channels
        that actually changed are written, and contiguous dirty channels
        are batched into one I2C transaction.
        """
        if self._c_driven or not self._pwm:
            return
        duty = self._duty
        target = self._target
        channels = self._channels
        n_ch = len(channels)
        # Check if anything changed
        dirty = False
        for i in range(_N_BUTTONS):
            if target[i] != duty[i]:
                dirty = True
                break
        if not dirty:
            return
        # All same value? Use batch write for all 5 in one transaction
        t0 = target[0]
        uniform = True
        for i in range(1, _N_BUTTONS):
            if target[i] != t0:
                uniform = False
                break
        if uniform and n_ch == _N_BUTTONS:
            self._pwm.set_duty_batch(self._ch_start, target)
        else:
            # Write only changed channels individually
            for i in range(_N_BUTTONS):
                if target[i] != duty[i] and i < n_ch:
                    self._pwm.set_duty(channels[i], target[i])
        # Sync current state
        for i in range(_N_BUTTONS):
            duty[i] = target[i]

    # --- Raw LED control (low-level) ---

    def set_led(self, index, brightness):
        """Set target LED brightness for one arcade button (0–255).

        Does not write to I2C — call flush() after all updates.
        """
        self._target[index] = (brightness * _MAX_DUTY) // 255 if brightness > 0 else 0

    def set_all_leds(self, brightness):
        """Set all 5 arcade LEDs to the same target brightness (0–255)."""
        duty = (brightness * _MAX_DUTY) // 255 if brightness > 0 else 0
        target = self._target
        for i in range(_N_BUTTONS):
            target[i] = duty

    def set_led_duty(self, index, duty):
        """Set target raw 12-bit PWM duty for one arcade LED (0–4095)."""
        self._target[index] = duty

    def get_led_duty(self, index):
        """Return the target duty for an arcade LED."""
        return self._target[index]

    # --- Semantic LED states ---
    # Game modes should prefer these over raw set_led calls.
    # All methods update the target buffer; call flush() once per frame.

    def off(self, index):
        """LED dark — button not relevant in current context."""
        self._target[index] = 0
        self._pulse_start[index] = -1

    def all_off(self):
        """Turn off all arcade LEDs."""
        target = self._target
        ps = self._pulse_start
        for i in range(_N_BUTTONS):
            target[i] = 0
            ps[i] = -1

    def glow(self, index):
        """Dim standby — button available but not actively needed."""
        self._target[index] = _GLOW_DUTY
        self._pulse_start[index] = -1

    def all_glow(self):
        """All LEDs to dim standby."""
        target = self._target
        ps = self._pulse_start
        for i in range(_N_BUTTONS):
            target[i] = _GLOW_DUTY
            ps[i] = -1

    def on(self, index):
        """Bright solid — active / pressed / selected."""
        self._target[index] = _MAX_DUTY
        self._pulse_start[index] = -1

    def all_on(self):
        """All LEDs bright solid."""
        target = self._target
        ps = self._pulse_start
        for i in range(_N_BUTTONS):
            target[i] = _MAX_DUTY
            ps[i] = -1

    def pulse(self, index, frame, speed=2):
        """Smooth triangle-wave breathing — "press me" / awaiting input.

        Each button starts its breath cycle from zero when it first
        enters pulse mode. Call every frame for animation.
        Speed 1=slow, 4=fast, 8=urgent.
        """
        ps = self._pulse_start
        if ps[index] < 0:
            ps[index] = frame
        phase = ((frame - ps[index]) * speed) & 0xFF
        v = phase if phase < 128 else 255 - phase
        self._target[index] = (v * _MAX_DUTY) // 255

    def all_pulse(self, frame, speed=2):
        """Pulse all LEDs in unison (synchronized, no per-button offset)."""
        phase = (frame * speed) & 0xFF
        v = phase if phase < 128 else 0xFF - phase
        duty = (v * _MAX_DUTY) // 255
        target = self._target
        ps = self._pulse_start
        for i in range(_N_BUTTONS):
            target[i] = duty
            ps[i] = -1

    def blink(self, index, frame, speed=4):
        """Fast on/off flash — alert / urgent attention.

        Call every frame. Speed controls blink rate (higher = faster).
        """
        self._target[index] = _MAX_DUTY if ((frame * speed) >> 5) & 1 else 0
        self._pulse_start[index] = -1

    def wave(self, frame, speed=2, spacing=32):
        """Staggered pulse across all buttons — ripple/wave effect.

        Each button is offset by `spacing` phase steps from its neighbour,
        creating a left-to-right wave. Speed and spacing control the look:
        small spacing = tight wave, large spacing = loose cascade.
        """
        target = self._target
        for i in range(_N_BUTTONS):
            phase = ((frame * speed) - i * spacing) & 0xFF
            v = phase if phase < 128 else 255 - phase
            target[i] = (v * _MAX_DUTY) // 255

    def all_blink(self, frame, speed=4):
        """Blink all LEDs in unison."""
        duty = _MAX_DUTY if ((frame * speed) >> 5) & 1 else 0
        target = self._target
        ps = self._pulse_start
        for i in range(_N_BUTTONS):
            target[i] = duty
            ps[i] = -1

    def flash(self, index, duration=9):
        """Start a single bright burst that decays over `duration` frames.

        Call tick_flash() every frame to animate the decay.
        """
        self._flash_ttl[index] = duration
        self._target[index] = _MAX_DUTY
        self._pulse_start[index] = -1

    def tick_flash(self):
        """Advance flash decay for all buttons. Call once per frame.

        Returns True if any flash is still active.
        """
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

    # Legacy alias
    def pulse_led(self, index, frame, speed=2):
        """Alias for pulse() — kept for backward compatibility."""
        self.pulse(index, frame, speed)
