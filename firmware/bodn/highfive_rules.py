# bodn/highfive_rules.py — High-Five Friends game engine (pure logic)
#
# Animals pop up on arcade buttons wanting high-fives. Tap the lit
# button before it disappears. Difficulty ramps over rounds.
#
# No hardware imports — testable on host with pytest.

from micropython import const

try:
    from urandom import getrandbits
except ImportError:
    from random import getrandbits

NUM_BUTTONS = const(5)

# Game states
READY = const(0)  # waiting to start
SHOWING = const(1)  # target is active, waiting for tap
HIT_FLASH = const(2)  # correct tap, brief celebration
MISS_FLASH = const(3)  # timeout, brief feedback
GAME_OVER = const(4)  # final screen

# Timing (milliseconds, wall-clock, frame-rate independent)
_HIT_MS = const(660)  # celebration
_MISS_MS = const(830)  # miss feedback
_READY_MS = const(1500)  # before first target
_GAP_MS = const(400)  # pause between targets
_GAME_OVER_MS = const(3000)  # before auto-restart

# Difficulty curve
_START_WINDOW_MS = const(2000)  # initial reaction window
_MIN_WINDOW_MS = const(500)  # fastest window
_WINDOW_SHRINK_MS = const(100)  # shrink per round
_TARGETS_PER_ROUND = const(5)  # hits before level-up
_MAX_MISSES = const(3)  # misses before game over


class HighFiveEngine:
    """Pure game logic for High-Five Friends.

    Call advance() every tick with dt (ms). Check state for current phase.
    """

    def __init__(self):
        self.state = READY
        self.score = 0
        self.streak = 0
        self.best_streak = 0
        self.high_score = 0
        self.round = 1
        self.misses = 0
        self.target = -1  # active button index, -1 = none
        self.round_hits = 0  # hits in current round
        self._state_ms = 0
        self._prev_target = -1
        self._window_ms = _START_WINDOW_MS

    @property
    def window_ms(self):
        """Current reaction window in milliseconds."""
        return self._window_ms

    @property
    def pulse_speed(self):
        """LED pulse speed (higher = more urgent)."""
        if self._window_ms > 1500:
            return 2
        if self._window_ms > 1000:
            return 3
        if self._window_ms > 700:
            return 4
        return 5

    def start(self, dt=0):
        """Begin a new game."""
        self.state = READY
        self.score = 0
        self.streak = 0
        self.best_streak = 0
        self.round = 1
        self.misses = 0
        self.target = -1
        self.round_hits = 0
        self._state_ms = 0
        self._prev_target = -1
        self._window_ms = _START_WINDOW_MS

    def advance(self, hit, miss, dt):
        """Advance the state machine by one tick.

        Args:
            hit: True if C driver detected a hit this frame
            miss: True if C driver detected a timeout this frame
            dt: milliseconds since last tick

        Returns:
            Current state after advancing.
        """
        self._state_ms += dt

        if self.state == READY:
            if self._state_ms >= _READY_MS:
                self._pick_target()
            return self.state

        if self.state == SHOWING:
            if hit:
                self.score += 1
                self.streak += 1
                if self.streak > self.best_streak:
                    self.best_streak = self.streak
                self.round_hits += 1
                self._set_state(HIT_FLASH)
            elif miss:
                self.streak = 0
                self.misses += 1
                self._set_state(MISS_FLASH)
            return self.state

        if self.state == HIT_FLASH:
            if self._state_ms >= _HIT_MS:
                if self.round_hits >= _TARGETS_PER_ROUND:
                    self._level_up()
                self._pick_target()
            return self.state

        if self.state == MISS_FLASH:
            if self._state_ms >= _MISS_MS:
                if self.misses >= _MAX_MISSES:
                    self._set_state(GAME_OVER)
                    self.target = -1
                    if self.score > self.high_score:
                        self.high_score = self.score
                else:
                    self._pick_target()
            return self.state

        if self.state == GAME_OVER:
            if self._state_ms >= _GAME_OVER_MS:
                self.start()
            return self.state

        return self.state

    def _set_state(self, new_state):
        """Transition to a new state, resetting the state timer."""
        self.state = new_state
        self._state_ms = 0

    def _pick_target(self):
        """Choose a random button (avoid repeating the same one)."""
        target = self._prev_target
        for _ in range(10):
            target = getrandbits(3) % NUM_BUTTONS
            if target != self._prev_target:
                break
        self._prev_target = target
        self.target = target
        self._set_state(SHOWING)

    def _level_up(self):
        """Advance to next round — shrink window, reset round hits."""
        self.round += 1
        self.round_hits = 0
        self._window_ms = max(_MIN_WINDOW_MS, self._window_ms - _WINDOW_SHRINK_MS)
