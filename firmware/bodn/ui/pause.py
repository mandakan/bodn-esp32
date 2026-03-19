# bodn/ui/pause.py — in-game pause menu overlay

from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered

NAV = config.ENC_NAV

# Menu items
_RESUME = 0
_QUIT = 1
_ITEMS = ["Resume", "Back to menu"]


class PauseMenu(Screen):
    """In-game pause menu triggered by nav encoder button.

    Shows two options: Resume (continue playing) or Back to menu.
    Nav encoder rotates selection, nav encoder button confirms.
    Any play button also confirms.

    Usage in a game screen's update():
        if self._pause.is_open:
            result = self._pause.update(inp, frame)
            if result == "resume":
                pass  # continue
            elif result == "quit":
                self._manager.pop()
            return  # skip game logic while paused
        if inp.enc_btn_pressed[NAV]:
            self._pause.open()
            return
    """

    def __init__(self):
        self._open = False
        self._index = _RESUME
        self._dirty = False
        self._manager = None

    @property
    def is_open(self):
        return self._open

    def open(self):
        self._open = True
        self._index = _RESUME
        self._dirty = True

    def close(self):
        self._open = False
        self._dirty = True

    def set_manager(self, manager):
        self._manager = manager

    def update(self, inp, frame):
        """Process input while paused. Returns 'resume', 'quit', or None."""
        if not self._open:
            return None

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
        """Draw the pause menu. Call from the game screen's render()."""
        if not self._open:
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
