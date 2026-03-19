# bodn/ui/secondary.py — lightweight renderer for the secondary display


class SecondaryDisplay:
    """Manages the secondary (ambient) display independently from the main UI.

    Runs a single Screen at a time — no stack, no overlay.
    Call tick() from the main loop alongside the primary ScreenManager.
    """

    def __init__(self, tft, theme):
        self.tft = tft
        self.theme = theme
        self._screen = None
        self._frame = 0

    def set_screen(self, screen):
        """Set the active screen. Calls enter/exit as needed."""
        if self._screen:
            self._screen.exit()
        self._screen = screen
        if self._screen:
            self._screen.enter(self)

    def tick(self, inp=None):
        """One frame: update → clear → render → show."""
        self._frame += 1
        if not self._screen:
            return
        if inp:
            self._screen.update(inp, self._frame)
        self.tft.fill(self.theme.BLACK)
        self._screen.render(self.tft, self.theme, self._frame)
        self.tft.show()
