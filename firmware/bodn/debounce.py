"""Software debouncing for buttons and encoder switches.

Pure logic — no hardware imports. Takes raw pin states and timestamps,
returns debounced events. This makes it easy to unit test on the host.
"""


class Debouncer:
    """Debounce a single active-low digital input.

    Args:
        delay_ms: Minimum stable time before a state change is accepted.
    """

    def __init__(self, delay_ms=50):
        self.delay_ms = delay_ms
        self._state = False  # debounced state: True = pressed
        self._last_raw = 1  # raw pin level (1 = released for active-low)
        self._last_change_ms = 0

    @property
    def pressed(self):
        return self._state

    def update(self, raw_value, now_ms):
        """Feed a new raw pin reading and the current time in ms.

        Returns the debounced state (True = pressed, False = released).
        """
        if raw_value != self._last_raw:
            self._last_raw = raw_value
            self._last_change_ms = now_ms

        if (now_ms - self._last_change_ms) >= self.delay_ms:
            self._state = self._last_raw == 0  # active-low
        return self._state

    def fell(self, raw_value, now_ms):
        """Returns True on the transition from released → pressed."""
        was = self._state
        now = self.update(raw_value, now_ms)
        return now and not was

    def rose(self, raw_value, now_ms):
        """Returns True on the transition from pressed → released."""
        was = self._state
        now = self.update(raw_value, now_ms)
        return not now and was
