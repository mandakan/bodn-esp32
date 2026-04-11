# bodn/sortera_rules.py — Sortera classification game engine (pure logic)
#
# A tangible DCCS (Dimensional Change Card Sort) game using NFC cards.
# The device announces a sorting rule ("Find all the animals!"), the child
# scans matching cards.  After N correct the rule switches to a different
# dimension ("Now find all the RED ones!"), exercising cognitive flexibility
# and inhibitory control.
#
# Endless play — no game-over state.  The child stops via pause menu.

import os

from micropython import const
from bodn.patterns import N_STICKS, _led_buf

# Game states
WELCOME = const(0)  # waiting to start
ANNOUNCE_RULE = const(1)  # showing/announcing the current rule
WAITING = const(2)  # waiting for a card scan
CORRECT = const(3)  # correct card — celebration
WRONG = const(4)  # wrong card — gentle feedback
RULE_SWITCH = const(5)  # rule is changing

# Timing (milliseconds)
ANNOUNCE_MS = const(2500)  # rule announcement duration
CORRECT_MS = const(1200)  # celebration duration
WRONG_MS = const(1500)  # gentle feedback
SWITCH_MS = const(2000)  # rule switch animation

# Rule switching config
SWITCH_AFTER_MIN = const(4)  # min correct before rule switch
SWITCH_AFTER_MAX = const(6)  # max correct before rule switch

# Colour palette for rule feedback (RGB)
COLOUR_MAP = {
    "red": (255, 50, 50),
    "blue": (50, 100, 255),
    "green": (50, 220, 100),
    "yellow": (255, 220, 30),
}

# Demo mode: button index → card ID mapping
DEMO_CARDS = [
    "cat_red",
    "dog_green",
    "rabbit_red",
    "bird_blue",
    "fish_red",
    "horse_green",
    "cow_red",
    "frog_blue",
]


def _rand_int(lo, hi):
    """Random integer in [lo, hi] inclusive."""
    span = hi - lo + 1
    return lo + (int.from_bytes(os.urandom(1), "big") % span)


class SorteraEngine:
    """Stateful game engine for Sortera.

    Pure logic — no hardware imports beyond patterns.
    Feed it card IDs (from NFC or demo buttons) and time deltas.
    """

    def __init__(self, card_set):
        """Initialise with a card set dict (from sortera.json)."""
        self._cards = {c["id"]: c for c in card_set.get("cards", [])}
        self._dimensions = card_set.get("dimensions", [])
        self._card_list = list(self._cards.values())
        self.reset()

    def reset(self):
        """Reset to initial state."""
        self.state = WELCOME
        self.score = 0
        self.streak = 0
        self.best_streak = 0
        self.rule_switches = 0
        self.rule_dimension = ""  # e.g., "category" or "colour"
        self.rule_value = ""  # e.g., "animal" or "red"
        self.last_card_id = None  # last scanned card ID
        self.last_card = None  # last scanned card dict
        self.last_correct = False  # was last scan correct?
        self._state_ms = 0
        self._rule_correct_count = 0
        self._switch_threshold = 0
        self._prev_rule = None  # (dimension, value) to avoid repeats

    def _set_state(self, new_state):
        self.state = new_state
        self._state_ms = 0

    def _pick_switch_threshold(self):
        self._switch_threshold = _rand_int(SWITCH_AFTER_MIN, SWITCH_AFTER_MAX)
        self._rule_correct_count = 0

    def _pick_rule(self):
        """Pick a random rule (dimension + value), avoiding the previous one."""
        if not self._dimensions or not self._card_list:
            return

        # Collect all unique (dimension, value) pairs from the card set
        options = []
        for dim in self._dimensions:
            values = set()
            for card in self._card_list:
                val = card.get(dim)
                if val is not None:
                    values.add(val)
            for val in values:
                if (dim, val) != self._prev_rule:
                    options.append((dim, val))

        if not options:
            # Only one possible rule — use it
            options = [
                (self._dimensions[0], self._card_list[0].get(self._dimensions[0], ""))
            ]

        idx = int.from_bytes(os.urandom(1), "big") % len(options)
        dim, val = options[idx]
        self._prev_rule = (dim, val)
        self.rule_dimension = dim
        self.rule_value = val
        self._pick_switch_threshold()

    def check_card(self, card_id):
        """Check if a card matches the current rule.

        Returns True if the card matches, False otherwise.
        Updates last_card, last_card_id, last_correct.
        """
        card = self._cards.get(card_id)
        self.last_card_id = card_id
        self.last_card = card

        if card is None:
            self.last_correct = False
            return False

        matches = card.get(self.rule_dimension) == self.rule_value
        self.last_correct = matches
        return matches

    @property
    def matching_count(self):
        """How many cards in the set match the current rule."""
        count = 0
        for card in self._card_list:
            if card.get(self.rule_dimension) == self.rule_value:
                count += 1
        return count

    @property
    def rule_colour_rgb(self):
        """RGB colour for the current rule value (if colour dimension)."""
        if self.rule_dimension == "colour":
            return COLOUR_MAP.get(self.rule_value, (255, 255, 255))
        return (100, 200, 255)  # default cyan-ish for non-colour rules

    def update(self, card_id, dt):
        """Advance engine state. card_id is a scanned card ID or None.

        Args:
            card_id: card ID string from NFC scan or demo button, None if no input
            dt: milliseconds since last tick

        Returns the current state.
        """
        self._state_ms += dt

        if self.state == WELCOME:
            if card_id is not None:
                self._pick_rule()
                self._set_state(ANNOUNCE_RULE)
            return self.state

        elif self.state == ANNOUNCE_RULE:
            if self._state_ms >= ANNOUNCE_MS:
                self._set_state(WAITING)
            return self.state

        elif self.state == WAITING:
            if card_id is not None:
                return self._handle_scan(card_id)
            return self.state

        elif self.state == CORRECT:
            if self._state_ms >= CORRECT_MS:
                if self._rule_correct_count >= self._switch_threshold:
                    self._set_state(RULE_SWITCH)
                    self.rule_switches += 1
                else:
                    self._set_state(WAITING)
            return self.state

        elif self.state == WRONG:
            if self._state_ms >= WRONG_MS:
                self._set_state(WAITING)
            return self.state

        elif self.state == RULE_SWITCH:
            if self._state_ms >= SWITCH_MS:
                self._pick_rule()
                self._set_state(ANNOUNCE_RULE)
            return self.state

        return self.state

    def _handle_scan(self, card_id):
        """Process a card scan during WAITING state."""
        if self.check_card(card_id):
            self.score += 1
            self.streak += 1
            if self.streak > self.best_streak:
                self.best_streak = self.streak
            self._rule_correct_count += 1
            self._set_state(CORRECT)
        else:
            self.streak = 0
            self._set_state(WRONG)
        return self.state

    def make_static_leds(self, brightness):
        """Return LED stick buffer for the current state."""
        buf = bytearray(len(_led_buf))

        def _sc(val):
            return (val * brightness) >> 8

        if self.state == ANNOUNCE_RULE or self.state == WAITING:
            r, g, b = self.rule_colour_rgb
            for i in range(N_STICKS):
                buf[i * 3] = _sc(g)
                buf[i * 3 + 1] = _sc(r)
                buf[i * 3 + 2] = _sc(b)

        elif self.state == CORRECT:
            g_val = _sc(200)
            for i in range(N_STICKS):
                buf[i * 3] = g_val
                buf[i * 3 + 1] = 0
                buf[i * 3 + 2] = 0

        elif self.state == WRONG:
            r_val = _sc(80)
            for i in range(N_STICKS):
                buf[i * 3] = 0
                buf[i * 3 + 1] = r_val
                buf[i * 3 + 2] = 0

        elif self.state == RULE_SWITCH:
            for i in range(N_STICKS):
                if i % 2 == 0:
                    buf[i * 3] = _sc(100)
                    buf[i * 3 + 1] = _sc(255)
                    buf[i * 3 + 2] = 0
                else:
                    buf[i * 3] = _sc(255)
                    buf[i * 3 + 1] = 0
                    buf[i * 3 + 2] = _sc(200)

        return buf
