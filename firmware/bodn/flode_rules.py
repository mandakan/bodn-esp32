# bodn/flode_rules.py — Flöde game logic (pure, no hardware)
#
# Puzzle: align horizontal gaps in vertical wall segments so a flow
# can pass from left to right across the screen.

from micropython import const

# Game states
PLAYING = const(0)
COMPLETE = const(1)
FLOWING = const(3)  # flow animation — shows WHY the solution works
CELEBRATE = const(2)

# Level definitions: (num_segments, num_positions, gap_slots)
# gap_slots = how many snap positions the gap spans (larger = easier)
_LEVELS = (
    # Level 1–2: intro (1–2 segments, 3 positions)
    (1, 3),
    (2, 3),
    # Level 3–4: easy (3–4 segments, 4 positions)
    (3, 4),
    (4, 4),
    # Level 5–6: medium (5–6 segments, 5 positions)
    (5, 5),
    (6, 6),
)

MAX_LEVEL = const(6)

# Flow animation: frames per segment (~30ms each)
FLOW_FRAMES_PER_SEG = const(12)  # ~360ms per segment

# Celebration duration in frames (~30ms each)
CELEBRATE_FRAMES = const(60)  # ~1.8 seconds


class FlodeEngine:
    """Pure game logic for Flöde.

    Positions are integers 0..num_positions-1 representing snap slots.
    The screen maps these to pixel coordinates.
    """

    def __init__(self, rand_fn=None):
        self._rand = rand_fn  # rand_fn(n) returns 0..n-1
        self.level = 0
        self.num_segments = 0
        self.num_positions = 0
        self.positions = []  # current gap position per segment
        self.target = 0  # target gap position (flow height)
        self.selected = 0  # currently selected segment index
        self.state = PLAYING
        self._celebrate_frame = 0
        self._flow_frame = 0
        self._flow_progress = 0  # 0..num_segments*FLOW_FRAMES_PER_SEG

    def start_level(self, level):
        """Set up a new level. Level is 1-based."""
        self.level = min(level, MAX_LEVEL)
        idx = self.level - 1
        self.num_segments, self.num_positions = _LEVELS[idx]
        self.selected = 0
        self.state = PLAYING
        self._celebrate_frame = 0
        self._generate()

    def _generate(self):
        """Randomize target and segment positions."""
        rand = self._rand
        n_pos = self.num_positions
        n_seg = self.num_segments

        self.target = rand(n_pos)
        self.positions = []
        for _ in range(n_seg):
            # Pick a position different from target
            p = rand(n_pos - 1)
            if p >= self.target:
                p += 1
            self.positions.append(p)

    def select_delta(self, d):
        """Move segment selection by d (wraps). Returns True if changed."""
        if self.num_segments <= 1 or self.state != PLAYING:
            return False
        old = self.selected
        self.selected = (self.selected + d) % self.num_segments
        return self.selected != old

    def shift(self, d):
        """Shift selected segment by d positions (clamped). Returns True if changed.

        Does NOT check completion — the screen should check after
        snap animations finish so the child sees the piece land.
        """
        if self.state != PLAYING:
            return False
        old = self.positions[self.selected]
        new = max(0, min(self.num_positions - 1, old + d))
        if new == old:
            return False
        self.positions[self.selected] = new
        return True

    def check_complete(self):
        """Check if all gaps are aligned. Call after animations finish."""
        if self.state == PLAYING and self.flow_reaches() == self.num_segments:
            self.state = COMPLETE
            return True
        return False

    def flow_reaches(self):
        """Return how many segments from left the flow passes through.

        0 = blocked at first, num_segments = all aligned.
        """
        target = self.target
        for i, p in enumerate(self.positions):
            if p != target:
                return i
        return self.num_segments

    def start_flowing(self):
        """Transition from COMPLETE to FLOWING — animate the solution."""
        if self.state == COMPLETE:
            self.state = FLOWING
            self._flow_frame = 0
            self._flow_progress = 0

    def update_flowing(self):
        """Advance flow animation. Returns True when done."""
        if self.state != FLOWING:
            return False
        self._flow_frame += 1
        total = (self.num_segments + 1) * FLOW_FRAMES_PER_SEG
        self._flow_progress = self._flow_frame
        if self._flow_frame >= total:
            return True
        return False

    @property
    def flow_anim_reaches(self):
        """How many segments the animated flow has reached (fractional as 0-256 per seg)."""
        if self.state != FLOWING:
            return 0
        segs = self._flow_frame * 256 // (FLOW_FRAMES_PER_SEG * (self.num_segments + 1))
        return min(segs, (self.num_segments + 1) * 256)

    def start_celebration(self):
        """Transition to CELEBRATE."""
        self.state = CELEBRATE
        self._celebrate_frame = 0

    def update_celebration(self):
        """Advance celebration timer. Returns True when done."""
        if self.state != CELEBRATE:
            return False
        self._celebrate_frame += 1
        return self._celebrate_frame >= CELEBRATE_FRAMES

    @property
    def celebrate_progress(self):
        """0.0 to 1.0 celebration progress (integer fraction)."""
        if self.state != CELEBRATE:
            return 0
        return min(self._celebrate_frame * 100 // CELEBRATE_FRAMES, 100)

    def has_next_level(self):
        """Return True if there's a harder level available."""
        return self.level < MAX_LEVEL
