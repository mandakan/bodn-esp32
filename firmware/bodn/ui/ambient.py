# bodn/ui/ambient.py — screens for the secondary (ambient) display

import time
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered


class AmbientClock(Screen):
    """Shows time and date on the secondary display.

    Only signals a redraw when the minute changes, avoiding
    unnecessary SPI traffic (~once per minute instead of ~33/sec).
    """

    def __init__(self):
        self._last_min = -1

    def enter(self, display):
        self._last_min = -1

    def update(self, inp, frame):
        pass

    def needs_redraw(self):
        """Return True when the display content has changed."""
        t = time.localtime()
        cur_min = t[4]
        if cur_min != self._last_min:
            self._last_min = cur_min
            return True
        return False

    def render(self, tft, theme, frame):
        t = time.localtime()

        clock = "{:02d}:{:02d}".format(t[3], t[4])
        date = "{:04d}-{:02d}-{:02d}".format(t[0], t[1], t[2])

        draw_centered(tft, clock, theme.CENTER_Y - 14, theme.CYAN, theme.width, scale=2)
        draw_centered(tft, date, theme.CENTER_Y + 10, theme.WHITE, theme.width)
