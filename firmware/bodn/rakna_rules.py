# bodn/rakna_rules.py — Rakna math game engine (pure logic)
#
# NFC-based number sense progression following Bruner's CPA model.
# Level 1: Quantity Discovery — scan cards, see dots, hear the number.
# Level 2: Find the Number — TTS asks for a number, child scans it.
# Level 3: More or Less — comparison challenges ("find more than 3!").
# Level 4: Put Together — visual addition (two dot groups, scan total).
# Level 5: Take Away — subtraction as removal (dots fade, scan remainder).
# Level 6: Build Numbers — child scans num + op + num, device shows result.
#
# Self-paced, never timed.  No game-over state.

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
COMPARE_THRESHOLD = const(6)  # correct answers before level 4
ADD_THRESHOLD = const(6)  # correct answers before level 5
SUB_THRESHOLD = const(6)  # correct answers to "complete" level 5

# Challenge types
CHALLENGE_DISCOVER = "discover"
CHALLENGE_FIND = "find"
CHALLENGE_MORE = "more"
CHALLENGE_LESS = "less"
CHALLENGE_ADD = "add"
CHALLENGE_SUB = "sub"
CHALLENGE_BUILD = "build"

# Build step markers (level 6)
BUILD_NEED_FIRST = const(0)
BUILD_NEED_OP = const(1)
BUILD_NEED_SECOND = const(2)
BUILD_DONE = const(3)

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

# Number word i18n key prefix (neutral so clips can be reused across modes)
_NUMBER_KEY_PREFIX = "num_"

# Warm amber for discovery, cool cyan for challenges
_COLOUR_DISCOVER = (255, 180, 50)
_COLOUR_FIND = (100, 200, 255)
_COLOUR_COMPARE = (200, 150, 255)
_COLOUR_ADD = (100, 230, 150)
_COLOUR_SUB = (255, 150, 100)
_COLOUR_BUILD = (180, 100, 240)


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
        self.level = max(1, min(level, 6))
        self.score = 0
        self.streak = 0
        self.best_streak = 0
        self.target = 0  # target number (level 2) or reference (level 3)
        self.addend_a = 0  # first group (level 4) or start (level 5)
        self.addend_b = 0  # second group (level 4) or removed (level 5)
        self.challenge_type = CHALLENGE_DISCOVER
        self.last_card_id = None
        self.last_card = None
        self.last_card_quantity = 0
        self.discovered = set()  # quantities seen in level 1
        self._state_ms = 0
        self._level_correct = 0  # correct answers in current level
        self._target_range = 5  # level 2 starts with 1-5
        self._add_range = 5  # level 4 starts with totals within 5
        # Level 6 equation builder state
        self.build_step = BUILD_NEED_FIRST
        self.build_a = 0
        self.build_op = ""
        self.build_b = 0
        self.build_result = 0

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
        elif self.level == 4:
            self._pick_addition()
        elif self.level == 5:
            self._pick_subtraction()
        elif self.level == 6:
            self._start_build()

    def _start_build(self):
        """Level 6: set up a fresh equation slot, awaiting child's construction."""
        self.challenge_type = CHALLENGE_BUILD
        self.target = 0
        self.build_step = BUILD_NEED_FIRST
        self.build_a = 0
        self.build_op = ""
        self.build_b = 0
        self.build_result = 0

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

    def _pick_addition(self):
        """Pick a visual addition challenge (a + b = ?)."""
        self.challenge_type = CHALLENGE_ADD
        # Total must be within range and ≤ 10; both addends ≥ 1
        max_total = min(self._add_range, 10)
        total = _rand_int(2, max_total)
        self.addend_a = _rand_int(1, total - 1)
        self.addend_b = total - self.addend_a
        self.target = total

    def _pick_subtraction(self):
        """Pick a subtraction challenge (a - b = ?)."""
        self.challenge_type = CHALLENGE_SUB
        # Start ≥ 2, removal ≥ 1, remainder ≥ 1
        self.addend_a = _rand_int(3, 10)  # start quantity
        self.addend_b = _rand_int(1, self.addend_a - 1)  # removed
        self.target = self.addend_a - self.addend_b  # remainder

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
        elif self.level == 4:
            # Addition: scan the total
            return qty == self.target
        elif self.level == 5:
            # Subtraction: scan the remainder
            return qty == self.target

        return False

    @property
    def number_key(self):
        """i18n key for the last scanned quantity, e.g. 'num_3'."""
        if self.last_card_quantity > 0:
            return "{}{}".format(_NUMBER_KEY_PREFIX, self.last_card_quantity)
        return None

    @property
    def target_number_key(self):
        """i18n key for the target number."""
        if self.target > 0:
            return "{}{}".format(_NUMBER_KEY_PREFIX, self.target)
        return None

    def result_number_key(self):
        """i18n key for the current build result (level 6), e.g. 'num_7'."""
        if 0 <= self.build_result <= 20:
            return "{}{}".format(_NUMBER_KEY_PREFIX, self.build_result)
        return None

    @property
    def rule_colour_rgb(self):
        """RGB colour for the current level/challenge."""
        if self.level == 1:
            return _COLOUR_DISCOVER
        elif self.level == 2:
            return _COLOUR_FIND
        elif self.level == 3:
            return _COLOUR_COMPARE
        elif self.level == 4:
            return _COLOUR_ADD
        elif self.level == 5:
            return _COLOUR_SUB
        elif self.level == 6:
            return _COLOUR_BUILD
        return _COLOUR_DISCOVER

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
            if card_id is not None:
                # Card scanned during announce — skip ahead and process it
                self._set_state(WAITING)
                return self._handle_scan(card_id)
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
                    elif self.level == 6:
                        # Free-build: clear slot and wait for next equation
                        self._start_build()
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
                self.level = min(self.level + 1, 6)
                self._level_correct = 0
                if self.level == 2:
                    self._target_range = 5
                elif self.level == 4:
                    self._add_range = 5
                self._pick_challenge()
                self._set_state(ANNOUNCE)
            return self.state

        return self.state

    def _handle_scan(self, card_id):
        """Process a card scan during WAITING state."""
        if self.level == 6:
            return self._handle_build_scan(card_id)

        if self._check_answer(card_id):
            self.score += 1
            self.streak += 1
            if self.streak > self.best_streak:
                self.best_streak = self.streak
            self._level_correct += 1
            if self.level == 1:
                self.discovered.add(self.last_card_quantity)
            # Expand ranges after some success
            if self.level == 2 and self._level_correct == 3 and self._target_range < 10:
                self._target_range = 10
            if self.level == 4 and self._level_correct == 3 and self._add_range < 10:
                self._add_range = 10
            self._set_state(CORRECT)
        else:
            self.streak = 0
            self._set_state(WRONG)
        return self.state

    def _handle_build_scan(self, card_id):
        """Process a card scan while building a level-6 equation.

        The child scans num -> op -> num.  Bad types go to WRONG without
        discarding the partial build.
        """
        card = self._cards.get(card_id)
        self.last_card_id = card_id
        self.last_card = card
        if card is None:
            self.last_card_quantity = 0
            self.streak = 0
            self._set_state(WRONG)
            return self.state

        ctype = card.get("type")
        qty = card.get("quantity")
        op = card.get("operator")

        if self.build_step == BUILD_NEED_FIRST:
            if ctype == "number" and qty is not None:
                self.build_a = qty
                self.last_card_quantity = qty
                self.build_step = BUILD_NEED_OP
                self._set_state(WAITING)
                return self.state
            self.last_card_quantity = qty if qty is not None else 0
            self.streak = 0
            self._set_state(WRONG)
            return self.state

        if self.build_step == BUILD_NEED_OP:
            if ctype == "operator" and op in ("+", "-"):
                self.build_op = op
                self.last_card_quantity = 0
                self.build_step = BUILD_NEED_SECOND
                self._set_state(WAITING)
                return self.state
            self.last_card_quantity = qty if qty is not None else 0
            self.streak = 0
            self._set_state(WRONG)
            return self.state

        if self.build_step == BUILD_NEED_SECOND:
            if ctype == "number" and qty is not None:
                self.build_b = qty
                self.last_card_quantity = qty
                if self.build_op == "+":
                    self.build_result = self.build_a + self.build_b
                else:
                    self.build_result = max(0, self.build_a - self.build_b)
                self.target = self.build_result
                self.score += 1
                self.streak += 1
                if self.streak > self.best_streak:
                    self.best_streak = self.streak
                self._level_correct += 1
                self.build_step = BUILD_DONE
                self._set_state(CORRECT)
                return self.state
            self.last_card_quantity = qty if qty is not None else 0
            self.streak = 0
            self._set_state(WRONG)
            return self.state

        return self.state

    def _should_level_up(self):
        """Check if conditions are met for a level up."""
        if self.level == 1:
            return len(self.discovered) >= DISCOVER_THRESHOLD
        elif self.level == 2:
            return self._level_correct >= FIND_THRESHOLD
        elif self.level == 3:
            return self._level_correct >= COMPARE_THRESHOLD
        elif self.level == 4:
            return self._level_correct >= ADD_THRESHOLD
        elif self.level == 5:
            return self._level_correct >= SUB_THRESHOLD
        # Level 6 is the final level — endless free-build
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
