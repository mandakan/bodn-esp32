# bodn/ui/overlay.py — session-aware display overlay

from bodn.session import (
    WARN_5,
    WARN_2,
    WINDDOWN,
    SLEEPING,
    COOLDOWN,
    LOCKDOWN,
    IDLE,
)
from bodn.patterns import scale, N_LEDS
from bodn.ui.screen import Screen


class SessionOverlay(Screen):
    """Draws session blocking states on the primary display.

    The running timer has moved to the secondary display (AmbientClock).
    This overlay only renders for blocking states (winddown, sleeping,
    cooldown, lockdown) that take over the whole screen.
    """

    _TAKEOVER_STATES = (SLEEPING, COOLDOWN, LOCKDOWN, WINDDOWN)

    def __init__(self, session_mgr):
        self.session_mgr = session_mgr
        self._prev_state = None
        self._dirty = True

    @property
    def takes_over(self):
        return self.session_mgr.state in self._TAKEOVER_STATES

    def needs_redraw(self):
        return self._dirty

    def update(self, inp, frame):
        state = self.session_mgr.state
        # Wake from IDLE on any button press
        if state == IDLE and inp.any_btn_pressed():
            self.session_mgr.try_wake()

        # Track state changes
        if state != self._prev_state:
            self._prev_state = state
            self._dirty = True

        # Blinking states need periodic redraws
        if state == WINDDOWN and frame % 20 == 0:
            self._dirty = True

    def render(self, tft, theme, frame):
        self._dirty = False
        state = self.session_mgr.state

        if state == WINDDOWN:
            if (frame // 20) % 2 == 0:
                tft.text("Zzz...", 40, 70, theme.AMBER)

        elif state in (SLEEPING, COOLDOWN):
            tft.text("Zzz", 52, 60, theme.BLUE)
            tft.text("See you", 36, 80, theme.WHITE)
            tft.text("soon!", 44, 96, theme.WHITE)

        elif state == LOCKDOWN:
            tft.text("Goodnight!", 24, 70, theme.MAGENTA)

    def led_override(self, state, frame, leds, brightness):
        """Modify LED output based on session state. Writes into leds in-place."""
        if state == WARN_5:
            if (frame // 30) % 2 == 0:
                c = scale((255, 191, 0), brightness)
                for i in range(N_LEDS):
                    leds[i] = c
            return leds

        elif state == WARN_2:
            phase = (frame * 3) & 0xFF
            v = phase if phase < 128 else 255 - phase
            dim = max(10, (v * brightness) >> 8)
            c = scale((255, 100, 0), dim)
            for i in range(N_LEDS):
                leds[i] = c
            return leds

        elif state == WINDDOWN:
            fade = max(0, 255 - (frame % 1000) * 255 // 1000)
            c = scale((40, 40, 80), (fade * brightness) >> 8)
            for i in range(N_LEDS):
                leds[i] = c
            return leds

        elif state in (SLEEPING, COOLDOWN, LOCKDOWN):
            for i in range(N_LEDS):
                leds[i] = (0, 0, 0)
            return leds

        return leds
