# bodn/ui/ambient.py — screens for the secondary (ambient) display

import time
from bodn.session import PLAYING, WARN_5, WARN_2, IDLE
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered, draw_progress_bar


class AmbientClock(Screen):
    """Shows time, date, and session progress on the secondary display.

    Redraws when the minute changes or the session state transitions.
    The session timer is a progress bar that depletes over the session,
    colored green → amber → red as time runs out.
    """

    def __init__(self, session_mgr):
        self._session_mgr = session_mgr
        self._last_min = -1
        self._prev_state = None
        self._prev_remaining_min = -1

    def enter(self, display):
        self._last_min = -1
        self._prev_state = None
        self._prev_remaining_min = -1

    def update(self, inp, frame):
        pass

    def needs_redraw(self):
        """Redraw on minute change or session state/minute change."""
        changed = False

        t = time.localtime()
        cur_min = t[4]
        if cur_min != self._last_min:
            self._last_min = cur_min
            changed = True

        state = self._session_mgr.state
        if state != self._prev_state:
            self._prev_state = state
            changed = True

        # Update progress bar per-minute (not per-second)
        if state in (PLAYING, WARN_5, WARN_2):
            remaining_min = self._session_mgr.time_remaining_s // 60
            if remaining_min != self._prev_remaining_min:
                self._prev_remaining_min = remaining_min
                changed = True

        return changed

    def render(self, tft, theme, frame):
        t = time.localtime()
        w = theme.width
        h = theme.height

        clock = "{:02d}:{:02d}".format(t[3], t[4])
        date = "{:04d}-{:02d}-{:02d}".format(t[0], t[1], t[2])

        draw_centered(tft, clock, h // 4 - 8, theme.CYAN, w, scale=2)
        draw_centered(tft, date, h // 4 + 14, theme.WHITE, w)

        # Session progress bar
        state = self._session_mgr.state
        if state in (PLAYING, WARN_5, WARN_2):
            remaining = self._session_mgr.time_remaining_s
            limit = self._session_mgr._session_limit_s()

            # Color based on state
            if state == WARN_2:
                bar_color = theme.RED
            elif state == WARN_5:
                bar_color = theme.AMBER
            else:
                bar_color = theme.GREEN

            # Progress bar
            bar_w = w - 16
            bar_x = 8
            bar_y = h * 3 // 5
            bar_h = 10
            draw_progress_bar(
                tft, bar_x, bar_y, bar_w, bar_h,
                remaining, limit, bar_color, theme.BLACK, border=theme.WHITE,
            )

            # Minutes remaining label
            mins = remaining // 60
            label = "{} min".format(mins) if mins > 0 else "<1 min"
            draw_centered(tft, label, bar_y + bar_h + 6, bar_color, w)

        elif state == IDLE:
            remaining = self._session_mgr.sessions_remaining
            color = theme.GREEN if remaining > 0 else theme.RED
            draw_centered(tft, "{} plays".format(remaining), h * 3 // 5, color, w)
