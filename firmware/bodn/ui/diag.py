# bodn/ui/diag.py — diagnostic info screen (reachable from settings menu)

from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered
from bodn.i18n import t


class DiagScreen(Screen):
    """Full-screen diagnostic info. Any button or encoder press dismisses."""

    def __init__(self):
        self._manager = None
        self._dirty = True
        self._info = None

    def enter(self, manager):
        self._manager = manager
        self._dirty = True
        # Gather info on entry so RAM measurement reflects runtime state
        from bodn.diag import gather

        self._info = gather()

    def needs_redraw(self):
        return self._dirty

    def update(self, inp, frame):
        # Dismiss on any button or encoder button press
        if inp.any_btn_pressed():
            self._dismiss()
            return
        for i in range(len(inp.enc_btn_pressed)):
            if inp.enc_btn_pressed[i]:
                self._dismiss()
                return

    def _dismiss(self):
        if self._manager:
            self._manager.pop()

    def render(self, tft, theme, frame):
        self._dirty = False
        tft.fill(theme.BLACK)

        draw_centered(tft, t("diag_title"), 4, theme.AMBER, theme.width)

        line_h = 14
        y = 22
        for label, val in self._info:
            tft.text(label, 4, y, theme.AMBER)
            vx = min(80, (len(label) + 1) * 8 + 4)
            tft.text(str(val), vx, y, theme.WHITE)
            y += line_h

        draw_centered(
            tft, t("diag_dismiss"), theme.height - 16, theme.CYAN, theme.width
        )
