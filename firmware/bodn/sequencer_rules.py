# bodn/sequencer_rules.py — Loop sequencer engine (pure logic, testable on host)
#
# Grid-based step sequencer with live-jam quantization.
# 5 percussion tracks (arcade buttons) + 1 melody track (mini buttons).
# No hardware imports — the screen passes delta_ms each frame.

try:
    from micropython import const
except ImportError:

    def const(x):
        return x


# Engine states
STOPPED = const(0)
PLAYING = const(1)

# Defaults and limits
DEFAULT_BPM = const(90)
MIN_BPM = const(70)
MAX_BPM = const(140)
BPM_STEP = const(5)

NUM_PERC_TRACKS = const(5)
NUM_MELODY_NOTES = const(8)

# Pentatonic scale C major across two octaves (btn index → Hz)
MELODY_FREQS = (262, 294, 330, 392, 440, 523, 587, 659)


class SequencerEngine:
    """Pure-logic loop sequencer engine.

    The grid stores percussion hits (0/1 per track per step) and melody
    notes (0 = off, 1-8 = mini button index + 1).  The caller drives
    the clock by passing elapsed milliseconds via advance().
    """

    def __init__(self, n_steps=8):
        self.n_steps = n_steps
        self.perc = [bytearray(n_steps) for _ in range(NUM_PERC_TRACKS)]
        self.melody = bytearray(n_steps)
        self.state = STOPPED
        self.bpm = DEFAULT_BPM
        self.step = 0
        self._ms_accum = 0
        self._ms_per_step = 0
        self._frac = 0.0
        self.step_advanced = False
        self.dirty_steps = set()
        self._recompute_timing()

    # ------------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------------

    def _recompute_timing(self):
        """Recompute ms_per_step from bpm and n_steps.

        A bar is always 4 beats regardless of step count.
        8 steps → 2 steps per beat, 16 steps → 4 steps per beat.
        """
        self._ms_per_step = 60_000 * 4 // (self.bpm * self.n_steps)

    def advance(self, delta_ms):
        """Accumulate time and advance the playhead.

        Returns True if the step index changed this call.
        """
        self.step_advanced = False
        if self.state != PLAYING:
            return False
        self._ms_accum += delta_ms
        while self._ms_accum >= self._ms_per_step:
            self._ms_accum -= self._ms_per_step
            self.step = (self.step + 1) % self.n_steps
            self.step_advanced = True
        # Fractional position for quantization
        if self._ms_per_step > 0:
            self._frac = self.step + self._ms_accum / self._ms_per_step
        return self.step_advanced

    def nearest_step(self):
        """Return the grid step closest to the current fractional position."""
        return round(self._frac) % self.n_steps

    # ------------------------------------------------------------------
    # Grid editing
    # ------------------------------------------------------------------

    def toggle_perc(self, track, step=None):
        """Toggle a percussion hit. Returns (step, new_value)."""
        if step is None:
            step = self.nearest_step()
        new_val = 0 if self.perc[track][step] else 1
        self.perc[track][step] = new_val
        self.dirty_steps.add(step)
        return step, new_val

    def set_melody(self, btn_idx, step=None):
        """Set or erase a melody note. Returns (step, new_value).

        Same button on same step erases; different button overwrites.
        """
        if step is None:
            step = self.nearest_step()
        val = btn_idx + 1
        if self.melody[step] == val:
            self.melody[step] = 0
            new_val = 0
        else:
            self.melody[step] = val
            new_val = val
        self.dirty_steps.add(step)
        return step, new_val

    def get_step_sounds(self, step):
        """Return (perc_active, melody_val) for a given step.

        perc_active is a list of 5 bools; melody_val is 0 or 1-8.
        """
        perc_active = [bool(self.perc[t][step]) for t in range(NUM_PERC_TRACKS)]
        return perc_active, self.melody[step]

    # ------------------------------------------------------------------
    # Transport controls
    # ------------------------------------------------------------------

    def start(self):
        if self.state != PLAYING:
            self.state = PLAYING
            self._ms_accum = 0

    def stop(self):
        self.state = STOPPED

    def set_bpm(self, bpm):
        self.bpm = max(MIN_BPM, min(MAX_BPM, bpm))
        self._recompute_timing()

    def set_steps(self, n):
        """Resize grid to n steps (8 or 16).

        8→16: duplicate the pattern into the second half.
        16→8: keep only the first 8 steps.
        """
        if n == self.n_steps:
            return
        old_n = self.n_steps
        self.n_steps = n
        if n > old_n:
            # Expand: duplicate pattern
            for t in range(NUM_PERC_TRACKS):
                new_track = bytearray(n)
                new_track[:old_n] = self.perc[t]
                new_track[old_n:n] = self.perc[t][: n - old_n]
                self.perc[t] = new_track
            new_mel = bytearray(n)
            new_mel[:old_n] = self.melody
            new_mel[old_n:n] = self.melody[: n - old_n]
            self.melody = new_mel
        else:
            # Shrink: truncate
            for t in range(NUM_PERC_TRACKS):
                self.perc[t] = self.perc[t][:n]
            self.melody = self.melody[:n]
        self.step = self.step % n
        self._ms_accum = 0
        self._recompute_timing()

    def clear_all(self):
        """Zero all grid data and reset the playhead."""
        for t in range(NUM_PERC_TRACKS):
            for i in range(self.n_steps):
                self.perc[t][i] = 0
        for i in range(self.n_steps):
            self.melody[i] = 0
        self.step = 0
        self._ms_accum = 0
        self._frac = 0.0
