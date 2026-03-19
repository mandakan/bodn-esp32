# bodn/ui/secondary.py — lightweight renderer for the secondary display


class SecondaryDisplay:
    """Manages the secondary (ambient) display independently from the main UI.

    Runs a single Screen at a time — no stack, no overlay.
    Call tick() from the main loop alongside the primary ScreenManager.

    Only redraws when the screen signals a change via needs_redraw(),
    or when the screen is first set. This avoids unnecessary SPI traffic
    for slow-changing content like a clock.
    """

    def __init__(self, tft, theme):
        self.tft = tft
        self.theme = theme
        self._screen = None
        self._frame = 0
        self._dirty = True

    def set_screen(self, screen):
        """Set the active screen. Calls enter/exit as needed."""
        if self._screen:
            self._screen.exit()
        self._screen = screen
        self._dirty = True
        if self._screen:
            self._screen.enter(self)

    def invalidate(self):
        """Force a redraw on the next tick."""
        self._dirty = True

    def tick(self, inp=None):
        """One frame: update → redraw only if needed."""
        self._frame += 1
        if not self._screen:
            return
        if inp:
            self._screen.update(inp, self._frame)

        # Check if the screen wants a redraw
        needs = getattr(self._screen, "needs_redraw", None)
        if needs and not needs():
            if not self._dirty:
                return
        self._dirty = False

        self.tft.fill(self.theme.BLACK)
        self._screen.render(self.tft, self.theme, self._frame)
        self.tft.show()
