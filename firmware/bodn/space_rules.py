# bodn/space_rules.py — Spaceship Cockpit rule engine (pure logic, testable on host)
#
# Open-ended pretend-play mode: every input controls a part of the spaceship.
# A friendly AI ("Stellar") announces random scenarios; the child resolves them.
# No fail state — scenarios resolve gently after two timeouts.
#
# Targets executive functions at age 4+:
#   Working memory   — remember which system needs attention
#   Inhibitory control — wait for the right moment, then act
#   Cognitive flexibility — switch between different scenario types

import os

from micropython import const
from bodn.patterns import N_STICKS, scale, _led_buf, _BLACK

# --- States ---
CRUISING = const(0)  # flying freely, no active scenario
ANNOUNCE = const(1)  # scenario picked, AI is announcing it
ACTIVE = const(2)  # child must respond within timeout
SUCCESS = const(3)  # correct action — celebration
HINT = const(4)  # first timeout — show hint, then retry

# --- Scenario types ---
SC_ASTEROID = const(0)  # turn steering encoder to dodge
SC_COURSE = const(1)  # press the indicated arcade button (LED pulses)
SC_SHIELD = const(2)  # flip toggle switch 0 ON
SC_ENGINE = const(3)  # push throttle encoder up (N clicks)
SC_LANDING = const(4)  # press the indicated arcade button

NUM_SCENARIOS = const(5)

# Timing in frames (~30 fps)
ANNOUNCE_FRAMES = const(60)  # AI speaks, then ACTIVE starts (~2 s)
SUCCESS_FRAMES = const(60)  # celebration before returning to CRUISING (~2 s)
HINT_FRAMES = const(45)  # hint shown, then retry ACTIVE (~1.5 s)

# Timeout per difficulty level (frames)
TIMEOUTS = [240, 180, 150]  # level 1/2/3 → 8 s / 6 s / 5 s

# Cruise intervals: random within [BASE, BASE + SPREAD)
CRUISE_BASE = const(200)  # minimum frames between scenarios (~6.5 s)
CRUISE_SPREAD = const(150)  # additional random frames (~5 s)

# Arcade button colours — physical left-to-right order
ARC_COLORS = [
    (0, 220, 50),  # 0 green
    (0, 80, 255),  # 1 blue
    (220, 220, 220),  # 2 white
    (255, 200, 0),  # 3 yellow
    (255, 30, 0),  # 4 red
]


def _rand8():
    """Return a random byte 0–255."""
    return int.from_bytes(os.urandom(1), "big")


def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


class SpaceEngine:
    """Stateful engine for the Spaceship Cockpit mode.

    Pure logic — no hardware imports beyond patterns.
    Call update() every frame; it returns an event string or None.

    Events:
        "announce"  — scenario picked; play TTS for scenario_type
        "success"   — correct action; play success audio
        "hint"      — first timeout; play hint audio
        "resolve"   — second timeout; scenario gently resolved
    """

    def __init__(self):
        self.reset()

    def reset(self):
        # Cockpit state (always tracked, drives ambient feedback)
        self.throttle = 128  # 0–255 (engine speed)
        self.steering = 0  # -128..127 (course heading offset)
        self.shields_on = False
        self.stealth = False

        # Scenario state
        self.state = CRUISING
        self.scenario_type = -1  # SC_* constant, -1 = none
        self.difficulty = 1  # 1–3; adapts over time
        self._successes = 0  # consecutive successes at current level
        self._timeouts = 0  # consecutive timeouts at current level

        # Internal scenario details
        self._target_arc = -1  # SC_COURSE / SC_LANDING: which arcade button
        self._steer_dir = 1  # SC_ASTEROID: 1=right, -1=left
        self._throttle_clicks = 0  # SC_ENGINE: clicks accumulated
        self._throttle_needed = 3  # SC_ENGINE: clicks required
        self._sw0_was_on = False  # SC_SHIELD: sw0 state at scenario start
        self._hinted = False  # whether HINT phase was already shown

        # Timers
        self._state_frame = 0
        self._timer = 0
        self._cruise_countdown = CRUISE_BASE + _rand8() % CRUISE_SPREAD

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, btn, arc, enc_a_delta, enc_b_delta, sw0, sw1, frame):
        """Call every frame.  Returns event string or None.

        Args:
            btn          -- just-pressed button index (0–7), -1 if none
            arc          -- just-pressed arcade button (0–4), -1 if none
            enc_a_delta  -- throttle encoder delta (signed detent count)
            enc_b_delta  -- steering encoder delta (signed detent count)
            sw0          -- toggle switch 0 state (bool)
            sw1          -- toggle switch 1 state (bool)
            frame        -- current frame counter
        """
        # Always update cockpit instruments (ambient feedback)
        self.throttle = _clamp(self.throttle + enc_a_delta * 8, 0, 255)
        self.steering = _clamp(self.steering + enc_b_delta * 8, -128, 127)
        self.shields_on = sw0
        self.stealth = sw1

        elapsed = frame - self._state_frame

        if self.state == CRUISING:
            self._timer += 1
            if self._timer >= self._cruise_countdown:
                return self._pick_scenario(frame, sw0)

        elif self.state == ANNOUNCE:
            if elapsed >= ANNOUNCE_FRAMES:
                self.state = ACTIVE
                self._state_frame = frame

        elif self.state == ACTIVE:
            if self._check_solution(btn, arc, enc_a_delta, enc_b_delta, sw0):
                self.state = SUCCESS
                self._state_frame = frame
                self._successes += 1
                self._timeouts = 0
                self._adjust_difficulty()
                return "success"
            if elapsed >= TIMEOUTS[self.difficulty - 1]:
                if not self._hinted:
                    self._hinted = True
                    self.state = HINT
                    self._state_frame = frame
                    return "hint"
                else:
                    self._timeouts += 1
                    self._adjust_difficulty()
                    self._end_scenario(frame)
                    return "resolve"

        elif self.state == HINT:
            if elapsed >= HINT_FRAMES:
                self.state = ACTIVE
                self._state_frame = frame

        elif self.state == SUCCESS:
            if elapsed >= SUCCESS_FRAMES:
                self._end_scenario(frame)

        return None

    @property
    def target_color(self):
        """RGB of the target input for the current scenario, or None."""
        if self.scenario_type in (SC_COURSE, SC_LANDING) and self._target_arc >= 0:
            return ARC_COLORS[self._target_arc]
        if self.scenario_type == SC_SHIELD:
            return (255, 50, 50)
        if self.scenario_type == SC_ENGINE:
            return (255, 160, 0)
        if self.scenario_type == SC_ASTEROID:
            return (255, 100, 0)
        return None

    @property
    def target_arc_idx(self):
        """Arcade button index for SC_COURSE or SC_LANDING, -1 otherwise."""
        return self._target_arc

    @property
    def steer_dir(self):
        """Steering direction for SC_ASTEROID: 1=right, -1=left."""
        return self._steer_dir

    @property
    def engine_progress(self):
        """0.0..1.0 completion for SC_ENGINE throttle push."""
        if self._throttle_needed == 0:
            return 1.0
        return min(1.0, self._throttle_clicks / self._throttle_needed)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _pick_scenario(self, frame, sw0):
        """Choose and configure a random scenario."""
        # Avoid SC_SHIELD if shields are already on
        candidates = list(range(NUM_SCENARIOS))
        if sw0:
            candidates = [c for c in candidates if c != SC_SHIELD]
        if not candidates:
            candidates = [SC_ASTEROID, SC_COURSE, SC_ENGINE, SC_LANDING]

        r = _rand8() % len(candidates)
        sc = candidates[r]
        self.scenario_type = sc
        self.state = ANNOUNCE
        self._state_frame = frame
        self._timer = 0
        self._hinted = False
        self._throttle_clicks = 0

        if sc == SC_COURSE:
            self._target_arc = _rand8() % 5
        elif sc == SC_LANDING:
            self._target_arc = _rand8() % 5
        elif sc == SC_ASTEROID:
            self._steer_dir = 1 if (_rand8() & 1) else -1
        elif sc == SC_ENGINE:
            self._throttle_needed = 3 + self.difficulty
        elif sc == SC_SHIELD:
            self._sw0_was_on = sw0

        return "announce"

    def _check_solution(self, btn, arc, enc_a_delta, enc_b_delta, sw0):
        """Return True if the child has performed the required action."""
        sc = self.scenario_type
        if sc == SC_ASTEROID:
            # Correct steering direction
            return enc_b_delta * self._steer_dir > 0
        elif sc == SC_COURSE:
            return arc == self._target_arc
        elif sc == SC_SHIELD:
            return sw0 and not self._sw0_was_on
        elif sc == SC_ENGINE:
            if enc_a_delta > 0:
                self._throttle_clicks += enc_a_delta
            return self._throttle_clicks >= self._throttle_needed
        elif sc == SC_LANDING:
            return arc == self._target_arc
        return False

    def _adjust_difficulty(self):
        """Increment or decrement difficulty based on recent performance."""
        if self._successes >= 3 and self.difficulty < 3:
            self.difficulty += 1
            self._successes = 0
        elif self._timeouts >= 2 and self.difficulty > 1:
            self.difficulty -= 1
            self._timeouts = 0

    def _end_scenario(self, frame):
        """Return to CRUISING with a fresh random interval."""
        self.state = CRUISING
        self._timer = 0
        self._state_frame = frame
        self.scenario_type = -1
        self._target_arc = -1
        self._cruise_countdown = CRUISE_BASE + _rand8() % CRUISE_SPREAD

    # ------------------------------------------------------------------
    # LED generation (sticks only — lid ring handled by screen)
    # ------------------------------------------------------------------

    def make_static_leds(self, brightness=128):
        """Return LED buffer for stick LEDs (indices 0–15).

        The lid ring (indices 16–107) is left untouched and written by
        the screen's zone_* helpers.
        """
        buf = _led_buf
        n = N_STICKS
        black = _BLACK
        _s = scale

        if self.state == CRUISING or self.state == ANNOUNCE:
            # Dim blue-purple ambient
            c = _s((10, 20, 80), brightness // 3)
            for i in range(n):
                buf[i] = c
            return buf

        elif self.state == ACTIVE or self.state == HINT:
            for i in range(n):
                buf[i] = black
            sc = self.scenario_type
            if sc == SC_ASTEROID:
                # Arrow on sticks: right side (B) for right, left side (A) for left
                arrow_col = _s((255, 80, 0), brightness // 2)
                if self._steer_dir > 0:  # steer right → light stick B
                    for i in range(8, 16):
                        buf[i] = arrow_col
                else:  # steer left → light stick A
                    for i in range(0, 8):
                        buf[i] = arrow_col
            elif sc == SC_COURSE and self._target_arc >= 0:
                # Sticks glow with the target arcade button's colour as ambient hint
                c = _s(ARC_COLORS[self._target_arc], brightness // 3)
                for i in range(n):
                    buf[i] = c
            elif sc == SC_SHIELD:
                # Alternating red warning
                c = _s((255, 0, 0), brightness // 2)
                for i in range(0, n, 2):
                    buf[i] = c
            elif sc == SC_ENGINE:
                # Fill based on throttle-click progress
                filled = min(n, int(self.engine_progress * n))
                c = _s((255, 140, 0), brightness)
                for i in range(filled):
                    buf[i] = c
            elif sc == SC_LANDING:
                # Slow green pulse — actual arcade LED handled by screen
                c = _s((0, 180, 60), brightness // 3)
                for i in range(n):
                    buf[i] = c
            return buf

        elif self.state == SUCCESS:
            g = _s((0, 255, 80), brightness)
            for i in range(n):
                buf[i] = g
            return buf

        # Fallback: all off
        for i in range(n):
            buf[i] = black
        return buf

    def make_leds(self, frame, brightness=128):
        """Animated version — used by Demo / home carousel preview."""
        buf = _led_buf
        n = N_STICKS
        _s = scale
        _hsv = None  # avoid import at module level; inline if needed

        phase = (frame * 2) & 0xFF
        v = phase if phase < 128 else 255 - phase
        v = (v * brightness) >> 8
        c = _s((10, 20, 80), max(1, v))
        for i in range(n):
            buf[i] = c
        return buf
