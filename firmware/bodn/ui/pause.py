# bodn/ui/pause.py — in-game pause menu with hold-to-open

from micropython import const
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered, draw_hold_bar
from bodn.hold_detector import HoldDetector
from bodn.i18n import t, set_language, get_language, available

NAV = const(0)  # config.ENC_NAV

# Menu items
_RESUME = const(0)
_QUIT = const(1)
_LANG = const(2)
_N_ITEMS = const(3)

# Hold bar: redraw every N% to avoid full-screen redraws.
# The bar draws directly over the existing framebuffer (4px at y=0)
# and pushes show() itself — no game re-render needed.
_HOLD_BAR_STEPS = const(4)  # ~4 visual updates over the hold duration
_HOLD_BAR_H = const(4)


class PauseMenu(Screen):
    """In-game pause menu with hold-to-open protection.

    The nav encoder button must be held for ~1.5 seconds to open the
    pause menu, preventing accidental exits during play.  A thin
    progress bar at the top of the screen shows hold progress.

    The hold bar is drawn as a direct partial update — it overwrites
    only the top 4 pixels and calls tft.show() itself, avoiding a
    full-screen redraw of the game content underneath.

    Once open, quick clicks navigate and confirm.

    Usage in a game screen's update():

        result = self._pause.update(inp)
        if result == "resume":
            pass  # continue game
        elif result == "quit":
            self._manager.pop()
        if self._pause.is_open or self._pause.is_holding:
            return  # skip game logic

    And in render(), after game content:

        self._pause.render(tft, theme, frame)
    """

    def __init__(self, hold_ms=1500, settings=None):
        self._open = False
        self._index = _RESUME
        self._dirty = False
        self._manager = None
        self._settings = settings
        self._hold = HoldDetector(threshold_ms=hold_ms)
        self._last_hold_step = -1
        self._bar_visible = False  # True when bar pixels are on screen

    @property
    def is_open(self):
        return self._open

    @property
    def is_holding(self):
        """True while the user is holding the nav button (before menu opens)."""
        return self._hold.holding and not self._open

    @property
    def hold_progress(self):
        """0.0 to 1.0 — how far through the hold-to-open threshold."""
        return self._hold.progress

    def open(self):
        self._open = True
        self._index = _RESUME
        self._dirty = True

    def close(self):
        self._open = False
        self._hold.reset()
        self._dirty = True

    def set_manager(self, manager):
        self._manager = manager

    def update(self, inp, frame=None):
        """Process input every frame. Returns 'resume', 'quit', or None.

        Handles both the hold-to-open detection AND menu navigation.
        Game screens should call this unconditionally every frame.
        """
        if self._open:
            return self._update_menu(inp)
        return self._update_hold(inp)

    def _update_hold(self, inp):
        """Track nav encoder hold for opening the menu.

        Draws the hold bar as a direct partial update — no _dirty flag,
        no full-screen redraw. Only the top 4px strip is touched.
        """
        was_holding = self._hold.holding
        self._hold.update(inp.enc_btn_held[NAV], inp._time_ms())

        if self._hold.triggered:
            # Clear bar before opening menu (menu will redraw everything)
            self._last_hold_step = -1
            self._bar_visible = False
            self.open()
            self._hold.reset()
            return None

        if self._hold.holding and self._manager:
            step = int(self._hold.progress * _HOLD_BAR_STEPS)
            if step != self._last_hold_step:
                self._last_hold_step = step
                # Draw bar directly into framebuffer — no game re-render
                tft = self._manager.tft
                theme = self._manager.theme
                draw_hold_bar(tft, theme, self._hold.progress, theme.width)
                self._manager.request_show(0, 0, theme.width, _HOLD_BAR_H)
                self._bar_visible = True
        elif was_holding and self._manager:
            # Just released — clear the bar strip
            self._last_hold_step = -1
            if self._bar_visible:
                tft = self._manager.tft
                theme = self._manager.theme
                tft.fill_rect(0, 0, theme.width, _HOLD_BAR_H, theme.BLACK)
                self._manager.request_show(0, 0, theme.width, _HOLD_BAR_H)
                self._bar_visible = False

        return None

    def _update_menu(self, inp):
        """Navigate the open pause menu."""
        # Nav encoder rotation scrolls
        delta = inp.enc_delta[NAV]
        if delta != 0:
            step = 1 if delta > 0 else -1
            self._index = (self._index + step) % _N_ITEMS
            if self._manager:
                mid = self._manager.inp._encoders[NAV]._max // 2
                self._manager.inp._encoders[NAV].value = mid
                self._manager.inp._prev_enc_pos[NAV] = mid
            self._dirty = True

        # Nav encoder button or any play button = confirm
        if inp.enc_btn_pressed[NAV] or inp.any_btn_pressed():
            if self._index == _LANG:
                self._cycle_language()
                self._dirty = True
                return None
            self._open = False
            self._hold.reset()
            self._dirty = True
            if self._index == _RESUME:
                return "resume"
            else:
                return "quit"

        return None

    def _cycle_language(self):
        """Cycle to the next available language and persist."""
        langs = available()
        cur = get_language()
        idx = 0
        for i in range(len(langs)):
            if langs[i] == cur:
                idx = i
                break
        new_lang = langs[(idx + 1) % len(langs)]
        set_language(new_lang)
        if self._settings is not None:
            self._settings["language"] = new_lang
            try:
                from bodn.storage import save_settings

                save_settings(self._settings)
            except Exception:
                pass

    @property
    def needs_render(self):
        return self._dirty

    def render(self, tft, theme, frame):
        """Draw pause menu overlay. Called from game screen's render().

        The hold bar is NOT drawn here — it's handled as a direct
        partial update in _update_hold() to avoid full-screen redraws.
        """
        self._dirty = False

        if not self._open:
            return

        w = theme.width
        h = theme.height

        # Semi-transparent overlay effect: dark rectangle
        tft.fill_rect(w // 6, h // 4, w * 2 // 3, h // 2, theme.BLACK)
        tft.rect(w // 6, h // 4, w * 2 // 3, h // 2, theme.WHITE)

        # Title
        draw_centered(tft, t("pause_title"), h // 4 + 12, theme.WHITE, w, scale=2)

        # Menu items
        items = [
            t("pause_resume"),
            t("pause_quit"),
            t("pause_lang", get_language().upper()),
        ]
        for i, label in enumerate(items):
            y = h // 4 + 48 + i * 24
            selected = i == self._index
            if selected:
                tft.fill_rect(w // 6 + 8, y - 2, w * 2 // 3 - 16, 20, theme.MUTED)
            color = theme.CYAN if selected else theme.WHITE
            draw_centered(tft, label, y + 2, color, w)
