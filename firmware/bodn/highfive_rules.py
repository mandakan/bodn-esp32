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

# Timing (frames at ~30 fps)
_HIT_FRAMES = const(20)  # ~660 ms celebration
_MISS_FRAMES = const(25)  # ~830 ms miss feedback
_READY_FRAMES = const(45)  # ~1.5 s before first target
_GAP_FRAMES = const(12)  # ~400 ms pause between targets
_GAME_OVER_FRAMES = const(90)  # ~3 s before auto-restart

# Difficulty curve
_START_WINDOW_MS = const(2000)  # initial reaction window
_MIN_WINDOW_MS = const(500)  # fastest window
_WINDOW_SHRINK_MS = const(100)  # shrink per round
_TARGETS_PER_ROUND = const(5)  # hits before level-up
_MAX_MISSES = const(3)  # misses before game over


class HighFiveEngine:
    """Pure game logic for High-Five Friends.

    Call advance() every frame. Check state for current phase.
    Uses frame counting for animations and wall-clock ms for
    the reaction window (passed to C LED driver).
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
        self._state_frame = 0
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

    def start(self, frame):
        """Begin a new game."""
        self.state = READY
        self.score = 0
        self.streak = 0
        self.best_streak = 0
        self.round = 1
        self.misses = 0
        self.target = -1
        self.round_hits = 0
        self._state_frame = frame
        self._prev_target = -1
        self._window_ms = _START_WINDOW_MS

    def advance(self, hit, miss, frame):
        """Advance the state machine by one frame.

        Args:
            hit: True if C driver detected a hit this frame
            miss: True if C driver detected a timeout this frame
            frame: current frame counter

        Returns:
            Current state after advancing.
        """
        elapsed = frame - self._state_frame

        if self.state == READY:
            if elapsed >= _READY_FRAMES:
                self._pick_target(frame)
            return self.state

        if self.state == SHOWING:
            if hit:
                self.score += 1
                self.streak += 1
                if self.streak > self.best_streak:
                    self.best_streak = self.streak
                self.round_hits += 1
                self.state = HIT_FLASH
                self._state_frame = frame
            elif miss:
                self.streak = 0
                self.misses += 1
                self.state = MISS_FLASH
                self._state_frame = frame
            return self.state

        if self.state == HIT_FLASH:
            if elapsed >= _HIT_FRAMES:
                if self.round_hits >= _TARGETS_PER_ROUND:
                    self._level_up()
                self._pick_target(frame)
            return self.state

        if self.state == MISS_FLASH:
            if elapsed >= _MISS_FRAMES:
                if self.misses >= _MAX_MISSES:
                    self.state = GAME_OVER
                    self._state_frame = frame
                    self.target = -1
                    if self.score > self.high_score:
                        self.high_score = self.score
                else:
                    self._pick_target(frame)
            return self.state

        if self.state == GAME_OVER:
            if elapsed >= _GAME_OVER_FRAMES:
                self.start(frame)
            return self.state

        return self.state

    def _pick_target(self, frame):
        """Choose a random button (avoid repeating the same one)."""
        target = self._prev_target
        for _ in range(10):
            target = getrandbits(3) % NUM_BUTTONS
            if target != self._prev_target:
                break
        self._prev_target = target
        self.target = target
        self.state = SHOWING
        self._state_frame = frame

    def _level_up(self):
        """Advance to next round — shrink window, reset round hits."""
        self.round += 1
        self.round_hits = 0
        self._window_ms = max(_MIN_WINDOW_MS, self._window_ms - _WINDOW_SHRINK_MS)
