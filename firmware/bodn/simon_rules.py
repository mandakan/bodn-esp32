# bodn/simon_rules.py — Pattern Copy (Simon) rule engine (pure logic, testable on host)
#
# A sequence memory game: Bodn plays a pattern of button presses (LED + color),
# then the child reproduces it. Correct → sequence grows. Wrong → replay.
#
# Uses buttons 0–5 (6 colors), targeting 2–3 step sequences for age 4.

import os

from bodn.patterns import N_LEDS, scale, _led_buf

# Game states
READY = 0  # waiting to start
SHOWING = 1  # playing the sequence
WAITING = 2  # child's turn
WIN = 3  # round complete — celebration
FAIL = 4  # wrong button — gentle cue
GAME_OVER = 5  # optional: after too many fails

# Timing (in frames, ~33 fps)
SHOW_STEP_FRAMES = 25  # how long each step lights up (~0.75s)
SHOW_GAP_FRAMES = 10  # gap between steps (~0.3s)
WIN_FRAMES = 60  # celebration duration (~1.8s)
FAIL_FRAMES = 45  # fail cue duration (~1.4s)

# Game config
NUM_BUTTONS = 6  # use buttons 0–5
START_LENGTH = 2  # initial sequence length (age 4 sweet spot)
MAX_FAILS = 3  # replays before game over

# Button colors (RGB, matching theme.BTN_RGB for buttons 0–5)
BTN_COLORS = [
    (255, 0, 0),  # Red
    (0, 255, 0),  # Green
    (0, 0, 255),  # Blue
    (255, 255, 0),  # Yellow
    (0, 255, 255),  # Cyan
    (255, 0, 255),  # Magenta
]


def _random_button():
    """Pick a random button index (0 to NUM_BUTTONS-1)."""
    return int.from_bytes(os.urandom(1), "big") % NUM_BUTTONS


class SimonEngine:
    """Stateful game engine for Pattern Copy.

    Pure logic — no hardware imports beyond patterns.
    Feed it button presses each frame and read back the current state.
    """

    def __init__(self, start_length=START_LENGTH):
        self._start_length = start_length
        self.reset()

    def reset(self):
        """Reset to initial state, ready for a new game."""
        self.state = READY
        self.sequence = []
        self.score = 0  # longest sequence completed
        self.high_score = 0
        self._input_pos = 0  # how far the child is in reproducing
        self._show_pos = 0  # which step we're showing
        self._state_frame = 0  # frame when current state started
        self._fail_count = 0
        self._active_btn = -1  # button currently lit during SHOWING

    def start_game(self):
        """Begin a new game: generate initial sequence, start showing."""
        self.sequence = [_random_button() for _ in range(self._start_length)]
        self.score = 0
        self._fail_count = 0
        self._begin_show(frame=0)

    def _begin_show(self, frame):
        """Start showing the sequence."""
        self.state = SHOWING
        self._show_pos = 0
        self._state_frame = frame
        self._active_btn = -1

    def _begin_wait(self, frame):
        """Start waiting for child input."""
        self.state = WAITING
        self._input_pos = 0
        self._state_frame = frame
        self._active_btn = -1

    @property
    def sequence_length(self):
        return len(self.sequence)

    @property
    def active_button(self):
        """Button index currently highlighted (-1 if none)."""
        return self._active_btn

    @property
    def show_progress(self):
        """How far through the showing phase (0.0 to 1.0)."""
        if self.state != SHOWING or not self.sequence:
            return 0.0
        return self._show_pos / len(self.sequence)

    @property
    def input_progress(self):
        """How far the child is through their turn (0.0 to 1.0)."""
        if self.state != WAITING or not self.sequence:
            return 0.0
        return self._input_pos / len(self.sequence)

    def update(self, btn_pressed, frame):
        """Call every frame. btn_pressed is the just-pressed button index (-1 if none).

        Returns the current state.
        """
        elapsed = frame - self._state_frame

        if self.state == READY:
            # Any button starts the game
            if btn_pressed >= 0:
                self.start_game()
                self._state_frame = frame
            return self.state

        elif self.state == SHOWING:
            return self._update_showing(frame, elapsed)

        elif self.state == WAITING:
            return self._update_waiting(btn_pressed, frame)

        elif self.state == WIN:
            if elapsed >= WIN_FRAMES:
                # Grow sequence and show next round
                self.sequence.append(_random_button())
                self._begin_show(frame)
            return self.state

        elif self.state == FAIL:
            if elapsed >= FAIL_FRAMES:
                if self._fail_count >= MAX_FAILS:
                    self.state = GAME_OVER
                    self._state_frame = frame
                else:
                    # Replay the same sequence
                    self._begin_show(frame)
            return self.state

        elif self.state == GAME_OVER:
            # Any button restarts
            if btn_pressed >= 0:
                self.reset()
                self.start_game()
                self._state_frame = frame
            return self.state

        return self.state

    def _update_showing(self, frame, elapsed):
        """Advance through the sequence display."""
        step_total = SHOW_STEP_FRAMES + SHOW_GAP_FRAMES
        pos = elapsed // step_total
        phase = elapsed % step_total

        if pos >= len(self.sequence):
            # Done showing — child's turn
            self._active_btn = -1
            self._begin_wait(frame)
            return self.state

        self._show_pos = pos
        if phase < SHOW_STEP_FRAMES:
            self._active_btn = self.sequence[pos]
        else:
            self._active_btn = -1  # gap

        return self.state

    def _update_waiting(self, btn_pressed, frame):
        """Check child's button press against the sequence."""
        if btn_pressed < 0:
            return self.state

        expected = self.sequence[self._input_pos]
        if btn_pressed == expected:
            self._active_btn = btn_pressed
            self._input_pos += 1
            if self._input_pos >= len(self.sequence):
                # Whole sequence correct!
                self.score = len(self.sequence)
                if self.score > self.high_score:
                    self.high_score = self.score
                self.state = WIN
                self._state_frame = frame
                self._active_btn = -1
        else:
            # Wrong button
            self._fail_count += 1
            self.state = FAIL
            self._state_frame = frame
            self._active_btn = btn_pressed

        return self.state

    def make_leds(self, frame, brightness=128):
        """Generate LED colors for the current game state.

        Buttons 0–5 map to LEDs 0–5 (first 6). LEDs 6–15 used for effects.
        """
        elapsed = frame - self._state_frame

        if self.state == READY:
            # Gentle breathing invite
            phase = (frame * 3) & 0xFF
            v = phase if phase < 128 else 255 - phase
            v = (v * brightness) >> 8
            for i in range(N_LEDS):
                h = (i * 255 // N_LEDS + frame) & 0xFF
                if h < 85:
                    c = (v, 0, 0)
                elif h < 170:
                    c = (0, v, 0)
                else:
                    c = (0, 0, v)
                _led_buf[i] = c
            return _led_buf

        elif self.state == SHOWING:
            # Light up the active button's LED
            for i in range(N_LEDS):
                _led_buf[i] = (0, 0, 0)
            if self._active_btn >= 0:
                color = BTN_COLORS[self._active_btn]
                c = scale(color, brightness)
                # Light the button's LED
                _led_buf[self._active_btn] = c
                # Also light the mirrored position on the second stick
                mirror = N_LEDS - 1 - self._active_btn
                if mirror != self._active_btn:
                    _led_buf[mirror] = scale(color, brightness // 3)
            return _led_buf

        elif self.state == WAITING:
            # Dim glow on valid buttons, bright flash on last correct press
            for i in range(N_LEDS):
                _led_buf[i] = (0, 0, 0)
            # Show which buttons are in play (dim)
            for i in range(NUM_BUTTONS):
                _led_buf[i] = scale(BTN_COLORS[i], brightness // 8)
            # Flash the last correctly pressed button
            if self._active_btn >= 0 and self._input_pos > 0:
                fade = max(0, 255 - elapsed * 20)
                if fade > 0:
                    c = scale(BTN_COLORS[self._active_btn], (fade * brightness) >> 8)
                    _led_buf[self._active_btn] = c
            return _led_buf

        elif self.state == WIN:
            # Rainbow chase celebration
            for i in range(N_LEDS):
                h = (i * 255 // N_LEDS + elapsed * 8) & 0xFF
                # Simple rainbow from hue
                if h < 85:
                    r, g, b = 255 - h * 3, h * 3, 0
                elif h < 170:
                    h2 = h - 85
                    r, g, b = 0, 255 - h2 * 3, h2 * 3
                else:
                    h2 = h - 170
                    r, g, b = h2 * 3, 0, 255 - h2 * 3
                _led_buf[i] = scale((r, g, b), brightness)
            return _led_buf

        elif self.state == FAIL:
            # Soft red pulse
            phase = (elapsed * 6) & 0xFF
            v = phase if phase < 128 else 255 - phase
            v = (v * brightness) >> 8
            c = (v, 0, 0)
            for i in range(N_LEDS):
                _led_buf[i] = c
            return _led_buf

        elif self.state == GAME_OVER:
            # Fade to dim warm glow
            v = max(10, brightness // 6)
            c = (v, v // 2, 0)
            for i in range(N_LEDS):
                _led_buf[i] = c
            return _led_buf

        # Fallback: all off
        for i in range(N_LEDS):
            _led_buf[i] = (0, 0, 0)
        return _led_buf
