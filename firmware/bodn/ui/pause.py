# bodn/ui/pause.py — in-game pause menu with hold-to-open

from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered, draw_hold_bar
from bodn.hold_detector import HoldDetector

NAV = config.ENC_NAV

# Menu items
_RESUME = 0
_QUIT = 1
_ITEMS = ["Resume", "Back to menu"]


class PauseMenu(Screen):
    """In-game pause menu with hold-to-open protection.

    The nav encoder button must be held for ~1.5 seconds to open the
    pause menu, preventing accidental exits during play.  A thin
    progress bar at the top of the screen shows hold progress.

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

    def __init__(self, hold_ms=1500):
        self._open = False
        self._index = _RESUME
        self._dirty = False
        self._manager = None
        self._hold = HoldDetector(threshold_ms=hold_ms)

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
        """Track nav encoder hold for opening the menu."""
        was_holding = self._hold.holding
        self._hold.update(inp.enc_btn_held[NAV], inp._time_ms())

        if self._hold.triggered:
            self.open()
            self._hold.reset()
            return None

        # Redraw needed when hold bar appears or disappears
        if self._hold.holding or was_holding:
            self._dirty = True

        return None

    def _update_menu(self, inp):
        """Navigate the open pause menu."""
        # Nav encoder rotation scrolls
        delta = inp.enc_delta[NAV]
        if delta != 0:
            self._index = _QUIT if self._index == _RESUME else _RESUME
            if self._manager:
                mid = self._manager.inp._encoders[NAV]._max // 2
                self._manager.inp._encoders[NAV].value = mid
                self._manager.inp._prev_enc_pos[NAV] = mid
            self._dirty = True

        # Nav encoder button or any play button = confirm
        if inp.enc_btn_pressed[NAV] or inp.any_btn_pressed():
            self._open = False
            self._hold.reset()
            self._dirty = True
            if self._index == _RESUME:
                return "resume"
            else:
                return "quit"

        return None

    @property
    def needs_render(self):
        return self._dirty

    def render(self, tft, theme, frame):
        """Draw hold bar or pause menu. Call from game screen's render().

        When not open: draws the hold progress bar (if holding).
        When open: draws the full pause menu overlay.
        """
        if not self._open:
            # Hold progress bar at top of screen
            if self._hold.holding:
                draw_hold_bar(tft, theme, self._hold.progress, theme.width)
            self._dirty = False
            return

        self._dirty = False

        w = theme.width
        h = theme.height

        # Semi-transparent overlay effect: dark rectangle
        tft.fill_rect(w // 6, h // 4, w * 2 // 3, h // 2, theme.BLACK)
        tft.rect(w // 6, h // 4, w * 2 // 3, h // 2, theme.WHITE)

        # Title
        draw_centered(tft, "PAUSED", h // 4 + 12, theme.WHITE, w, scale=2)

        # Menu items
        for i, label in enumerate(_ITEMS):
            y = h // 4 + 48 + i * 24
            selected = i == self._index
            if selected:
                tft.fill_rect(w // 6 + 8, y - 2, w * 2 // 3 - 16, 20, theme.MUTED)
            color = theme.CYAN if selected else theme.WHITE
            draw_centered(tft, label, y + 2, color, w)
