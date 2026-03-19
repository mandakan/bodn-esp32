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
        """Draw this screen's contents. Called every frame.

        The screen is responsible for clearing its own regions.
        A full fill(BLACK) is only done on screen transitions (see ScreenManager).
        """
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
        self._dirty = True  # full clear needed on first frame / transitions

    @property
    def active(self):
        """Return the topmost screen, or None."""
        return self._stack[-1] if self._stack else None

    def invalidate(self):
        """Mark the display as needing a full clear on the next tick."""
        self._dirty = True

    def push(self, screen):
        """Push a screen onto the stack."""
        self._stack.append(screen)
        self._dirty = True
        screen.enter(self)

    def pop(self):
        """Pop the topmost screen. Returns it, or None if stack is empty."""
        if not self._stack:
            return None
        screen = self._stack.pop()
        screen.exit()
        self._dirty = True
        return screen

    def replace(self, screen):
        """Replace the topmost screen (lateral navigation)."""
        if self._stack:
            self._stack[-1].exit()
            self._stack[-1] = screen
        else:
            self._stack.append(screen)
        self._dirty = True
        screen.enter(self)

    def set_overlay(self, overlay):
        """Set a single overlay drawn after the main screen."""
        self._overlay = overlay

    def tick(self):
        """One frame: scan → update → clear-if-dirty → render → show."""
        self._frame += 1
        self.inp.scan()

        active = self.active
        if active:
            active.update(self.inp, self._frame)

        if self._overlay:
            self._overlay.update(self.inp, self._frame)

        # Full clear only on screen transitions; screens handle their own regions
        if self._dirty:
            self.tft.fill(self.theme.BLACK)
            self._dirty = False

        takes_over = self._overlay and getattr(self._overlay, "takes_over", False)
        if active and not takes_over:
            active.render(self.tft, self.theme, self._frame)

        if self._overlay:
            self._overlay.render(self.tft, self.theme, self._frame)

        self.tft.show()
