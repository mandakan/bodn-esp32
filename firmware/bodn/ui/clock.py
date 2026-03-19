# bodn/ui/clock.py — simple clock screen (time + date)

import time
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered
from bodn.ui.pause import PauseMenu

NAV = config.ENC_NAV


class ClockScreen(Screen):
    """Shows current time (HH:MM) and ISO date.

    Only redraws when the second changes (~1/sec instead of ~33/sec).
    Nav encoder button opens pause menu.
    """

    def __init__(self):
        self._manager = None
        self._pause = PauseMenu()
        self._last_sec = -1
        self._dirty = True

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._last_sec = -1
        self._dirty = True

    def needs_redraw(self):
        if self._pause.is_open:
            return self._pause.needs_render
        t = time.localtime()
        if t[5] != self._last_sec:
            self._last_sec = t[5]
            self._dirty = True
        return self._dirty

    def update(self, inp, frame):
        if self._pause.is_open:
            result = self._pause.update(inp, frame)
            if result == "quit" and self._manager:
                self._manager.pop()
            elif result == "resume":
                self._dirty = True
            return

        if inp.enc_btn_pressed[NAV]:
            self._pause.open()
            self._dirty = True

    def render(self, tft, theme, frame):
        if self._pause.is_open:
            if self._dirty:
                self._dirty = False
                tft.fill(theme.BLACK)
                self._render_clock(tft, theme)
            self._pause.render(tft, theme, frame)
            return

        self._dirty = False
        tft.fill(theme.BLACK)
        self._render_clock(tft, theme)

    def _render_clock(self, tft, theme):
        t = time.localtime()
        clock = "{:02d}:{:02d}".format(t[3], t[4])
        date = "{:04d}-{:02d}-{:02d}".format(t[0], t[1], t[2])
        draw_centered(tft, clock, theme.CENTER_Y - 20, theme.CYAN, theme.width, scale=2)
        draw_centered(tft, date, theme.CENTER_Y + 10, theme.WHITE, theme.width)
