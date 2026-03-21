# bodn/ui/ambient.py — screens for the secondary (ambient) display

import time
from bodn.session import PLAYING, WARN_5, WARN_2, IDLE
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered, draw_progress_bar, draw_battery_icon
from bodn.ui.secondary import STATUS_Y, STATUS_H
import bodn.battery as battery

_AMBIENT_TEXT_Y = 38  # 2px above clock at y=40 (scale=3, h=24)
_AMBIENT_TEXT_H = 52  # covers clock (40..64) and date (80..88) with margin


class AmbientClock(Screen):
    """Large clock display for the 128×128 content zone.

    Shows time and date in the centre of the content area.
    Redraws when the minute changes.  Only the text region is cleared
    (not the full zone) so SecondaryDisplay.show_rect() covers as few
    pixels as possible.
    """

    def __init__(self):
        self._last_min = -1

    def enter(self, display):
        self._last_min = -1

    def needs_redraw(self):
        t = time.localtime()
        cur_min = t[4]
        if cur_min != self._last_min:
            self._last_min = cur_min
            return True
        return False

    def render(self, tft, theme, frame):
        w = theme.width
        tft.fill_rect(0, _AMBIENT_TEXT_Y, w, _AMBIENT_TEXT_H, theme.BLACK)
        t = time.localtime()
        clock = "{:02d}:{:02d}".format(t[3], t[4])
        date = "{:04d}-{:02d}-{:02d}".format(t[0], t[1], t[2])
        draw_centered(tft, clock, 40, theme.CYAN, w, scale=3)
        draw_centered(tft, date, 80, theme.WHITE, w)


class StatusStrip(Screen):
    """Compact clock + session timer for the 128×32 status strip.

    Renders at y=128..159.  Redraws on minute change or session state
    transition — at most once per second in practice.
    """

    def __init__(self, session_mgr):
        self._session_mgr = session_mgr
        self._last_min = -1
        self._prev_state = None
        self._prev_remaining_min = -1
        self._prev_bat_pct = -1
        self._prev_charging = None

    def enter(self, display):
        self._last_min = -1
        self._prev_state = None
        self._prev_remaining_min = -1
        self._prev_bat_pct = -1
        self._prev_charging = None

    def needs_redraw(self):
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

        if state in (PLAYING, WARN_5, WARN_2):
            remaining_min = self._session_mgr.time_remaining_s // 60
            if remaining_min != self._prev_remaining_min:
                self._prev_remaining_min = remaining_min
                changed = True

        # Battery (cached — at most one ADC read per call, refresh every 30 s)
        bat_pct, charging = battery.read()
        if bat_pct != self._prev_bat_pct or charging != self._prev_charging:
            self._prev_bat_pct = bat_pct
            self._prev_charging = charging
            changed = True

        return changed

    def render(self, tft, theme, frame):
        w = theme.width
        y0 = STATUS_Y
        tft.fill_rect(0, y0, w, STATUS_H, theme.BLACK)
        t = time.localtime()

        bat_pct, charging = battery.read()

        # Row 1: clock left, session info right
        clock = "{:02d}:{:02d}".format(t[3], t[4])
        tft.text(clock, 2, y0 + 2, theme.CYAN)

        state = self._session_mgr.state
        if state in (PLAYING, WARN_5, WARN_2):
            remaining = self._session_mgr.time_remaining_s
            limit = self._session_mgr._session_limit_s()

            if state == WARN_2:
                bar_color = theme.RED
            elif state == WARN_5:
                bar_color = theme.AMBER
            else:
                bar_color = theme.GREEN

            # Minutes remaining — right-aligned on row 1
            mins = remaining // 60
            label = "{}m".format(mins) if mins > 0 else "<1m"
            x_right = w - len(label) * 8 - 2
            tft.text(label, x_right, y0 + 2, bar_color)

            # Progress bar — row 2
            draw_progress_bar(
                tft,
                2,
                y0 + 14,
                w - 4,
                8,
                remaining,
                limit,
                bar_color,
                theme.BLACK,
                border=theme.WHITE,
            )

        elif state == IDLE:
            remaining = self._session_mgr.sessions_remaining
            color = theme.GREEN if remaining > 0 else theme.RED
            label = "{} plays".format(remaining)
            x_right = w - len(label) * 8 - 2
            tft.text(label, x_right, y0 + 2, color)

        # Battery icon — row 2, always visible
        # Colour: green ≥50 %, amber ≥20 %, red <20 %; bolt overlay when charging
        if bat_pct >= 50:
            bat_color = theme.GREEN
        elif bat_pct >= 20:
            bat_color = theme.AMBER
        else:
            bat_color = theme.RED
        icon_w, icon_h = 20, 10
        icon_x = w - icon_w - 2
        icon_y = y0 + 18
        draw_battery_icon(
            tft,
            icon_x,
            icon_y,
            icon_w,
            icon_h,
            bat_pct,
            bat_color,
            theme.BLACK,
            theme.WHITE,
        )
        if charging:
            # Small "+" mark to indicate charging
            tft.text("+", icon_x + icon_w // 2 - 4, icon_y + 1, theme.YELLOW)
