# bodn/ui/ambient.py — screens for the secondary (ambient) display

import time
from bodn.session import PLAYING, WARN_5, WARN_2, IDLE
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered, draw_progress_bar, draw_battery_icon
from bodn.ui.secondary import CONTENT_SIZE
import bodn.battery as battery
from bodn import temperature
from bodn.i18n import t as _t

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
        w = CONTENT_SIZE
        tft.fill_rect(0, _AMBIENT_TEXT_Y, w, _AMBIENT_TEXT_H, theme.BLACK)
        t = time.localtime()
        clock = "{:02d}:{:02d}".format(t[3], t[4])
        date = "{:04d}-{:02d}-{:02d}".format(t[0], t[1], t[2])
        draw_centered(tft, clock, 40, theme.CYAN, w, scale=3)
        draw_centered(tft, date, 80, theme.WHITE, w)


class StatusStrip(Screen):
    """Compact clock + session timer + battery for the status strip.

    Adapts layout automatically based on orientation:
    - Portrait (128×32): horizontal — clock left, session right, battery below
    - Landscape (32×128): vertical — clock top, session middle, battery bottom
    """

    def __init__(self, session_mgr):
        self._session_mgr = session_mgr
        self._last_min = -1
        self._prev_state = None
        self._prev_remaining_min = -1
        self._prev_bat_pct = -1
        self._prev_charging = None
        self._prev_temp_status = "ok"
        self._landscape = False

    def enter(self, display):
        self._last_min = -1
        self._prev_state = None
        self._prev_remaining_min = -1
        self._prev_bat_pct = -1
        self._prev_charging = None
        self._prev_temp_status = "ok"
        self._landscape = getattr(display, "landscape", False)

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
        # bat_pct is None when no battery detected — still track for changes
        if bat_pct != self._prev_bat_pct or charging != self._prev_charging:
            self._prev_bat_pct = bat_pct
            self._prev_charging = charging
            changed = True

        # Temperature status
        temp_st = temperature.status()
        if temp_st != self._prev_temp_status:
            self._prev_temp_status = temp_st
            changed = True

        return changed

    def render(self, tft, theme, frame):
        if self._landscape:
            self._render_vertical(tft, theme)
        else:
            self._render_horizontal(tft, theme)

    def _render_horizontal(self, tft, theme):
        """Portrait layout: 128×32 horizontal strip."""
        w = tft.width
        h = tft.height
        tft.fill_rect(0, 0, w, h, theme.BLACK)
        t = time.localtime()

        bat_pct, charging = battery.read()

        # Row 1: clock left, session info right
        clock = "{:02d}:{:02d}".format(t[3], t[4])
        tft.text(clock, 2, 2, theme.CYAN)

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
            tft.text(label, x_right, 2, bar_color)

            # Progress bar — row 2
            draw_progress_bar(
                tft,
                2,
                14,
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
            label = _t("plays", remaining)
            x_right = w - len(label) * 8 - 2
            tft.text(label, x_right, 2, color)

        # Row 2: safety alerts > battery icon (priority order)
        temp_st = temperature.status()
        bat_st = battery.status()
        if temp_st == "critical":
            tft.fill_rect(0, 14, w, 18, theme.RED)
            label = _t("temp_critical")
            lx = (w - len(label) * 8) // 2
            tft.text(label, max(0, lx), 18, theme.WHITE)
        elif bat_st == "critical":
            tft.fill_rect(0, 14, w, 18, theme.RED)
            label = _t("bat_critical")
            lx = (w - len(label) * 8) // 2
            tft.text(label, max(0, lx), 18, theme.WHITE)
        elif temp_st == "warn":
            t_c = temperature.max_temp()
            label = _t("temp_warn")
            if t_c is not None:
                label = "{}C {}".format(int(t_c), label)
            tft.text(label, 2, 22, theme.AMBER)
        elif bat_st == "warn":
            label = _t("bat_low")
            tft.text(label, 2, 22, theme.AMBER)
        else:
            # Battery icon — row 2 (hidden when no battery detected)
            if bat_pct is not None:
                if bat_pct >= 50:
                    bat_color = theme.GREEN
                elif bat_pct >= 20:
                    bat_color = theme.AMBER
                else:
                    bat_color = theme.RED
                icon_w, icon_h = 20, 10
                icon_x = w - icon_w - 2
                icon_y = 18
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
                    tft.text("+", icon_x + icon_w // 2 - 4, icon_y + 1, theme.YELLOW)

    def _render_vertical(self, tft, theme):
        """Landscape layout: 32×128 vertical strip."""
        w = tft.width  # 32
        h = tft.height  # 128
        tft.fill_rect(0, 0, w, h, theme.BLACK)
        t = time.localtime()

        bat_pct, charging = battery.read()

        # Top: clock (HH:MM centered, scale=1 → 5 chars × 8px = 40px, won't fit)
        # Use compact HH\nMM or just HH:MM at x=0
        hh = "{:02d}".format(t[3])
        mm = "{:02d}".format(t[4])
        # Center "HH" and "MM" vertically stacked
        hh_x = (w - 16) // 2  # 2 chars × 8px
        tft.text(hh, hh_x, 4, theme.CYAN)
        tft.text(mm, hh_x, 16, theme.CYAN)
        # Colon-like dots between
        dot_x = w // 2 - 1
        tft.fill_rect(dot_x, 13, 2, 2, theme.CYAN)

        # Middle: session info
        state = self._session_mgr.state
        y_session = 34

        if state in (PLAYING, WARN_5, WARN_2):
            remaining = self._session_mgr.time_remaining_s
            limit = self._session_mgr._session_limit_s()

            if state == WARN_2:
                bar_color = theme.RED
            elif state == WARN_5:
                bar_color = theme.AMBER
            else:
                bar_color = theme.GREEN

            mins = remaining // 60
            label = "{}m".format(mins) if mins > 0 else "<1m"
            lx = (w - len(label) * 8) // 2
            tft.text(label, lx, y_session, bar_color)

            # Vertical progress bar
            bar_x = (w - 8) // 2
            bar_h = 40
            bar_y = y_session + 14
            frac = remaining / limit if limit > 0 else 0
            filled = int(frac * bar_h)
            tft.rect(bar_x, bar_y, 8, bar_h, theme.WHITE)
            if filled > 0:
                tft.fill_rect(
                    bar_x + 1, bar_y + bar_h - filled - 1, 6, filled, bar_color
                )

        elif state == IDLE:
            rem = self._session_mgr.sessions_remaining
            color = theme.GREEN if rem > 0 else theme.RED
            label = _t("plays", rem)
            # Truncate if wider than strip
            max_chars = w // 8
            if len(label) > max_chars:
                label = label[:max_chars]
            lx = (w - len(label) * 8) // 2
            tft.text(label, max(0, lx), y_session, color)

        # Bottom: safety alerts > battery icon (priority order)
        temp_st = temperature.status()
        bat_st = battery.status()
        if temp_st == "critical":
            tft.fill_rect(0, h - 16, w, 16, theme.RED)
            tft.text("HOT", (w - 24) // 2, h - 14, theme.WHITE)
        elif bat_st == "critical":
            tft.fill_rect(0, h - 16, w, 16, theme.RED)
            tft.text("LOW", (w - 24) // 2, h - 14, theme.WHITE)
        elif temp_st == "warn":
            t_c = temperature.max_temp()
            label = "{}C".format(int(t_c)) if t_c is not None else "?"
            lx = (w - len(label) * 8) // 2
            tft.text(label, max(0, lx), h - 12, theme.AMBER)
        elif bat_st == "warn":
            tft.text("BAT", (w - 24) // 2, h - 12, theme.AMBER)
        elif bat_pct is not None:
            if bat_pct >= 50:
                bat_color = theme.GREEN
            elif bat_pct >= 20:
                bat_color = theme.AMBER
            else:
                bat_color = theme.RED
            icon_w, icon_h = 20, 10
            icon_x = (w - icon_w) // 2
            icon_y = h - icon_h - 4
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
                tft.text("+", icon_x + icon_w // 2 - 4, icon_y + 1, theme.YELLOW)
