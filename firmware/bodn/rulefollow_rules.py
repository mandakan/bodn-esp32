# bodn/rulefollow_rules.py — Rule Follow game engine (pure logic, testable on host)
#
# A rule-switching game: Bodn shows a rule (match or opposite), then flashes
# a stimulus color.  The child presses the correct button based on the active
# rule.  Periodically the rule switches, training inhibitory control and
# cognitive flexibility.
#
# Uses buttons 0–3 (4 colors), targeting age 4 with generous timing.

import os

from micropython import const
from bodn.patterns import N_STICKS, scale, _led_buf, _BLACK

# Game states
READY = const(0)  # waiting to start
SHOW_RULE = const(1)  # displaying the current rule
STIMULUS = const(2)  # showing stimulus, waiting for response
CORRECT = const(3)  # correct answer — celebration
WRONG = const(4)  # wrong answer — gentle cue
RULE_SWITCH = const(5)  # rule is changing
GAME_OVER = const(6)  # game finished

# Rules
RULE_MATCH = const(0)  # press the same color
RULE_OPPOSITE = const(1)  # press the opposite color

# Timing (in frames, ~33 fps)
SHOW_RULE_FRAMES = const(50)  # rule display duration (~1.5s)
STIMULUS_TIMEOUT = const(100)  # max wait for response (~3s)
CORRECT_FRAMES = const(33)  # celebration duration (~1s)
WRONG_FRAMES = const(40)  # gentle feedback (~1.2s)
RULE_SWITCH_FRAMES = const(66)  # rule change animation (~2s)

# Game config
NUM_BUTTONS = const(4)  # use buttons 0–3
DEFAULT_ROUNDS = const(12)  # total stimulus rounds per game
SWITCH_AFTER_MIN = const(4)  # min correct before rule switch
SWITCH_AFTER_MAX = const(6)  # max correct before rule switch

# Opposite mapping: 0↔2, 1↔3 (diagonal swap in 2×2 grid)
_OPPOSITE = (2, 3, 0, 1)

# Button colors (RGB, matching theme.BTN_RGB for buttons 0–3)
BTN_COLORS = [
    (255, 0, 0),  # Red
    (0, 255, 0),  # Green
    (0, 0, 255),  # Blue
    (255, 255, 0),  # Yellow
]

# Rule colors (RGB) — blue for match, orange for opposite
RULE_COLORS = [
    (0, 100, 255),  # Match = blue
    (255, 140, 0),  # Opposite = orange
]


def _rand_int(lo, hi):
    """Random integer in [lo, hi] inclusive."""
    span = hi - lo + 1
    return lo + (int.from_bytes(os.urandom(1), "big") % span)


def _random_button():
    """Pick a random button index (0 to NUM_BUTTONS-1)."""
    return int.from_bytes(os.urandom(1), "big") % NUM_BUTTONS


class RuleFollowEngine:
    """Stateful game engine for Rule Follow.

    Pure logic — no hardware imports beyond patterns.
    Feed it button presses each frame and read back the current state.
    """

    def __init__(
        self,
        num_buttons=NUM_BUTTONS,
        rounds=DEFAULT_ROUNDS,
        switch_min=SWITCH_AFTER_MIN,
        switch_max=SWITCH_AFTER_MAX,
    ):
        self._num_buttons = num_buttons
        self._total_rounds = rounds
        self._switch_min = switch_min
        self._switch_max = switch_max
        self.reset()

    def reset(self):
        """Reset to initial state, ready for a new game."""
        self.state = READY
        self.current_rule = RULE_MATCH
        self.stimulus_button = -1  # which button color is shown
        self.correct_button = -1  # which button should be pressed
        self.score = 0  # correct answers
        self.total = 0  # total stimuli presented
        self.streak = 0  # current consecutive correct
        self.best_streak = 0
        self.round_num = 0
        self._state_frame = 0
        self._rule_correct_count = 0  # correct on current rule
        self._switch_threshold = 0  # correct needed before switch
        self._pick_switch_threshold()

    def _pick_switch_threshold(self):
        """Randomly pick how many correct answers before rule switches."""
        self._switch_threshold = _rand_int(self._switch_min, self._switch_max)
        self._rule_correct_count = 0

    def _pick_stimulus(self):
        """Choose a random stimulus button, avoiding repeats when possible."""
        btn = _random_button()
        # Simple repeat avoidance: try once more if same as last
        if btn == self.stimulus_button:
            btn = _random_button()
        return btn

    @staticmethod
    def get_correct(stimulus, rule):
        """Return the correct button for a given stimulus and rule."""
        if rule == RULE_MATCH:
            return stimulus
        else:
            return _OPPOSITE[stimulus]

    @property
    def rule_color(self):
        """RGB color for the current rule."""
        return RULE_COLORS[self.current_rule]

    def update(self, btn_pressed, frame):
        """Call every frame. btn_pressed is the just-pressed button index (-1 if none).

        Returns the current state.
        """
        elapsed = frame - self._state_frame

        if self.state == READY:
            if btn_pressed >= 0:
                self._start_game(frame)
            return self.state

        elif self.state == SHOW_RULE:
            if elapsed >= SHOW_RULE_FRAMES:
                self._begin_stimulus(frame)
            return self.state

        elif self.state == STIMULUS:
            return self._update_stimulus(btn_pressed, frame, elapsed)

        elif self.state == CORRECT:
            if elapsed >= CORRECT_FRAMES:
                self._after_response(frame)
            return self.state

        elif self.state == WRONG:
            if elapsed >= WRONG_FRAMES:
                self._after_response(frame)
            return self.state

        elif self.state == RULE_SWITCH:
            if elapsed >= RULE_SWITCH_FRAMES:
                # Switch complete — show the new rule
                self.state = SHOW_RULE
                self._state_frame = frame
            return self.state

        elif self.state == GAME_OVER:
            if btn_pressed >= 0:
                self.reset()
                self._start_game(frame)
            return self.state

        return self.state

    def _start_game(self, frame):
        """Begin a new game."""
        self.current_rule = RULE_MATCH
        self.score = 0
        self.total = 0
        self.streak = 0
        self.best_streak = 0
        self.round_num = 0
        self._pick_switch_threshold()
        self.state = SHOW_RULE
        self._state_frame = frame

    def _begin_stimulus(self, frame):
        """Pick a stimulus and transition to STIMULUS state."""
        self.stimulus_button = self._pick_stimulus()
        self.correct_button = self.get_correct(self.stimulus_button, self.current_rule)
        self.state = STIMULUS
        self._state_frame = frame

    def _update_stimulus(self, btn_pressed, frame, elapsed):
        """Handle the stimulus phase — waiting for a button press."""
        if elapsed >= STIMULUS_TIMEOUT:
            # Timeout — count as wrong (no press)
            self.total += 1
            self.round_num += 1
            self.streak = 0
            self.state = WRONG
            self._state_frame = frame
            return self.state

        if btn_pressed < 0 or btn_pressed >= self._num_buttons:
            return self.state

        self.total += 1
        self.round_num += 1

        if btn_pressed == self.correct_button:
            self.score += 1
            self.streak += 1
            if self.streak > self.best_streak:
                self.best_streak = self.streak
            self._rule_correct_count += 1
            self.state = CORRECT
            self._state_frame = frame
        else:
            self.streak = 0
            self.state = WRONG
            self._state_frame = frame

        return self.state

    def _after_response(self, frame):
        """Decide what happens after a correct/wrong response."""
        if self.round_num >= self._total_rounds:
            self.state = GAME_OVER
            self._state_frame = frame
            return

        # Check if it's time to switch rules
        if self._rule_correct_count >= self._switch_threshold:
            self.current_rule = (
                RULE_OPPOSITE if self.current_rule == RULE_MATCH else RULE_MATCH
            )
            self._pick_switch_threshold()
            self.state = RULE_SWITCH
            self._state_frame = frame
        else:
            # Next stimulus
            self._begin_stimulus(frame)

    def make_static_leds(self, brightness=128):
        """Generate static LED colors for the current game state.

        Buttons 0–3 map to LEDs 0–3. LEDs 4–15 for accent.
        """
        buf = _led_buf
        n = N_STICKS
        black = _BLACK
        _scale = scale

        if self.state == READY:
            # Gentle blue glow
            dim = brightness // 4
            c = _scale((0, 100, 255), dim)
            for i in range(n):
                buf[i] = c
            return buf

        elif self.state == SHOW_RULE or self.state == RULE_SWITCH:
            # All LEDs in rule color
            rc = RULE_COLORS[self.current_rule]
            c = _scale(rc, brightness // 2)
            for i in range(n):
                buf[i] = c
            return buf

        elif self.state == STIMULUS:
            # Light up the stimulus button LED bright, others dim in rule color
            rc = RULE_COLORS[self.current_rule]
            dim = _scale(rc, brightness // 8)
            for i in range(n):
                buf[i] = dim
            if 0 <= self.stimulus_button < n:
                sc = BTN_COLORS[self.stimulus_button]
                buf[self.stimulus_button] = _scale(sc, brightness)
                # Mirror on stick B
                mirror = n - 1 - self.stimulus_button
                if mirror != self.stimulus_button:
                    buf[mirror] = _scale(sc, brightness // 3)
            return buf

        elif self.state == CORRECT:
            # Green pulse on all LEDs
            c = _scale((0, 255, 0), brightness)
            for i in range(n):
                buf[i] = c
            return buf

        elif self.state == WRONG:
            # Soft dim red
            c = _scale((255, 0, 0), brightness // 3)
            for i in range(n):
                buf[i] = c
            return buf

        elif self.state == GAME_OVER:
            # Warm glow
            v = max(10, brightness // 4)
            c = (v, v // 2, 0)
            for i in range(n):
                buf[i] = c
            return buf

        # Fallback: all off
        for i in range(n):
            buf[i] = black
        return buf
