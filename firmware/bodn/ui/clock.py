# bodn/ui/clock.py — simple clock screen (time + date)

import time
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered

NAV = config.ENC_NAV


class ClockScreen(Screen):
    """Shows current time (HH:MM) and ISO date (YYYY-MM-DD)."""

    def __init__(self):
        self._manager = None

    def enter(self, manager):
        self._manager = manager

    def update(self, inp, frame):
        if inp.enc_btn_pressed[NAV] and self._manager:
            self._manager.pop()

    def render(self, tft, theme, frame):
        tft.fill(theme.BLACK)
        t = time.localtime()
        clock = "{:02d}:{:02d}".format(t[3], t[4])
        date = "{:04d}-{:02d}-{:02d}".format(t[0], t[1], t[2])

        draw_centered(tft, clock, theme.CENTER_Y - 20, theme.CYAN, theme.width, scale=2)
        draw_centered(tft, date, theme.CENTER_Y + 10, theme.WHITE, theme.width)
