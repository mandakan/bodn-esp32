# bodn/hold_detector.py — detect intentional long-press (hold) on a button
#
# Pure logic — no hardware imports. Feed it held state and timestamps,
# get back progress and a one-shot trigger when the threshold is reached.


class HoldDetector:
    """Detect a sustained button hold exceeding a time threshold.

    Args:
        threshold_ms: How long the button must be held to trigger (default 1500ms).
    """

    def __init__(self, threshold_ms=1500):
        self.threshold_ms = threshold_ms
        self._hold_start = 0
        self._holding = False
        self._triggered = False
        self._progress = 0.0

    @property
    def holding(self):
        """True while the button is being held (before or after trigger)."""
        return self._holding

    @property
    def triggered(self):
        """True for one update cycle when the hold threshold is reached."""
        return self._triggered

    @property
    def progress(self):
        """0.0 to 1.0 — how far through the hold threshold."""
        return self._progress

    def update(self, held, now_ms):
        """Feed current held state and timestamp. Call once per frame.

        Returns True on the frame the threshold is reached (same as triggered).
        """
        self._triggered = False

        if held:
            if not self._holding:
                # Just started holding
                self._hold_start = now_ms
                self._holding = True

            elapsed = now_ms - self._hold_start
            self._progress = min(1.0, elapsed / self.threshold_ms)

            if self._progress >= 1.0 and elapsed < self.threshold_ms + 100:
                # Fire trigger once (within a small window after threshold)
                self._triggered = True
        else:
            self._holding = False
            self._progress = 0.0

        return self._triggered

    def reset(self):
        """Clear all state."""
        self._hold_start = 0
        self._holding = False
        self._triggered = False
        self._progress = 0.0
