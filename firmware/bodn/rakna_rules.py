# bodn/rakna_rules.py — Rakna math game engine (pure logic)
#
# NFC-based number sense progression following Bruner's CPA model.
# Level 1: Quantity Discovery — scan cards, see dots, hear the number.
# Level 2: Find the Number — TTS asks for a number, child scans it.
# Level 3: More or Less — comparison challenges ("find more than 3!").
#
# Self-paced, never timed.  No game-over state.
# Levels 4-6 (addition, subtraction, symbolic) are future work.

import os

from micropython import const
from bodn.patterns import N_STICKS, N_LEDS

# Game states
WELCOME = const(0)
ANNOUNCE = const(1)  # announcing challenge (TTS plays)
WAITING = const(2)  # waiting for card scan
CORRECT = const(3)  # celebration feedback
WRONG = const(4)  # gentle nudge
LEVEL_UP = const(5)  # level transition

# Timing (milliseconds) — generous, self-paced feel
WELCOME_MS = const(3000)
ANNOUNCE_MS = const(4000)  # longer than Sortera — let TTS finish
CORRECT_MS = const(2000)  # longer celebration ("celebrate process")
WRONG_MS = const(2500)  # gentle, re-states the challenge
LEVEL_UP_MS = const(3000)

# Level progression thresholds
DISCOVER_THRESHOLD = const(6)  # unique cards scanned before level 2
FIND_THRESHOLD = const(5)  # correct answers before level 3
COMPARE_THRESHOLD = const(6)  # correct answers to "complete" level 3

# Challenge types
CHALLENGE_DISCOVER = "discover"
CHALLENGE_FIND = "find"
CHALLENGE_MORE = "more"
CHALLENGE_LESS = "less"

# Demo mode: button index -> card ID mapping (buttons 0-7 -> dots_1..dots_8)
DEMO_CARDS = [
    "dots_1",
    "dots_2",
    "dots_3",
    "dots_4",
    "dots_5",
    "dots_6",
    "dots_7",
    "dots_8",
]

# Number word i18n key prefix
_NUMBER_KEY_PREFIX = "rakna_number_"

# Warm amber for discovery, cool cyan for challenges
_COLOUR_DISCOVER = (255, 180, 50)
_COLOUR_FIND = (100, 200, 255)
_COLOUR_COMPARE = (200, 150, 255)


def _rand_int(lo, hi):
    """Random integer in [lo, hi] inclusive."""
    span = hi - lo + 1
    return lo + (int.from_bytes(os.urandom(1), "big") % span)


class RaknaEngine:
    """Stateful game engine for Rakna.

    Pure logic — no hardware imports beyond patterns.
    Feed it card IDs (from NFC or demo buttons) and time deltas.
    """

    def __init__(self, card_set, level=1):
        """Initialise with a card set dict (from rakna.json)."""
        self._cards = {c["id"]: c for c in card_set.get("cards", [])}
        self._number_cards = {
            c["id"]: c for c in card_set.get("cards", []) if c.get("type") == "number"
        }
        self.reset(level)

    def reset(self, level=1):
        """Reset to initial state at the given level."""
        self.state = WELCOME
        self.level = max(1, min(level, 3))
        self.score = 0
        self.streak = 0
        self.best_streak = 0
        self.target = 0  # target number (level 2) or reference (level 3)
        self.challenge_type = CHALLENGE_DISCOVER
        self.last_card_id = None
        self.last_card = None
        self.last_card_quantity = 0
        self.discovered = set()  # quantities seen in level 1
        self._state_ms = 0
        self._level_correct = 0  # correct answers in current level
        self._target_range = 5  # level 2 starts with 1-5

    def _set_state(self, new_state):
        self.state = new_state
        self._state_ms = 0

    def _pick_challenge(self):
        """Pick a challenge appropriate for the current level."""
        if self.level == 1:
            self.challenge_type = CHALLENGE_DISCOVER
            self.target = 0
        elif self.level == 2:
            self.challenge_type = CHALLENGE_FIND
            self.target = _rand_int(1, self._target_range)
        elif self.level == 3:
            self._pick_comparison()

    def _pick_comparison(self):
        """Pick a comparison challenge with guaranteed valid answers."""
        if _rand_int(0, 1) == 0:
            # "more than" — reference must be < 10 (so some card is greater)
            self.challenge_type = CHALLENGE_MORE
            self.target = _rand_int(1, 9)
        else:
            # "less than" — reference must be > 1 (so some card is smaller)
            self.challenge_type = CHALLENGE_LESS
            self.target = _rand_int(2, 10)

    def check_card(self, card_id):
        """Look up a card and update last_card state.

        Returns True if the card exists and is a number card, False otherwise.
        """
        card = self._cards.get(card_id)
        self.last_card_id = card_id
        self.last_card = card

        if card is None:
            self.last_card_quantity = 0
            return False

        qty = card.get("quantity")
        if qty is None:
            # Operator card or unknown type
            self.last_card_quantity = 0
            return False

        self.last_card_quantity = qty
        return True

    def _check_answer(self, card_id):
        """Check if the scanned card is a correct answer for the current challenge."""
        if not self.check_card(card_id):
            return False

        qty = self.last_card_quantity

        if self.level == 1:
            # Discovery: any number card is correct
            return True
        elif self.level == 2:
            return qty == self.target
        elif self.level == 3:
            if self.challenge_type == CHALLENGE_MORE:
                return qty > self.target
            else:  # CHALLENGE_LESS
                return qty < self.target

        return False

    @property
    def number_key(self):
        """i18n key for the last scanned quantity, e.g. 'rakna_number_3'."""
        if self.last_card_quantity > 0:
            return "{}{}".format(_NUMBER_KEY_PREFIX, self.last_card_quantity)
        return None

    @property
    def target_number_key(self):
        """i18n key for the target number."""
        if self.target > 0:
            return "{}{}".format(_NUMBER_KEY_PREFIX, self.target)
        return None

    @property
    def rule_colour_rgb(self):
        """RGB colour for the current level/challenge."""
        if self.level == 1:
            return _COLOUR_DISCOVER
        elif self.level == 2:
            return _COLOUR_FIND
        return _COLOUR_COMPARE

    def update(self, card_id, dt):
        """Advance engine state.

        Args:
            card_id: card ID string from NFC scan or demo button, None if no input
            dt: milliseconds since last tick

        Returns the current state.
        """
        self._state_ms += dt

        if self.state == WELCOME:
            if self._state_ms >= WELCOME_MS:
                self._pick_challenge()
                self._set_state(ANNOUNCE)
            return self.state

        elif self.state == ANNOUNCE:
            if self._state_ms >= ANNOUNCE_MS:
                self._set_state(WAITING)
            return self.state

        elif self.state == WAITING:
            if card_id is not None:
                return self._handle_scan(card_id)
            return self.state

        elif self.state == CORRECT:
            if self._state_ms >= CORRECT_MS:
                if self._should_level_up():
                    self._set_state(LEVEL_UP)
                else:
                    if self.level == 1:
                        # Discovery: go straight back to waiting
                        self._set_state(WAITING)
                    else:
                        self._pick_challenge()
                        self._set_state(ANNOUNCE)
            return self.state

        elif self.state == WRONG:
            if self._state_ms >= WRONG_MS:
                self._set_state(WAITING)
            return self.state

        elif self.state == LEVEL_UP:
            if self._state_ms >= LEVEL_UP_MS:
                self.level = min(self.level + 1, 3)
                self._level_correct = 0
                if self.level == 2:
                    self._target_range = 5
                self._pick_challenge()
                self._set_state(ANNOUNCE)
            return self.state

        return self.state

    def _handle_scan(self, card_id):
        """Process a card scan during WAITING state."""
        if self._check_answer(card_id):
            self.score += 1
            self.streak += 1
            if self.streak > self.best_streak:
                self.best_streak = self.streak
            self._level_correct += 1
            if self.level == 1:
                self.discovered.add(self.last_card_quantity)
            # Expand target range in level 2 after some success
            if self.level == 2 and self._level_correct == 3 and self._target_range < 10:
                self._target_range = 10
            self._set_state(CORRECT)
        else:
            self.streak = 0
            self._set_state(WRONG)
        return self.state

    def _should_level_up(self):
        """Check if conditions are met for a level up."""
        if self.level == 1:
            return len(self.discovered) >= DISCOVER_THRESHOLD
        elif self.level == 2:
            return self._level_correct >= FIND_THRESHOLD
        elif self.level == 3:
            # Level 3 is endless — no level up (levels 4-6 are future work)
            return False
        return False

    def make_static_leds(self, brightness):
        """Return LED buffer (list of (r,g,b) tuples) for the current state."""
        buf = [(0, 0, 0)] * N_LEDS

        def _sc(val):
            return (val * brightness) >> 8

        if self.state in (ANNOUNCE, WAITING):
            r, g, b = self.rule_colour_rgb
            c = (_sc(r), _sc(g), _sc(b))
            for i in range(N_STICKS):
                buf[i] = c
            # In level 2/3, light up target-count LEDs on the sticks
            if self.level >= 2 and self.target > 0:
                n = min(self.target, N_STICKS)
                for i in range(n):
                    buf[i] = (_sc(255), _sc(255), _sc(255))

        elif self.state == CORRECT:
            c = (0, _sc(200), 0)
            for i in range(N_STICKS):
                buf[i] = c

        elif self.state == WRONG:
            c = (_sc(80), _sc(40), 0)  # warm amber, not harsh red
            for i in range(N_STICKS):
                buf[i] = c

        elif self.state == LEVEL_UP:
            for i in range(N_STICKS):
                if i % 2 == 0:
                    buf[i] = (_sc(255), _sc(200), 0)
                else:
                    buf[i] = (0, _sc(200), _sc(255))

        return buf
