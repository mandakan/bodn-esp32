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
        self._acc = EncoderAccumulator(
            settings=settings, fast_threshold=400, fast_multiplier=3
        )
        self._value = initial
        self._min = minimum
        self._max = maximum
        self._step = step

    @property
    def value(self):
        return self._value

    def update(self, delta, velocity):
        """Feed encoder delta and velocity; returns current brightness."""
        units = self._acc.update(delta, velocity)
        if units:
            v = self._value + units * self._step
            self._value = min(self._max, max(self._min, v))
        return self._value

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

        # Pending edge-latched state (accumulated by scan, consumed by consume)
        self._pend_btn_press = [False] * n_btn
        self._pend_btn_release = [False] * n_btn
        self._pend_arc_press = [False] * n_arc
        self._pend_arc_release = [False] * n_arc
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
        """
        now = self._time_ms()

        # Cache self.* as locals to avoid repeated dict lookups
        buttons = self._buttons
        btn_deb = self._btn_deb
        btn_held = self.btn_held
        prev_btn = self._prev_btn
        pend_bp = self._pend_btn_press
        pend_br = self._pend_btn_release
        on_press = self._on_press

        # Buttons
        for i, btn in enumerate(buttons):
            prev = prev_btn[i]
            cur = btn_deb[i].update(btn.value(), now)
            btn_held[i] = cur
            if cur and not prev:
                pend_bp[i] = True
                if on_press:
                    on_press("btn", i)
            if not cur and prev:
                pend_br[i] = True
            prev_btn[i] = cur

        # Toggle switches (no debounce — physical latching)
        sw = self.sw
        for i, switch in enumerate(self._switches):
            sw[i] = switch.value() == 0

        # Arcade buttons
        arc_pins = self._arcade_pins
        arc_deb = self._arc_deb
        arc_held = self.arc_held
        prev_arc = self._prev_arc
        pend_ap = self._pend_arc_press
        pend_ar = self._pend_arc_release

        for i, pin in enumerate(arc_pins):
            prev = prev_arc[i]
            cur = arc_deb[i].update(pin.value(), now)
            arc_held[i] = cur
            if cur and not prev:
                pend_ap[i] = True
                if on_press:
                    on_press("arc", i)
            if not cur and prev:
                pend_ar[i] = True
            prev_arc[i] = cur

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

        for i, enc in enumerate(encoders):
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
        """
        now = self._time_ms()
        n_btn = len(self._buttons)
        n_arc = len(self._arcade_pins)
        n_enc = len(self._encoders)

        # Buttons: copy latched edges, clear pending
        pend_bp = self._pend_btn_press
        pend_br = self._pend_btn_release
        bjp = self.btn_just_pressed
        bjr = self.btn_just_released
        for i in range(n_btn):
            bjp[i] = pend_bp[i]
            bjr[i] = pend_br[i]
            pend_bp[i] = False
            pend_br[i] = False

        # Arcade buttons
        pend_ap = self._pend_arc_press
        pend_ar = self._pend_arc_release
        ajp = self.arc_just_pressed
        ajr = self.arc_just_released
        for i in range(n_arc):
            ajp[i] = pend_ap[i]
            ajr[i] = pend_ar[i]
            pend_ap[i] = False
            pend_ar[i] = False

        # Encoder deltas (sum across scans) and buttons
        pend_ed = self._pend_enc_delta
        pend_ep = self._pend_enc_btn_press
        pend_er = self._pend_enc_btn_release
        ed = self.enc_delta
        ebp = self.enc_btn_pressed
        ebjr = self.enc_btn_just_released
        for i in range(n_enc):
            ed[i] = pend_ed[i]
            pend_ed[i] = 0
            ebp[i] = pend_ep[i]
            ebjr[i] = pend_er[i]
            pend_ep[i] = False
            pend_er[i] = False

        # Update gesture detector with consumed state
        gh = self._g_held
        gp = self._g_pressed
        gr = self._g_released
        bh = self.btn_held
        ah = self.arc_held
        ebh = self.enc_btn_held
        for i in range(n_btn):
            gh[i] = bh[i]
            gp[i] = bjp[i]
            gr[i] = bjr[i]
        off = n_btn
        for i in range(n_arc):
            gh[off + i] = ah[i]
            gp[off + i] = ajp[i]
            gr[off + i] = ajr[i]
        off += n_arc
        for i in range(n_enc):
            gh[off + i] = ebh[i]
            gp[off + i] = ebp[i]
            gr[off + i] = ebjr[i]
        self.gestures.update(gh, gp, gr, now)

    def has_activity(self):
        """Return True if any input changed this frame (for idle tracking)."""
        if any(self.btn_just_pressed) or any(self.btn_just_released):
            return True
        if any(self.arc_just_pressed) or any(self.arc_just_released):
            return True
        if any(d != 0 for d in self.enc_delta):
            return True
        if any(self.enc_btn_pressed):
            return True
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
