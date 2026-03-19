# bodn/ui/overlay.py — session-aware display overlay

from bodn.session import (
    PLAYING, WARN_5, WARN_2, WINDDOWN, SLEEPING, COOLDOWN, LOCKDOWN, IDLE,
)
from bodn.patterns import scale, N_LEDS
from bodn.ui.screen import Screen


class SessionOverlay(Screen):
    """Draws session state info over the active screen.

    When the session is in a blocking state (sleeping, lockdown, etc.),
    takes_over becomes True and the underlying screen is not rendered.
    """

    _TAKEOVER_STATES = (SLEEPING, COOLDOWN, LOCKDOWN, WINDDOWN)

    def __init__(self, session_mgr):
        self.session_mgr = session_mgr

    @property
    def takes_over(self):
        return self.session_mgr.state in self._TAKEOVER_STATES

    def update(self, inp, frame):
        state = self.session_mgr.state
        # Wake from IDLE on any button press
        if state == IDLE and inp.any_btn_pressed():
            self.session_mgr.try_wake()

    def render(self, tft, theme, frame):
        state = self.session_mgr.state

        if state == PLAYING:
            remaining = self.session_mgr.time_remaining_s
            mins = remaining // 60
            secs = remaining % 60
            tft.text("{:d}:{:02d}".format(mins, secs), 88, 3, theme.GREEN)

        elif state == WARN_5:
            remaining = self.session_mgr.time_remaining_s
            mins = remaining // 60
            secs = remaining % 60
            tft.text("{:d}:{:02d}".format(mins, secs), 88, 3, theme.AMBER)

        elif state == WARN_2:
            remaining = self.session_mgr.time_remaining_s
            mins = remaining // 60
            secs = remaining % 60
            if (frame // 15) % 2 == 0:
                tft.text("{:d}:{:02d}".format(mins, secs), 88, 3, theme.RED)

        elif state == WINDDOWN:
            if (frame // 20) % 2 == 0:
                tft.text("Zzz...", 40, 70, theme.AMBER)

        elif state in (SLEEPING, COOLDOWN):
            tft.text("Zzz", 52, 60, theme.BLUE)
            tft.text("See you", 36, 80, theme.WHITE)
            tft.text("soon!", 44, 96, theme.WHITE)

        elif state == LOCKDOWN:
            tft.text("Goodnight!", 24, 70, theme.MAGENTA)

    def led_override(self, state, frame, leds, brightness):
        """Modify LED output based on session state. Returns new LED list."""
        if state == WARN_5:
            amber = (255, 191, 0)
            if (frame // 30) % 2 == 0:
                return [scale(amber, brightness)] * N_LEDS
            return leds

        elif state == WARN_2:
            phase = (frame * 3) & 0xFF
            v = phase if phase < 128 else 255 - phase
            dim = max(10, (v * brightness) >> 8)
            return [scale((255, 100, 0), dim)] * N_LEDS

        elif state == WINDDOWN:
            fade = max(0, 255 - (frame % 1000) * 255 // 1000)
            return [scale((40, 40, 80), (fade * brightness) >> 8)] * N_LEDS

        elif state in (SLEEPING, COOLDOWN, LOCKDOWN):
            return [(0, 0, 0)] * N_LEDS

        return leds
