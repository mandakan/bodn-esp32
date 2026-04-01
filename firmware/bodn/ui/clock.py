# bodn/ui/clock.py — simple clock screen (time + date)

import time
from micropython import const
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered
from bodn.ui.pause import PauseMenu

NAV = const(0)  # config.ENC_NAV


class ClockScreen(Screen):
    """Shows current time (HH:MM) and ISO date.

    Time ticks (1/sec) are partial updates — only the text region is pushed
    via request_show(x, y, w, h).  Full redraws happen only on transitions
    (enter, pause open/close), keeping the typical SPI cost at ~7 KB/sec
    instead of ~150 KB/sec.
    Nav encoder button opens pause menu.
    """

    # Region containing both text lines (clock scale=2→16 px tall, date 8 px).
    # Relative to theme.CENTER_Y; total height = (CENTER_Y+10+8) - (CENTER_Y-20) = 38.
    _TEXT_REL_Y = -20  # offset from CENTER_Y
    _TEXT_H = 38

    def __init__(self, settings=None):
        self._manager = None
        self._pause = PauseMenu(settings=settings)
        self._last_sec = -1
        self._dirty = True

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._last_sec = -1
        self._dirty = True

    def needs_redraw(self):
        # Full render only for transitions and pause menu state changes.
        # Normal time ticks are handled via request_show() in update().
        return self._dirty or self._pause.needs_render

    def update(self, inp, frame):
        # Pause menu handles hold-to-open and menu navigation
        result = self._pause.update(inp, frame)
        if result == "quit" and self._manager:
            self._manager.pop()
            return
        elif result == "resume":
            self._dirty = True
        if self._pause.is_open or self._pause.is_holding:
            return

        # Time tick — partial push, no full render cycle
        t = time.localtime()
        if t[5] != self._last_sec and self._manager:
            self._last_sec = t[5]
            tft = self._manager.tft
            theme = self._manager.theme
            text_y = theme.CENTER_Y + self._TEXT_REL_Y
            tft.fill_rect(0, text_y, theme.width, self._TEXT_H, theme.BLACK)
            self._render_clock(tft, theme)
            self._manager.request_show(0, text_y, theme.width, self._TEXT_H)

    def render(self, tft, theme, frame):
        """Full redraw — only called on transitions and pause menu changes."""
        self._dirty = False
        tft.fill(theme.BLACK)
        self._render_clock(tft, theme)
        if self._pause.is_open:
            self._pause.render(tft, theme, frame)

    def _render_clock(self, tft, theme):
        t = time.localtime()
        clock = "{:02d}:{:02d}".format(t[3], t[4])
        date = "{:04d}-{:02d}-{:02d}".format(t[0], t[1], t[2])
        draw_centered(tft, clock, theme.CENTER_Y - 20, theme.CYAN, theme.width, scale=2)
        draw_centered(tft, date, theme.CENTER_Y + 10, theme.WHITE, theme.width)
