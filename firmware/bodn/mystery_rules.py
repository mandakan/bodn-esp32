# bodn/mystery_rules.py — Mystery Box rule engine (pure logic, testable on host)
#
# Each rule set is a dict describing how inputs map to outputs.
# The engine tracks input history and evaluates rules to produce
# visual feedback (color, animation type, LED pattern).

from bodn.patterns import N_LEDS, scale, hsv_to_rgb, _led_buf


# Output types
OUT_IDLE = 0
OUT_SINGLE = 1     # single button → solid color
OUT_MIX = 2        # two-button combo → blended color
OUT_MAGIC = 3      # special combo → sparkle animation

# How long a combo window lasts (in frames, ~33 fps)
COMBO_WINDOW = 33   # ~1 second
# How long an output stays visible
DISPLAY_HOLD = 50   # ~1.5 seconds
MAGIC_HOLD = 80     # ~2.5 seconds for magic combos


def mix_rgb(a, b):
    """Blend two RGB tuples by averaging."""
    return ((a[0] + b[0]) // 2, (a[1] + b[1]) // 2, (a[2] + b[2]) // 2)


def _pair_key(a, b):
    """Create a canonical key for a button pair (smaller index first)."""
    return (min(a, b), max(a, b))


# --- Rule set: Color Alchemy ---
# Magic pairs: sorted tuple of button indices → result color override
COLOR_ALCHEMY_MAGIC = {
    (0, 2): (128, 0, 255),    # Red + Blue → Purple
    (0, 3): (255, 128, 0),    # Red + Yellow → Orange
    (2, 3): (0, 200, 100),    # Blue + Yellow → Teal-Green
    (0, 1): (255, 215, 0),    # Red + Green → Gold
    (4, 5): (255, 255, 255),  # Cyan + Magenta → White
    (1, 2): (0, 128, 128),    # Green + Blue → Teal
    (6, 7): (255, 100, 200),  # Orange + Purple → Pink
    (3, 4): (180, 255, 180),  # Yellow + Cyan → Mint
}

# Base colors per button (same as theme.BTN_RGB)
BASE_COLORS = [
    (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
    (0, 255, 255), (255, 0, 255), (255, 128, 0), (128, 0, 255),
]


class MysteryEngine:
    """Stateful rule engine that tracks inputs and produces outputs.

    Pure logic — no hardware imports. Feed it button presses each frame
    and read back the current output state.
    """

    def __init__(self, colors=None, magic_pairs=None):
        self.colors = colors or BASE_COLORS
        self.magic = magic_pairs or COLOR_ALCHEMY_MAGIC
        # State
        self._last_btn = -1
        self._last_btn_frame = 0
        self._output = OUT_IDLE
        self._output_color = (0, 0, 0)
        self._output_frame = 0
        self._discoveries = set()  # tuple keys of combos discovered

    @property
    def output_type(self):
        return self._output

    @property
    def output_color(self):
        return self._output_color

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

    def update(self, btn_pressed, frame):
        """Call every frame with the index of a just-pressed button (-1 if none).

        Returns (output_type, color_rgb) for the current frame.
        """
        hold = MAGIC_HOLD if self._output == OUT_MAGIC else DISPLAY_HOLD

        # Check if current output has expired
        if self._output != OUT_IDLE and (frame - self._output_frame) > hold:
            self._output = OUT_IDLE
            self._output_color = (0, 0, 0)

        # Check if combo window expired (reset last button)
        if self._last_btn >= 0 and (frame - self._last_btn_frame) > COMBO_WINDOW:
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
            self._output_frame = frame
            self._last_btn = -1
        else:
            # First button (or same button again)
            self._output = OUT_SINGLE
            self._output_color = self.colors[btn_pressed]
            self._output_frame = frame
            self._last_btn = btn_pressed
            self._last_btn_frame = frame
            # Track single-color discoveries too
            self._discoveries.add((btn_pressed,))

        return self._output, self._output_color

    def make_leds(self, frame, brightness=128):
        """Generate LED colors for the current output state.

        Writes into the shared _led_buf to avoid per-frame allocations.
        """
        if self._output == OUT_IDLE:
            # Gentle ambient breathing
            phase = (frame * 2) & 0xFF
            v = phase if phase < 128 else 255 - phase
            v = (v * brightness) >> 8
            for i in range(N_LEDS):
                _led_buf[i] = scale(hsv_to_rgb((frame + i * 16) & 0xFF, 255, 255), v)
            return _led_buf

        if self._output == OUT_MAGIC:
            # Sparkle in the magic color
            from bodn.patterns import pattern_sparkle
            pattern_sparkle(frame, 3, self._output_color, brightness)
            # Add a solid underglow (modify buffer in-place)
            glow = scale(self._output_color, brightness // 4)
            for i in range(N_LEDS):
                b = _led_buf[i]
                _led_buf[i] = (max(b[0], glow[0]), max(b[1], glow[1]), max(b[2], glow[2]))
            return _led_buf

        if self._output == OUT_MIX:
            # Pulse the mixed color across all LEDs with a wave
            age = frame - self._output_frame
            # Expand from center
            mid = N_LEDS // 2
            c = scale(self._output_color, brightness)
            for i in range(N_LEDS):
                dist = abs(i - mid)
                _led_buf[i] = c if dist <= age else (0, 0, 0)
            return _led_buf

        # OUT_SINGLE: solid flash
        c = scale(self._output_color, brightness)
        for i in range(N_LEDS):
            _led_buf[i] = c
        return _led_buf
