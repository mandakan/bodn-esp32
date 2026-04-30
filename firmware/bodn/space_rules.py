# bodn/space_rules.py — Spaceship Cockpit rule engine (pure logic, testable on host)
#
# Open-ended pretend-play mode: every input controls a part of the spaceship.
# A friendly AI ("Stellar") announces random scenarios; the child resolves them.
# No fail state — scenarios resolve gently after two timeouts.
#
# Free-play mode: toggle switch sw1 ("stealth") disables scenarios entirely.
# The cockpit (throttle, steering, shields, button sounds, drone) keeps working;
# Stellar simply stops triggering events. Flipping stealth on mid-scenario
# cancels the current scenario gracefully.
#
# Targets executive functions at age 4+:
#   Working memory   — remember which system needs attention
#   Inhibitory control — wait for the right moment, then act
#   Cognitive flexibility — switch between different scenario types
#
# ─────────────────────────────────────────────────────────────────────────────
# INPUT MAP
# ─────────────────────────────────────────────────────────────────────────────
#
#   Encoder A (throttle)     — always tracked, drives engine drone pitch
#   Encoder B (steering)     — always tracked, drives steering indicator
#   Toggle sw0 (shields)     — always tracked; spoken confirmation on change
#   Toggle sw1 (stealth)     — always tracked; spoken confirmation on change
#   Buttons 0–7              — ambient ship-system sounds only (no scenario target)
#   Arcade 0–4               — scenario targets + PCA9685 LED brightness hints
#
# ─────────────────────────────────────────────────────────────────────────────
# ARCADE BUTTON ROLES  (fixed mapping — physical left-to-right)
# ─────────────────────────────────────────────────────────────────────────────
#
#   Index  Constant      Colour   Role              Sound file
#   ─────────────────────────────────────────────────────────
#     0    ARC_LAND      green    Landing           land.wav
#     1    ARC_COURSE    blue     Course correction course.wav
#     2    ARC_ENGINES   white    Engines           engines.wav
#     3    ARC_REPAIR    yellow   Repair            repair.wav
#     4    ARC_DISTRESS  red      Distress          distress.wav
#
#   LED brightness is 12-bit PWM (0–4095) via PCA9685.  The colour itself is
#   fixed hardware; only brightness changes.  Remap by changing the ARC_*
#   constants — the scenario logic references constants, not raw indices.
#
# ─────────────────────────────────────────────────────────────────────────────
# HOW TO ADD A SCENARIO
# ─────────────────────────────────────────────────────────────────────────────
#
#   1. Add a SC_* constant and increment NUM_SCENARIOS.
#   2. Add i18n keys (see firmware/bodn/lang/sv.py and en.py):
#        space_sc_<name>        — TTS announcement (full sentence)
#        space_sc_<name>_short  — short display label
#        space_instr_<name>     — on-screen instruction text
#   3. In _pick_scenario(): add an elif branch to set up scenario state
#      (e.g. pick a target arcade button via an ARC_* constant).
#   4. In _check_solution(): add an elif branch returning True when solved.
#   5. In make_static_leds(): add a branch for stick LED hint visuals.
#   6. In space.py _update_arcade_leds(): add the scenario to the
#      (SC_LANDING, SC_COURSE) tuple if an arcade LED should pulse.
#   7. In space.py _render_active(): add rendering for any on-screen hints.
#   8. Add TTS key to assets/audio/tts.json with "storage": "sd".
#   9. Add tests in tests/test_space_rules.py.

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

# Timing in milliseconds (wall-clock, frame-rate independent)
ANNOUNCE_MS = const(1500)  # AI speaks; input is accepted throughout
SUCCESS_MS = const(2000)  # celebration before returning to CRUISING
HINT_MS = const(1500)  # hint shown, then retry ACTIVE

# Timeout per difficulty level (milliseconds)
TIMEOUT_MS = [10000, 8000, 6000]  # level 1/2/3

# Cruise intervals in milliseconds: random within [BASE, BASE + SPREAD)
CRUISE_BASE_MS = const(20000)  # minimum ms between scenarios
CRUISE_SPREAD_MS = const(20000)  # additional random ms

# Arcade button roles — fixed mapping, physical left-to-right order.
# Indices are stable so future difficulty levels can remap without touching scenarios.
ARC_LAND = const(0)  # green  — landing
ARC_COURSE = const(1)  # blue   — course correction
ARC_ENGINES = const(2)  # white  — engines
ARC_REPAIR = const(3)  # yellow — repair
ARC_DISTRESS = const(4)  # red    — distress

# Arcade button colours matching the above roles
ARC_COLORS = [
    (0, 220, 50),  # ARC_LAND     green
    (0, 80, 255),  # ARC_COURSE   blue
    (220, 220, 220),  # ARC_ENGINES  white
    (255, 200, 0),  # ARC_REPAIR   yellow
    (255, 30, 0),  # ARC_DISTRESS red
]


def _rand8():
    """Return a random byte 0–255."""
    return int.from_bytes(os.urandom(1), "big")


def _rand16():
    """Return a random 0–65535."""
    return int.from_bytes(os.urandom(2), "big")


def _clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


class SpaceEngine:
    """Stateful engine for the Spaceship Cockpit mode.

    Pure logic — no hardware imports beyond patterns.
    Call update() every tick with dt (milliseconds since last tick).
    Returns an event string or None.

    Events:
        "announce"  — scenario picked; play TTS for scenario_type
        "success"   — correct action; play success audio
        "hint"      — first timeout; play hint audio
        "resolve"   — second timeout; scenario gently resolved
        "cruise"    — back to CRUISING after SUCCESS or free-play cancel
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

        # Timers (milliseconds)
        self._state_ms = 0  # ms accumulated in current state
        self._cruise_ms = 0  # ms accumulated during CRUISING
        self._cruise_target = CRUISE_BASE_MS + _rand16() % CRUISE_SPREAD_MS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, btn, arc, enc_a_delta, enc_b_delta, sw0, sw1, dt):
        """Call every tick.  Returns event string or None.

        Args:
            btn          -- just-pressed button index (0–7), -1 if none
            arc          -- just-pressed arcade button (0–4), -1 if none
            enc_a_delta  -- throttle encoder delta (signed detent count)
            enc_b_delta  -- steering encoder delta (signed detent count)
            sw0          -- toggle switch 0 state (bool)
            sw1          -- toggle switch 1 state (bool); True = free play
            dt           -- milliseconds since last tick (caller provides)
        """
        # Always update cockpit instruments (ambient feedback)
        self.throttle = _clamp(self.throttle + enc_a_delta * 8, 0, 255)
        self.steering = _clamp(self.steering + enc_b_delta * 8, -128, 127)
        self.shields_on = sw0

        prev_stealth = self.stealth
        self.stealth = sw1

        # Free play just turned on mid-scenario → cancel and return to cruise
        if sw1 and not prev_stealth and self.state != CRUISING:
            self._end_scenario()
            return "cruise"

        self._state_ms += dt

        if self.state == CRUISING:
            if sw1:
                # Free play: keep the cruise timer parked
                self._cruise_ms = 0
                return None
            self._cruise_ms += dt
            if self._cruise_ms >= self._cruise_target:
                return self._pick_scenario(sw0)

        elif self.state == ANNOUNCE:
            # Accept input throughout the announcement so the child never
            # has to wait for Stellar to finish talking.
            if self._check_solution(btn, arc, enc_a_delta, enc_b_delta, sw0):
                self._set_state(SUCCESS)
                self._successes += 1
                self._timeouts = 0
                self._adjust_difficulty()
                return "success"
            if self._state_ms >= ANNOUNCE_MS:
                self._set_state(ACTIVE)

        elif self.state == ACTIVE:
            if self._check_solution(btn, arc, enc_a_delta, enc_b_delta, sw0):
                self._set_state(SUCCESS)
                self._successes += 1
                self._timeouts = 0
                self._adjust_difficulty()
                return "success"
            if self._state_ms >= TIMEOUT_MS[self.difficulty - 1]:
                if not self._hinted:
                    self._hinted = True
                    self._set_state(HINT)
                    return "hint"
                else:
                    self._timeouts += 1
                    self._adjust_difficulty()
                    self._end_scenario()
                    return "resolve"

        elif self.state == HINT:
            if self._state_ms >= HINT_MS:
                self._set_state(ACTIVE)

        elif self.state == SUCCESS:
            if self._state_ms >= SUCCESS_MS:
                self._end_scenario()
                return "cruise"

        return None

    @property
    def active_timeout_ms(self):
        """Total timeout for the current difficulty level (ms)."""
        return TIMEOUT_MS[self.difficulty - 1]

    @property
    def active_elapsed_ms(self):
        """Milliseconds elapsed in the current ACTIVE/HINT phase."""
        return self._state_ms

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

    def _set_state(self, new_state):
        """Transition to a new state, resetting the state timer."""
        self.state = new_state
        self._state_ms = 0

    def _pick_scenario(self, sw0):
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
        self._set_state(ANNOUNCE)
        self._cruise_ms = 0
        self._hinted = False
        self._throttle_clicks = 0

        if sc == SC_COURSE:
            self._target_arc = ARC_COURSE
        elif sc == SC_LANDING:
            self._target_arc = ARC_LAND
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

    def _end_scenario(self):
        """Return to CRUISING with a fresh random interval."""
        self._set_state(CRUISING)
        self._cruise_ms = 0
        self.scenario_type = -1
        self._target_arc = -1
        self._cruise_target = CRUISE_BASE_MS + _rand16() % CRUISE_SPREAD_MS

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

        phase = (frame * 2) & 0xFF
        v = phase if phase < 128 else 255 - phase
        v = (v * brightness) >> 8
        c = _s((10, 20, 80), max(1, v))
        for i in range(n):
            buf[i] = c
        return buf
