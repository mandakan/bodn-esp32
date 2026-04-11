# bodn/mystery_rules.py — Mystery Box rule engine (pure logic, testable on host)
#
# Each rule set is a dict describing how inputs map to outputs.
# The engine tracks input history and evaluates rules to produce
# visual feedback (color, animation type, LED pattern).
#
# Switches and encoder B act as mystery modifiers:
#   SW0: invert colors (red↔cyan, green↔magenta, etc.)
#   SW1: mirror LED pattern (both halves identical)
#   ENC_B: hue shift — rotates output colors around the wheel

from micropython import const
from bodn.patterns import N_STICKS, scale, _led_buf, _BLACK

# Output types
OUT_IDLE = const(0)
OUT_SINGLE = const(1)  # single button → solid color
OUT_MIX = const(2)  # two-button combo → blended color
OUT_MAGIC = const(3)  # special combo → sparkle animation

# Timing (milliseconds, wall-clock, frame-rate independent)
COMBO_WINDOW_MS = const(1000)  # combo detection window
DISPLAY_HOLD_MS = const(1500)  # how long an output stays visible
MAGIC_HOLD_MS = const(2500)  # how long magic combos stay visible


def mix_rgb(a, b):
    """Blend two RGB tuples by averaging."""
    return ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2, (a[2] + b[2]) // 2)


def _pair_key(a, b):
    """Create a canonical key for a button pair (smaller index first)."""
    return (min(a, b), max(a, b))


def _invert_rgb(c):
    """Invert an RGB color."""
    return (255 - c[0], 255 - c[1], 255 - c[2])


def _shift_hue(c, amount):
    """Rotate RGB channels by an amount (0-255). Simple channel rotation."""
    if amount == 0:
        return c
    r, g, b = c
    # Shift by rotating through 3 zones of 85 each
    zone = (amount * 3) >> 8  # 0, 1, or 2
    frac = (amount * 3) & 0xFF
    inv = 255 - frac
    if zone == 0:
        # R→G transition
        return (
            (r * inv + g * frac) >> 8,
            (g * inv + b * frac) >> 8,
            (b * inv + r * frac) >> 8,
        )
    elif zone == 1:
        # G→B transition
        return (
            (r * inv + b * frac) >> 8,
            (g * inv + r * frac) >> 8,
            (b * inv + g * frac) >> 8,
        )
    else:
        # B→R transition
        return (
            (r * inv + g * frac) >> 8,
            (g * inv + b * frac) >> 8,
            (b * inv + r * frac) >> 8,
        )


# --- Rule set: Color Alchemy ---
# Magic pairs: sorted tuple of button indices → result color override
COLOR_ALCHEMY_MAGIC = {
    (0, 2): (128, 0, 255),  # Red + Blue → Purple
    (0, 3): (255, 128, 0),  # Red + Yellow → Orange
    (2, 3): (0, 200, 100),  # Blue + Yellow → Teal-Green
    (0, 1): (255, 215, 0),  # Red + Green → Gold
    (4, 5): (255, 255, 255),  # Cyan + Magenta → White
    (1, 2): (0, 128, 128),  # Green + Blue → Teal
    (6, 7): (255, 100, 200),  # Orange + Purple → Pink
    (3, 4): (180, 255, 180),  # Yellow + Cyan → Mint
}

# Base colors per button (same as theme.BTN_RGB)
BASE_COLORS = [
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 255, 0),
    (0, 255, 255),
    (255, 0, 255),
    (255, 128, 0),
    (128, 0, 255),
]


class MysteryEngine:
    """Stateful rule engine that tracks inputs and produces outputs.

    Pure logic — no hardware imports. Feed it button presses each tick
    with dt (ms) and read back the current output state.

    Modifiers (switches and encoder) transform the output color and
    LED pattern, multiplying the discovery space without adding rules.
    """

    def __init__(self, colors=None, magic_pairs=None):
        self.colors = colors or BASE_COLORS
        self.magic = magic_pairs or COLOR_ALCHEMY_MAGIC
        # State
        self._last_btn = -1
        self._last_btn_ms = 0  # ms since last button press
        self._output = OUT_IDLE
        self._output_color = (0, 0, 0)
        self._output_ms = 0  # ms since output was set
        self._discoveries = set()  # tuple keys of combos discovered
        # Modifier state (set by caller each frame)
        self.sw_invert = False
        self.sw_mirror = False
        self.hue_shift = 0  # 0-255 from encoder B

    @property
    def output_type(self):
        return self._output

    @property
    def output_color(self):
        return self._output_color

    @property
    def display_color(self):
        """Output color after modifier transforms (for screen display)."""
        return self._apply_color_mods(self._output_color)

    @property
    def discoveries(self):
        return self._discoveries

    @property
    def discovery_count(self):
        return len(self._discoveries)

    @property
    def total_discoverable(self):
        """Total unique outputs: 8 singles + N magic combos."""
        return len(self.colors) + len(self.magic)

    def _apply_color_mods(self, c):
        """Apply switch/encoder modifiers to a color."""
        if self.sw_invert:
            c = _invert_rgb(c)
        if self.hue_shift > 0:
            c = _shift_hue(c, self.hue_shift)
        return c

    def update(self, btn_pressed, dt):
        """Call every tick with the index of a just-pressed button (-1 if none).

        Args:
            btn_pressed -- button index (0–7), -1 if none
            dt          -- milliseconds since last tick

        Returns (output_type, color_rgb) for the current frame.
        """
        self._output_ms += dt
        self._last_btn_ms += dt

        hold = MAGIC_HOLD_MS if self._output == OUT_MAGIC else DISPLAY_HOLD_MS

        # Check if current output has expired
        if self._output != OUT_IDLE and self._output_ms > hold:
            self._output = OUT_IDLE
            self._output_color = (0, 0, 0)

        # Check if combo window expired (reset last button)
        if self._last_btn >= 0 and self._last_btn_ms > COMBO_WINDOW_MS:
            self._last_btn = -1

        if btn_pressed < 0:
            return self._output, self._output_color

        # A button was pressed
        if self._last_btn >= 0 and self._last_btn != btn_pressed:
            # Second button within combo window → try combo
            pair = _pair_key(self._last_btn, btn_pressed)
            if pair in self.magic:
                # Magic combo!
                self._output = OUT_MAGIC
                self._output_color = self.magic[pair]
                self._discoveries.add(pair)
            else:
                # Regular mix
                c1 = self.colors[self._last_btn]
                c2 = self.colors[btn_pressed]
                self._output = OUT_MIX
                self._output_color = mix_rgb(c1, c2)
            self._output_ms = 0
            self._last_btn = -1
        else:
            # First button (or same button again)
            self._output = OUT_SINGLE
            self._output_color = self.colors[btn_pressed]
            self._output_ms = 0
            self._last_btn = btn_pressed
            self._last_btn_ms = 0
            # Track single-color discoveries too
            self._discoveries.add((btn_pressed,))

        return self._output, self._output_color

    def make_static_leds(self, brightness=128):
        """Generate static LED colors for the current output state.

        No animation — solid colors only. Writes into the shared _led_buf.
        Applies modifier transforms (invert, hue shift, mirror).
        """
        buf = _led_buf
        n = N_STICKS
        if self._output == OUT_IDLE:
            idle_color = self._apply_color_mods((60, 20, 80))
            c = scale(idle_color, brightness // 3)
            for i in range(n):
                buf[i] = c
            return buf

        color = self._apply_color_mods(self._output_color)
        c = scale(color, brightness)

        # All active output types use the same solid fill
        for i in range(n):
            buf[i] = c

        # Mirror: copy first half to second half (reversed)
        if self.sw_mirror:
            half = n // 2
            for i in range(half):
                buf[n - 1 - i] = buf[i]

        return buf

    def make_leds(self, frame, brightness=128):
        """Generate LED colors for the current output state.

        Writes into the shared _led_buf to avoid per-frame allocations.
        Applies modifier transforms (invert, hue shift, mirror).
        """
        buf = _led_buf
        n = N_STICKS
        black = _BLACK
        if self._output == OUT_IDLE:
            # Gentle single-color breathing
            phase = (frame * 2) & 0xFF
            v = phase if phase < 128 else 255 - phase
            v = (v * brightness) >> 8
            idle_color = self._apply_color_mods((60, 20, 80))
            c = scale(idle_color, v)
            for i in range(n):
                buf[i] = c
            return buf

        # Apply color modifiers to the output
        color = self._apply_color_mods(self._output_color)

        if self._output == OUT_MAGIC:
            # Sparkle: some LEDs bright, rest dim underglow
            glow = scale(color, brightness // 4)
            bright_c = scale(color, brightness)
            for i in range(n):
                v = ((frame * 21 + i * 53) * 131) & 0xFF
                buf[i] = bright_c if v > 200 else glow

        elif self._output == OUT_MIX:
            # Expand from center using output age in ms
            mid = n // 2
            c = scale(color, brightness)
            age = self._output_ms // 33  # rough frame equivalent for animation
            for i in range(n):
                dist = abs(i - mid)
                buf[i] = c if dist <= age else black

        else:
            # OUT_SINGLE: solid flash
            c = scale(color, brightness)
            for i in range(n):
                buf[i] = c

        # Mirror: copy first half to second half (reversed)
        if self.sw_mirror:
            half = n // 2
            for i in range(half):
                buf[n - 1 - i] = buf[i]

        return buf
