# bodn/ui/input.py — unified input state with debouncing

from micropython import const

from bodn.debounce import Debouncer
from bodn.gesture import GestureDetector

_VELOCITY_TIMEOUT_MS = const(200)  # velocity decays to 0 after this idle time


class EncoderAccumulator:
    """Accumulates raw encoder detents into logical units with velocity scaling.

    Consumers instantiate with their own settings. Call update() each frame
    with the raw delta and velocity from InputState.

    Args:
        detents_per_unit: raw detent clicks needed for one logical unit.
        fast_threshold: velocity (steps/s) above which fast_multiplier applies.
        fast_multiplier: detent scaling factor at high velocity.
    """

    def __init__(
        self,
        detents_per_unit=None,
        fast_threshold=400,
        fast_multiplier=2,
        settings=None,
    ):
        if detents_per_unit is not None:
            self._dpu = detents_per_unit
        elif settings:
            from bodn.config import encoder_dpu

            self._dpu = encoder_dpu(settings)
        else:
            self._dpu = 1
        self._fast_thresh = fast_threshold
        self._fast_mult = fast_multiplier
        self._accum = 0

    def update(self, delta, velocity):
        """Feed raw delta and velocity, returns logical units to move."""
        if delta == 0:
            return 0
        if velocity >= self._fast_thresh:
            self._accum += delta * self._fast_mult
        else:
            self._accum += delta
        # Truncate toward zero: extract whole units, keep remainder
        a = self._accum
        dpu = self._dpu
        if a >= dpu:
            units = a // dpu
            self._accum = a - units * dpu
            return units
        if a <= -dpu:
            units = -((-a) // dpu)
            self._accum = a - units * dpu
            return units
        return 0

    def reset(self):
        """Clear accumulated detents (e.g. on screen transition)."""
        self._accum = 0


class BrightnessControl:
    """Velocity-aware brightness from encoder delta.

    Wraps EncoderAccumulator to produce a clamped brightness value.
    Slow turns give fine adjustment; fast spins jump to extremes.

    Args:
        initial: starting brightness (0–255).
        minimum: floor brightness (default 10, never fully off).
        maximum: ceiling brightness (default 255).
        step: brightness change per logical encoder unit.
    """

    def __init__(self, initial=128, minimum=10, maximum=255, step=20, settings=None):
        self._acc = EncoderAccumulator(settings=settings, fast_threshold=400, fast_multiplier=3)
        self._value = initial
        self._min = minimum
        self._max = maximum
        self._step = step
        self._pwm = settings.get("_pwm") if settings else None

    @property
    def value(self):
        return self._value

    def update(self, delta, velocity):
        """Feed encoder delta and velocity; returns current brightness."""
        units = self._acc.update(delta, velocity)
        if units:
            v = self._value + units * self._step
            self._value = min(self._max, max(self._min, v))
            self._update_backlight()
        return self._value

    def _update_backlight(self):
        """Sync display backlight to current brightness via PCA9685."""
        if self._pwm is None:
            return
        from bodn import config

        # Map 0–255 → 0–4095 (12-bit PWM)
        duty = self._value * 16
        if duty > 4095:
            duty = 4095
        self._pwm.set_duty(config.PWM_CH_BACKLIGHT, duty)

    def reset(self, value=None):
        """Reset accumulator; optionally set a new brightness value."""
        self._acc.reset()
        if value is not None:
            self._value = value


class InputState:
    """Wraps buttons, switches, arcade buttons and encoders into a single scannable state.

    Args:
        buttons: list of 8 Pin objects (active-low).
        switches: list of Pin objects (latching toggles, active-low).
        encoders: list of 3 Encoder objects (each has .value, .sw).
        time_ms_fn: callable returning current time in ms.
        arcade_pins: list of Pin objects for arcade buttons (active-low), or [].
    """

    def __init__(self, buttons, switches, encoders, time_ms_fn, arcade_pins=None):
        self._buttons = buttons
        self._switches = switches
        self._encoders = encoders
        self._time_ms = time_ms_fn
        self._arcade_pins = arcade_pins or []

        self._btn_deb = [Debouncer(delay_ms=15) for _ in range(len(buttons))]
        self._enc_btn_deb = [Debouncer(delay_ms=15) for _ in range(len(encoders))]
        self._arc_deb = [Debouncer(delay_ms=10) for _ in range(len(self._arcade_pins))]

        n_btn = len(buttons)
        n_enc = len(encoders)
        n_arc = len(self._arcade_pins)

        # Public state (copied from pending by consume())
        self.btn_held = [False] * n_btn
        self.btn_just_pressed = [False] * n_btn
        self.btn_just_released = [False] * n_btn
        self.sw = [False] * len(switches)
        self.arc_held = [False] * n_arc
        self.arc_just_pressed = [False] * n_arc
        self.arc_just_released = [False] * n_arc
        self.enc_pos = [0] * n_enc
        self.enc_delta = [0] * n_enc
        self.enc_velocity = [0] * n_enc  # steps/second per encoder
        self.enc_btn_held = [False] * n_enc
        self.enc_btn_pressed = [False] * n_enc
        self.enc_btn_just_released = [False] * n_enc
        # Press timestamps (ms) captured by the native scanner.  Only
        # meaningful when the corresponding *_just_pressed flag is True;
        # otherwise the value is stale.  Used by time-sensitive modes
        # (e.g. Sequencer) to quantize live input against the audio clock.
        self.btn_press_ts = [0] * n_btn
        self.arc_press_ts = [0] * n_arc

        # Pending edge-latched state (accumulated by scan, consumed by consume)
        self._pend_btn_press = [False] * n_btn
        self._pend_btn_release = [False] * n_btn
        self._pend_arc_press = [False] * n_arc
        self._pend_arc_release = [False] * n_arc
        self._pend_btn_press_ts = [0] * n_btn
        self._pend_arc_press_ts = [0] * n_arc
        self._pend_enc_btn_press = [False] * n_enc
        self._pend_enc_btn_release = [False] * n_enc
        self._pend_enc_delta = [0] * n_enc

        self._prev_btn = [False] * n_btn
        self._prev_arc = [False] * n_arc
        self._prev_enc_pos = [0] * n_enc
        self._prev_enc_btn = [False] * n_enc
        self._enc_last_step_ms = [0] * n_enc

        # Scan-time press callback: fired at 200 Hz on debounced press edge.
        # Signature: callback(kind, index) where kind is "btn" or "arc".
        self._on_press = None

        # Gesture detection for all buttons + arcade buttons + encoder buttons
        n_total = n_btn + n_arc + n_enc
        self.gestures = GestureDetector(n_total)
        self._g_held = [False] * n_total
        self._g_pressed = [False] * n_total
        self._g_released = [False] * n_total

    def scan(self):
        """Read all inputs and latch edges into pending state.

        Call at a fast rate (~5 ms) from the input task. Edge events
        (press/release) are OR-latched: once set, they stay True until
        consume() copies them to the public arrays and clears them.

        Hot path: indexed `while` loops (no enumerate/range allocation).
        See docs/PERFORMANCE_GUIDELINES.md §"Avoiding GC stalls".
        """
        now = self._time_ms()

        # Cache self.* as locals to avoid repeated dict lookups
        buttons = self._buttons
        btn_deb = self._btn_deb
        btn_held = self.btn_held
        prev_btn = self._prev_btn
        pend_bp = self._pend_btn_press
        pend_br = self._pend_btn_release
        pend_bp_ts = self._pend_btn_press_ts
        on_press = self._on_press

        # Buttons
        n_btn = len(buttons)
        i = 0
        while i < n_btn:
            prev = prev_btn[i]
            cur = btn_deb[i].update(buttons[i].value(), now)
            btn_held[i] = cur
            if cur and not prev:
                pend_bp[i] = True
                pend_bp_ts[i] = now
                if on_press:
                    on_press("btn", i)
            if not cur and prev:
                pend_br[i] = True
            prev_btn[i] = cur
            i += 1

        # Toggle switches (no debounce — physical latching)
        sw = self.sw
        switches = self._switches
        n_sw = len(switches)
        i = 0
        while i < n_sw:
            sw[i] = switches[i].value() == 0
            i += 1

        # Arcade buttons
        arc_pins = self._arcade_pins
        arc_deb = self._arc_deb
        arc_held = self.arc_held
        prev_arc = self._prev_arc
        pend_ap = self._pend_arc_press
        pend_ar = self._pend_arc_release
        pend_ap_ts = self._pend_arc_press_ts

        n_arc = len(arc_pins)
        i = 0
        while i < n_arc:
            prev = prev_arc[i]
            cur = arc_deb[i].update(arc_pins[i].value(), now)
            arc_held[i] = cur
            if cur and not prev:
                pend_ap[i] = True
                pend_ap_ts[i] = now
                if on_press:
                    on_press("arc", i)
            if not cur and prev:
                pend_ar[i] = True
            prev_arc[i] = cur
            i += 1

        # Encoders
        encoders = self._encoders
        enc_pos = self.enc_pos
        enc_velocity = self.enc_velocity
        prev_enc_pos = self._prev_enc_pos
        enc_btn_held = self.enc_btn_held
        prev_enc_btn = self._prev_enc_btn
        enc_btn_deb = self._enc_btn_deb
        enc_last_step = self._enc_last_step_ms
        pend_ed = self._pend_enc_delta
        pend_ep = self._pend_enc_btn_press
        pend_er = self._pend_enc_btn_release

        n_enc = len(encoders)
        i = 0
        while i < n_enc:
            enc = encoders[i]
            pos = enc.value
            enc_pos[i] = pos
            d = pos - prev_enc_pos[i]
            pend_ed[i] += d
            prev_enc_pos[i] = pos

            if d != 0:
                elapsed = now - enc_last_step[i]
                if elapsed > 0:
                    enc_velocity[i] = abs(d) * 1000 // elapsed
                enc_last_step[i] = now
            elif now - enc_last_step[i] > _VELOCITY_TIMEOUT_MS:
                enc_velocity[i] = 0

            p_btn = prev_enc_btn[i]
            cur_btn = enc_btn_deb[i].update(enc.sw.value(), now)
            enc_btn_held[i] = cur_btn
            if cur_btn and not p_btn:
                pend_ep[i] = True
            if not cur_btn and p_btn:
                pend_er[i] = True
            prev_enc_btn[i] = cur_btn
            i += 1

    def native_press(self, kind, index, ts_ms=None):
        """Latch a press edge from native C module events.

        ``ts_ms`` is the scanner's capture timestamp (ms since boot).
        When omitted, falls back to ``self._time_ms()`` — callers that
        have a real timestamp (e.g. from ``_mcpinput.get_events()``)
        should pass it so that time-sensitive modes can compensate for
        the frame-sync delay.
        """
        if ts_ms is None:
            ts_ms = self._time_ms()
        on_press = self._on_press
        if kind == "btn" and index < len(self.btn_held):
            self.btn_held[index] = True
            self._pend_btn_press[index] = True
            self._pend_btn_press_ts[index] = ts_ms
            if on_press:
                on_press("btn", index)
        elif kind == "arc" and index < len(self.arc_held):
            self.arc_held[index] = True
            self._pend_arc_press[index] = True
            self._pend_arc_press_ts[index] = ts_ms
            if on_press:
                on_press("arc", index)

    def native_release(self, kind, index):
        """Latch a release edge from native C module events."""
        if kind == "btn" and index < len(self.btn_held):
            self.btn_held[index] = False
            self._pend_btn_release[index] = True
        elif kind == "arc" and index < len(self.arc_held):
            self.arc_held[index] = False
            self._pend_arc_release[index] = True

    def scan_encoders(self):
        """Scan only encoders and encoder buttons (for native input mode).

        MCP1 buttons/arcade are handled by native_press/native_release.
        MCP2 encoder buttons and toggle switches are still Python-polled.

        Hot path: runs at ~200 Hz from input_scan_task. Use indexed `while`
        loops (no enumerate/range allocation). See PERFORMANCE_GUIDELINES.md.
        """
        now = self._time_ms()

        encoders = self._encoders
        enc_pos = self.enc_pos
        enc_velocity = self.enc_velocity
        prev_enc_pos = self._prev_enc_pos
        enc_btn_held = self.enc_btn_held
        prev_enc_btn = self._prev_enc_btn
        enc_btn_deb = self._enc_btn_deb
        enc_last_step = self._enc_last_step_ms
        pend_ed = self._pend_enc_delta
        pend_ep = self._pend_enc_btn_press
        pend_er = self._pend_enc_btn_release

        n = len(encoders)
        i = 0
        while i < n:
            enc = encoders[i]
            pos = enc.value
            enc_pos[i] = pos
            d = pos - prev_enc_pos[i]
            pend_ed[i] += d
            prev_enc_pos[i] = pos

            if d != 0:
                elapsed = now - enc_last_step[i]
                if elapsed > 0:
                    enc_velocity[i] = abs(d) * 1000 // elapsed
                enc_last_step[i] = now
            elif now - enc_last_step[i] > _VELOCITY_TIMEOUT_MS:
                enc_velocity[i] = 0

            p_btn = prev_enc_btn[i]
            cur_btn = enc_btn_deb[i].update(enc.sw.value(), now)
            enc_btn_held[i] = cur_btn
            if cur_btn and not p_btn:
                pend_ep[i] = True
            if not cur_btn and p_btn:
                pend_er[i] = True
            prev_enc_btn[i] = cur_btn
            i += 1

    def set_on_press(self, callback):
        """Register a callback fired from scan() on debounced press edge.

        Signature: callback(kind, index) where kind is "btn" or "arc".
        Runs at scan rate (~200 Hz), bypassing the frame sync delay.
        Callback must be fast — no I2C, no allocations.
        Pass None to clear.
        """
        self._on_press = callback

    def consume(self):
        """Copy latched edges to public state and clear pending.

        Call once per display frame from ScreenManager.tick(). This ensures
        that fast scans (200 Hz) feed into the slower display loop (~30 Hz)
        without losing short button presses.

        Hot path: called every render frame. Uses indexed `while` loops to
        avoid allocating range() iterators per call.
        """
        now = self._time_ms()
        n_btn = len(self._buttons)
        n_arc = len(self._arcade_pins)
        n_enc = len(self._encoders)

        # Buttons: copy latched edges, clear pending
        pend_bp = self._pend_btn_press
        pend_br = self._pend_btn_release
        pend_bp_ts = self._pend_btn_press_ts
        bjp = self.btn_just_pressed
        bjr = self.btn_just_released
        bp_ts = self.btn_press_ts
        i = 0
        while i < n_btn:
            bjp[i] = pend_bp[i]
            bjr[i] = pend_br[i]
            if pend_bp[i]:
                bp_ts[i] = pend_bp_ts[i]
            pend_bp[i] = False
            pend_br[i] = False
            i += 1

        # Arcade buttons
        pend_ap = self._pend_arc_press
        pend_ar = self._pend_arc_release
        pend_ap_ts = self._pend_arc_press_ts
        ajp = self.arc_just_pressed
        ajr = self.arc_just_released
        ap_ts = self.arc_press_ts
        i = 0
        while i < n_arc:
            ajp[i] = pend_ap[i]
            ajr[i] = pend_ar[i]
            if pend_ap[i]:
                ap_ts[i] = pend_ap_ts[i]
            pend_ap[i] = False
            pend_ar[i] = False
            i += 1

        # Encoder deltas (sum across scans) and buttons
        pend_ed = self._pend_enc_delta
        pend_ep = self._pend_enc_btn_press
        pend_er = self._pend_enc_btn_release
        ed = self.enc_delta
        ebp = self.enc_btn_pressed
        ebjr = self.enc_btn_just_released
        i = 0
        while i < n_enc:
            ed[i] = pend_ed[i]
            pend_ed[i] = 0
            ebp[i] = pend_ep[i]
            ebjr[i] = pend_er[i]
            pend_ep[i] = False
            pend_er[i] = False
            i += 1

        # Update gesture detector with consumed state
        gh = self._g_held
        gp = self._g_pressed
        gr = self._g_released
        bh = self.btn_held
        ah = self.arc_held
        ebh = self.enc_btn_held
        i = 0
        while i < n_btn:
            gh[i] = bh[i]
            gp[i] = bjp[i]
            gr[i] = bjr[i]
            i += 1
        off = n_btn
        i = 0
        while i < n_arc:
            gh[off + i] = ah[i]
            gp[off + i] = ajp[i]
            gr[off + i] = ajr[i]
            i += 1
        off += n_arc
        i = 0
        while i < n_enc:
            gh[off + i] = ebh[i]
            gp[off + i] = ebp[i]
            gr[off + i] = ebjr[i]
            i += 1
        self.gestures.update(gh, gp, gr, now)

    def resync_encoders(self):
        """Resync encoder baselines to current positions, discarding any delta.

        Call after waking from sleep — the PCNT hardware keeps counting
        during light sleep, producing a spurious delta on the first scan.
        """
        for i, enc in enumerate(self._encoders):
            pos = enc.value
            self._prev_enc_pos[i] = pos
            self.enc_pos[i] = pos
            self._pend_enc_delta[i] = 0
            self.enc_delta[i] = 0
            self.enc_velocity[i] = 0

    def has_activity(self):
        """Return True if any input changed this frame (for idle tracking).

        Hot path: called every frame. Indexed loops avoid the genexp
        (`any(d != 0 for d in ...)`) and the iterators that ``any(list)``
        otherwise creates -- both are fresh allocations per call.
        """
        bjp = self.btn_just_pressed
        bjr = self.btn_just_released
        n = len(bjp)
        i = 0
        while i < n:
            if bjp[i] or bjr[i]:
                return True
            i += 1
        ajp = self.arc_just_pressed
        ajr = self.arc_just_released
        n = len(ajp)
        i = 0
        while i < n:
            if ajp[i] or ajr[i]:
                return True
            i += 1
        ed = self.enc_delta
        n = len(ed)
        i = 0
        while i < n:
            if ed[i]:
                return True
            i += 1
        ebp = self.enc_btn_pressed
        n = len(ebp)
        i = 0
        while i < n:
            if ebp[i]:
                return True
            i += 1
        return False

    def any_btn_pressed(self):
        """Return True if any mini button was just pressed this frame."""
        return any(self.btn_just_pressed)

    def first_btn_pressed(self):
        """Return index of the first just-pressed mini button, or -1."""
        for i, p in enumerate(self.btn_just_pressed):
            if p:
                return i
        return -1

    def any_arc_pressed(self):
        """Return True if any arcade button was just pressed this frame."""
        return any(self.arc_just_pressed)

    def first_arc_pressed(self):
        """Return index of the first just-pressed arcade button, or -1."""
        for i, p in enumerate(self.arc_just_pressed):
            if p:
                return i
        return -1

    def gesture_arc(self, arc_idx):
        """Return gesture channel index for an arcade button."""
        return len(self._buttons) + arc_idx

    def gesture_enc(self, enc_idx):
        """Return gesture channel index for an encoder button."""
        return len(self._buttons) + len(self._arcade_pins) + enc_idx
