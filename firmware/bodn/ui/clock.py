# bodn/ui/clock.py — simple clock screen (time + date)

import time
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered

NAV = config.ENC_NAV


class ClockScreen(Screen):
    """Shows current time (HH:MM:SS) and ISO date.

    Only redraws when the second changes (~1/sec instead of ~33/sec).
    """

    def __init__(self):
        self._manager = None
        self._last_sec = -1
        self._dirty = True

    def enter(self, manager):
        self._manager = manager
        self._last_sec = -1
        self._dirty = True

    def needs_redraw(self):
        t = time.localtime()
        if t[5] != self._last_sec:
            self._last_sec = t[5]
            self._dirty = True
        return self._dirty

    def update(self, inp, frame):
        if inp.enc_btn_pressed[NAV] and self._manager:
            self._manager.pop()

    def render(self, tft, theme, frame):
        self._dirty = False
        tft.fill(theme.BLACK)
        t = time.localtime()
        clock = "{:02d}:{:02d}".format(t[3], t[4])
        date = "{:04d}-{:02d}-{:02d}".format(t[0], t[1], t[2])

        draw_centered(tft, clock, theme.CENTER_Y - 20, theme.CYAN, theme.width, scale=2)
        draw_centered(tft, date, theme.CENTER_Y + 10, theme.WHITE, theme.width)
