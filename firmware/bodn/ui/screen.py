# bodn/ui/screen.py — Screen base class and ScreenManager


class Screen:
    """Base class for all UI screens."""

    def enter(self, manager):
        """Called when this screen becomes active."""
        pass

    def exit(self):
        """Called when this screen is removed from the stack."""
        pass

    def update(self, inp, frame):
        """Process input and update state. Called every frame."""
        pass

    def render(self, tft, theme, frame):
        """Draw this screen's contents. Called every frame."""
        pass


class ScreenManager:
    """Stack-based screen manager with optional overlay."""

    def __init__(self, tft, theme, inp):
        self.tft = tft
        self.theme = theme
        self.inp = inp
        self._stack = []
        self._overlay = None
        self._frame = 0

    @property
    def active(self):
        """Return the topmost screen, or None."""
        return self._stack[-1] if self._stack else None

    def push(self, screen):
        """Push a screen onto the stack."""
        self._stack.append(screen)
        screen.enter(self)

    def pop(self):
        """Pop the topmost screen. Returns it, or None if stack is empty."""
        if not self._stack:
            return None
        screen = self._stack.pop()
        screen.exit()
        return screen

    def replace(self, screen):
        """Replace the topmost screen (lateral navigation)."""
        if self._stack:
            self._stack[-1].exit()
            self._stack[-1] = screen
        else:
            self._stack.append(screen)
        screen.enter(self)

    def set_overlay(self, overlay):
        """Set a single overlay drawn after the main screen."""
        self._overlay = overlay

    def tick(self):
        """One frame: scan → update → clear → render → show."""
        self._frame += 1
        self.inp.scan()

        active = self.active
        if active:
            active.update(self.inp, self._frame)

        if self._overlay:
            self._overlay.update(self.inp, self._frame)

        self.tft.fill(self.theme.BLACK)

        takes_over = self._overlay and getattr(self._overlay, "takes_over", False)
        if active and not takes_over:
            active.render(self.tft, self.theme, self._frame)

        if self._overlay:
            self._overlay.render(self.tft, self.theme, self._frame)

        self.tft.show()
