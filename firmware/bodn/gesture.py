# bodn/gesture.py — per-channel gesture detection (tap, double-tap, long-press)
#
# Pure logic — no hardware imports.  Feed held/just_pressed/just_released
# arrays and a timestamp, get back one-shot gesture events and continuous
# hold state.  Designed for 20 Hz frame loop with zero per-frame allocation.

from micropython import const

_ST_IDLE = const(0)
_ST_PRESSED = const(1)
_ST_WAIT_DOUBLE = const(2)
_ST_DOUBLE_PRESSED = const(3)

_DEFAULT_LONG_MS = const(1500)
_DEFAULT_DOUBLE_MS = const(250)


class GestureDetector:
    """Multi-channel gesture detector for buttons and encoder buttons.

    Args:
        n: number of channels (e.g. 8 buttons + 3 encoder buttons = 11).
        long_press_ms: hold duration before long-press fires (default 1500).
        double_tap_ms: max gap between taps for double-tap (default 250).
    """

    def __init__(
        self, n, long_press_ms=_DEFAULT_LONG_MS, double_tap_ms=_DEFAULT_DOUBLE_MS
    ):
        self._n = n
        self._long_ms = long_press_ms
        self._double_ms = double_tap_ms

        # Per-channel state machine
        self._state = [_ST_IDLE] * n
        self._press_start = [0] * n
        self._release_time = [0] * n
        self._long_fired = [False] * n  # prevents re-firing long_press

        # Per-channel config
        self._double_enabled = [False] * n  # opt-in per channel

        # One-shot output flags (cleared each update)
        self.tap = [False] * n
        self.double_tap = [False] * n
        self.long_press = [False] * n
        self.released = [False] * n

        # Continuous state
        self.holding = [False] * n
        self.long_progress = [0.0] * n

    def set_double_tap(self, channel, enabled):
        """Enable or disable double-tap detection for a channel.

        When disabled (default), taps fire immediately on release.
        When enabled, taps are delayed by double_tap_ms to allow a
        second press to be detected.
        """
        self._double_enabled[channel] = enabled

    def update(self, held, just_pressed, just_released, now_ms):
        """Advance all channels one frame.  Call once per frame after debouncing.

        Args:
            held: list[bool] — button currently down.
            just_pressed: list[bool] — rising edge this frame.
            just_released: list[bool] — falling edge this frame.
            now_ms: int — current time in milliseconds.
        """
        # Cache as locals
        n = self._n
        state = self._state
        press_start = self._press_start
        release_time = self._release_time
        long_fired = self._long_fired
        double_enabled = self._double_enabled
        long_ms = self._long_ms
        double_ms = self._double_ms

        tap = self.tap
        dtap = self.double_tap
        lp = self.long_press
        rel = self.released
        holding = self.holding
        prog = self.long_progress

        for i in range(n):
            # Clear one-shot flags
            tap[i] = False
            dtap[i] = False
            lp[i] = False
            rel[i] = just_released[i]
            holding[i] = held[i]

            s = state[i]

            if s == _ST_IDLE:
                prog[i] = 0.0
                if just_pressed[i]:
                    state[i] = _ST_PRESSED
                    press_start[i] = now_ms
                    long_fired[i] = False

            elif s == _ST_PRESSED:
                elapsed = now_ms - press_start[i]
                prog[i] = min(1.0, elapsed / long_ms) if long_ms > 0 else 1.0

                if not long_fired[i] and elapsed >= long_ms:
                    lp[i] = True
                    long_fired[i] = True

                if just_released[i]:
                    if long_fired[i]:
                        # Was a long press — just go idle
                        state[i] = _ST_IDLE
                        prog[i] = 0.0
                    elif double_enabled[i]:
                        # Short press — wait for possible second tap
                        state[i] = _ST_WAIT_DOUBLE
                        release_time[i] = now_ms
                    else:
                        # Double-tap disabled — fire tap immediately
                        tap[i] = True
                        state[i] = _ST_IDLE
                        prog[i] = 0.0

            elif s == _ST_WAIT_DOUBLE:
                prog[i] = 0.0
                if just_pressed[i]:
                    state[i] = _ST_DOUBLE_PRESSED
                    press_start[i] = now_ms
                    long_fired[i] = False
                elif now_ms - release_time[i] > double_ms:
                    # Window expired — it was a single tap
                    tap[i] = True
                    state[i] = _ST_IDLE

            elif s == _ST_DOUBLE_PRESSED:
                elapsed = now_ms - press_start[i]
                prog[i] = min(1.0, elapsed / long_ms) if long_ms > 0 else 1.0

                if just_released[i]:
                    dtap[i] = True
                    state[i] = _ST_IDLE
                    prog[i] = 0.0
                elif not long_fired[i] and elapsed >= long_ms:
                    # Held too long on second press — treat as long press
                    lp[i] = True
                    long_fired[i] = True

    def reset(self):
        """Clear all state back to idle."""
        n = self._n
        for i in range(n):
            self._state[i] = _ST_IDLE
            self._press_start[i] = 0
            self._release_time[i] = 0
            self._long_fired[i] = False
            self.tap[i] = False
            self.double_tap[i] = False
            self.long_press[i] = False
            self.released[i] = False
            self.holding[i] = False
            self.long_progress[i] = 0.0

    def reset_channel(self, i):
        """Clear state for a single channel."""
        self._state[i] = _ST_IDLE
        self._press_start[i] = 0
        self._release_time[i] = 0
        self._long_fired[i] = False
        self.tap[i] = False
        self.double_tap[i] = False
        self.long_press[i] = False
        self.released[i] = False
        self.holding[i] = False
        self.long_progress[i] = 0.0
