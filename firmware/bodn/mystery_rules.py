# bodn/mystery_rules.py — Mystery Box rule engine (pure logic, testable on host)
#
# Each base colour matches a physical button cap (see theme.BTN_RGB) so the
# swatch on screen and the stick LED match the cap the child just pressed.
# Pressing two caps within COMBO_WINDOW_MS produces either a plain RGB-average
# mix or, for hand-picked pairs, a *magic* combo with a distinctive colour
# and sparkle feedback.
#
# Modifiers transform the output without adding rules:
#   SW0   — invert colours
#   SW1   — mirror LED stick pattern
#   ENC_B — hue rotation

from micropython import const
from bodn.patterns import N_STICKS, scale, _led_buf

# Output types
OUT_IDLE = const(0)
OUT_SINGLE = const(1)
OUT_MIX = const(2)
OUT_MAGIC = const(3)

# Discovery events (consumed once by the screen)
EV_NONE = const(0)
EV_NEW_SINGLE = const(1)
EV_NEW_MAGIC = const(2)
EV_NEW_MOD = const(3)
EV_COMPLETE = const(4)

# Modifier unlock thresholds — gated on total discoveries so the toggles
# and encoder feel earned rather than mystery hardware. The kid first
# learns "press a cap, see a colour"; modifiers reveal themselves later.
MOD_INVERT_AT = const(5)
MOD_MIRROR_AT = const(10)
MOD_HUE_SINGLES = const(8)  # all 8 single caps discovered

# Modifier ids (for event payload)
MOD_INVERT = "invert"
MOD_MIRROR = "mirror"
MOD_HUE = "hue"

# Timing (milliseconds, wall-clock, frame-rate independent)
COMBO_WINDOW_MS = const(1000)
DISPLAY_HOLD_MS = const(1500)
MAGIC_HOLD_MS = const(2500)
FINALE_MS = const(5000)  # rainbow takeover after all 16 found


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
    zone = (amount * 3) >> 8
    frac = (amount * 3) & 0xFF
    inv = 255 - frac
    if zone == 0:
        return (
            (r * inv + g * frac) >> 8,
            (g * inv + b * frac) >> 8,
            (b * inv + r * frac) >> 8,
        )
    elif zone == 1:
        return (
            (r * inv + b * frac) >> 8,
            (g * inv + r * frac) >> 8,
            (b * inv + g * frac) >> 8,
        )
    else:
        return (
            (r * inv + g * frac) >> 8,
            (g * inv + b * frac) >> 8,
            (b * inv + r * frac) >> 8,
        )


# Base colours per button — must mirror theme.BTN_RGB so the screen swatch and
# stick LED match the physical cap. Index ↔ cap:
#   0 green, 1 blue, 2 white, 3 yellow, 4 red,
#   5 black-cap (rendered teal on dark bg), 6 green2 (mint), 7 blue2 (sky)
BASE_COLORS = [
    (0, 200, 0),
    (0, 100, 255),
    (255, 255, 255),
    (255, 220, 0),
    (255, 0, 0),
    (0, 160, 140),
    (0, 220, 120),
    (80, 160, 255),
]

# Magic pairs: sorted (a, b) → output colour. Eight kid-intuitive mixes that
# produce a recognisable new colour rather than the plain RGB average.
COLOR_ALCHEMY_MAGIC = {
    (0, 1): (0, 200, 255),  # green + blue   → cyan
    (0, 3): (180, 255, 50),  # green + yellow → lime
    (0, 4): (255, 165, 0),  # green + red    → amber
    (1, 3): (50, 255, 50),  # blue + yellow  → bright green
    (1, 4): (160, 0, 255),  # blue + red     → purple
    (3, 4): (255, 130, 0),  # yellow + red   → orange
    (1, 2): (130, 200, 255),  # white + blue   → sky
    (2, 4): (255, 150, 200),  # white + red    → pink
}


class MysteryEngine:
    """Stateful rule engine that tracks inputs and produces outputs.

    Pure logic — no hardware imports beyond patterns. Feed it button presses
    each tick with dt (ms) and read back the current output state. Modifiers
    (switches and encoder) transform the output colour and LED pattern,
    multiplying the discovery space without adding rules.
    """

    def __init__(self, colors=None, magic_pairs=None):
        self.colors = colors or BASE_COLORS
        self.magic = magic_pairs or COLOR_ALCHEMY_MAGIC
        self._last_btn = -1
        self._last_btn_ms = 0
        self._output = OUT_IDLE
        self._output_color = (0, 0, 0)
        self._output_ms = 0
        self.singles_discovered = set()
        self.magic_discovered = set()
        self._last_unlock = None
        self._last_mod_unlock = None
        self._event = EV_NONE
        # Modifier unlock state (latches True; never goes back)
        self._invert_unlocked = False
        self._mirror_unlocked = False
        self._hue_unlocked = False
        # Modifier inputs (set by caller each frame; ignored when not unlocked)
        self.sw_invert = False
        self.sw_mirror = False
        self.hue_shift = 0

    @property
    def output_type(self):
        return self._output

    @property
    def output_color(self):
        return self._output_color

    @property
    def display_color(self):
        """Output colour after modifier transforms (for screen display)."""
        return self._apply_color_mods(self._output_color)

    @property
    def discovery_count(self):
        return len(self.singles_discovered) + len(self.magic_discovered)

    @property
    def total_discoverable(self):
        """Total unique outputs: N singles + N magic combos."""
        return len(self.colors) + len(self.magic)

    @property
    def is_complete(self):
        return len(self.singles_discovered) == len(self.colors) and len(
            self.magic_discovered
        ) == len(self.magic)

    @property
    def last_unlock(self):
        """Most recent unlock as ('single', idx) or ('magic', (a, b)), or None.
        Used by the secondary display to highlight the freshly-found tile.
        """
        return self._last_unlock

    @property
    def last_mod_unlock(self):
        """Most recent modifier unlock id (MOD_INVERT/MIRROR/HUE) or None."""
        return self._last_mod_unlock

    @property
    def invert_unlocked(self):
        return self._invert_unlocked

    @property
    def mirror_unlocked(self):
        return self._mirror_unlocked

    @property
    def hue_unlocked(self):
        return self._hue_unlocked

    @property
    def discoveries(self):
        """Union of discoveries as a set of tuple keys: (idx,) or (a, b)."""
        out = set()
        for s in self.singles_discovered:
            out.add((s,))
        for m in self.magic_discovered:
            out.add(m)
        return out

    def consume_event(self):
        """Return and clear the latest discovery event (EV_*)."""
        e = self._event
        self._event = EV_NONE
        return e

    def to_state(self):
        """Snapshot for persistence. Sets serialise as sorted lists."""
        return {
            "singles": sorted(self.singles_discovered),
            "magic": sorted([list(p) for p in self.magic_discovered]),
            "invert": self._invert_unlocked,
            "mirror": self._mirror_unlocked,
            "hue": self._hue_unlocked,
        }

    def load_state(self, state):
        """Restore from a to_state() snapshot. Tolerant of missing keys."""
        if not state:
            return
        for s in state.get("singles", ()):
            if 0 <= s < len(self.colors):
                self.singles_discovered.add(s)
        for pair in state.get("magic", ()):
            if len(pair) == 2:
                key = _pair_key(pair[0], pair[1])
                if key in self.magic:
                    self.magic_discovered.add(key)
        self._invert_unlocked = bool(state.get("invert", False))
        self._mirror_unlocked = bool(state.get("mirror", False))
        self._hue_unlocked = bool(state.get("hue", False))
        # Backfill any gates the persisted counts already exceed (in case
        # thresholds were tightened between firmware versions).
        self._refresh_mod_gates(emit_event=False)

    def _refresh_mod_gates(self, emit_event=True):
        """Promote modifier unlock flags based on current discovery counts.

        Returns the modifier id that just unlocked (or None). If multiple
        unlock at once we emit the highest-tier event but flag all flags.
        """
        newly = None
        if not self._invert_unlocked and self.discovery_count >= MOD_INVERT_AT:
            self._invert_unlocked = True
            newly = MOD_INVERT
        if not self._mirror_unlocked and self.discovery_count >= MOD_MIRROR_AT:
            self._mirror_unlocked = True
            newly = MOD_MIRROR
        if not self._hue_unlocked and len(self.singles_discovered) >= MOD_HUE_SINGLES:
            self._hue_unlocked = True
            newly = MOD_HUE
        if newly and emit_event:
            self._last_mod_unlock = newly
            # Don't clobber a higher-tier event already queued this frame.
            if self._event in (EV_NONE, EV_NEW_SINGLE, EV_NEW_MAGIC):
                self._event = EV_NEW_MOD
        return newly

    def _apply_color_mods(self, c):
        if self._invert_unlocked and self.sw_invert:
            c = _invert_rgb(c)
        if self._hue_unlocked and self.hue_shift > 0:
            c = _shift_hue(c, self.hue_shift)
        return c

    @property
    def mirror_active(self):
        """Whether the LED mirror modifier should be applied this frame."""
        return self._mirror_unlocked and self.sw_mirror

    def update(self, btn_pressed, dt):
        """Call every tick. btn_pressed is just-pressed button index (-1 if none).

        Returns (output_type, color_rgb) for the current frame.
        """
        self._output_ms += dt
        self._last_btn_ms += dt

        hold = MAGIC_HOLD_MS if self._output == OUT_MAGIC else DISPLAY_HOLD_MS
        if self._output != OUT_IDLE and self._output_ms > hold:
            self._output = OUT_IDLE
            self._output_color = (0, 0, 0)

        if self._last_btn >= 0 and self._last_btn_ms > COMBO_WINDOW_MS:
            self._last_btn = -1

        if btn_pressed < 0:
            return self._output, self._output_color

        new_discovery = False
        if self._last_btn >= 0 and self._last_btn != btn_pressed:
            pair = _pair_key(self._last_btn, btn_pressed)
            if pair in self.magic:
                self._output = OUT_MAGIC
                self._output_color = self.magic[pair]
                if pair not in self.magic_discovered:
                    self.magic_discovered.add(pair)
                    self._last_unlock = ("magic", pair)
                    self._event = EV_NEW_MAGIC
                    new_discovery = True
            else:
                c1 = self.colors[self._last_btn]
                c2 = self.colors[btn_pressed]
                self._output = OUT_MIX
                self._output_color = mix_rgb(c1, c2)
            self._output_ms = 0
            self._last_btn = -1
        else:
            self._output = OUT_SINGLE
            self._output_color = self.colors[btn_pressed]
            self._output_ms = 0
            self._last_btn = btn_pressed
            self._last_btn_ms = 0
            if btn_pressed not in self.singles_discovered:
                self.singles_discovered.add(btn_pressed)
                self._last_unlock = ("single", btn_pressed)
                self._event = EV_NEW_SINGLE
                new_discovery = True

        if new_discovery:
            # Modifier promotions piggy-back on a new find. EV_COMPLETE wins
            # over modifier/discovery events because it's the loudest signal.
            if self.is_complete:
                self._event = EV_COMPLETE
            else:
                self._refresh_mod_gates(emit_event=True)

        return self._output, self._output_color

    def make_static_leds(self, brightness=128):
        """Generate static LED colours for the current output state.

        No animation — solid colours only. Writes into the shared _led_buf.
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
        for i in range(n):
            buf[i] = c

        if self.mirror_active:
            half = n // 2
            for i in range(half):
                buf[n - 1 - i] = buf[i]

        return buf
