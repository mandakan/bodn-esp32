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
from bodn.patterns import scale, N_LEDS, _BLACK
from bodn.ui.screen import Screen
from bodn.i18n import t


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
                tft.text(t("overlay_zzz"), 40, 70, theme.AMBER)

        elif state in (SLEEPING, COOLDOWN):
            tft.text(t("overlay_zzz_short"), 52, 60, theme.BLUE)
            tft.text(t("overlay_see_you"), 36, 80, theme.WHITE)
            tft.text(t("overlay_soon"), 44, 96, theme.WHITE)

        elif state == LOCKDOWN:
            tft.text(t("overlay_goodnight"), 24, 70, theme.MAGENTA)

    def static_led_override(self, state, leds, brightness):
        """Override LEDs with static colors based on session state.

        No animation — solid colors only. For game screens that update
        LEDs only on state changes.
        """
        n = N_LEDS
        if state == WARN_5:
            c = scale((255, 191, 0), brightness)
            for i in range(n):
                leds[i] = c
            return leds

        elif state == WARN_2:
            c = scale((255, 100, 0), brightness // 2)
            for i in range(n):
                leds[i] = c
            return leds

        elif state == WINDDOWN:
            c = scale((40, 40, 80), brightness // 4)
            for i in range(n):
                leds[i] = c
            return leds

        elif state in (SLEEPING, COOLDOWN, LOCKDOWN):
            black = _BLACK
            for i in range(n):
                leds[i] = black
            return leds

        return leds

    def led_override(self, state, frame, leds, brightness):
        """Modify LED output based on session state. Writes into leds in-place."""
        n = N_LEDS
        if state == WARN_5:
            if (frame // 30) % 2 == 0:
                c = scale((255, 191, 0), brightness)
                for i in range(n):
                    leds[i] = c
            return leds

        elif state == WARN_2:
            phase = (frame * 3) & 0xFF
            v = phase if phase < 128 else 255 - phase
            dim = max(10, (v * brightness) >> 8)
            c = scale((255, 100, 0), dim)
            for i in range(n):
                leds[i] = c
            return leds

        elif state == WINDDOWN:
            fade = max(0, 255 - (frame % 1000) * 255 // 1000)
            c = scale((40, 40, 80), (fade * brightness) >> 8)
            for i in range(n):
                leds[i] = c
            return leds

        elif state in (SLEEPING, COOLDOWN, LOCKDOWN):
            black = _BLACK
            for i in range(n):
                leds[i] = black
            return leds

        return leds
