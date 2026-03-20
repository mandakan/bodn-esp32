# bodn/ui/screen.py — Screen base class and ScreenManager


class Screen:
    """Base class for all UI screens.

    Screens can set self._dirty = True to request a redraw.
    ScreenManager checks needs_redraw() each tick and skips
    the render + show cycle when nothing changed.
    """

    def enter(self, manager):
        """Called when this screen becomes active."""
        pass

    def exit(self):
        """Called when this screen is removed from the stack."""
        pass

    def update(self, inp, frame):
        """Process input and update state. Called every frame."""
        pass

    def needs_redraw(self):
        """Return True if render() should be called this frame.

        Default returns True (always redraw) for backward compatibility.
        Override in subclasses that track their own dirty state.
        """
        return True

    def render(self, tft, theme, frame):
        """Draw this screen's contents.

        Only called when needs_redraw() returns True.
        The screen is responsible for clearing its own background.
        """
        pass


class ScreenManager:
    """Stack-based screen manager with optional overlay.

    Skips the expensive render + SPI show cycle when no screen
    needs a redraw, keeping the CPU idle between state changes.
    """

    def __init__(self, tft, theme, inp):
        self.tft = tft
        self.theme = theme
        self.inp = inp
        self._stack = []
        self._overlay = None
        self._frame = 0
        self._dirty = True  # full clear needed on first frame / transitions
        # Perf counters (enabled via debug_perf setting)
        self.debug_perf = False
        self._perf_total = 0
        self._perf_drawn = 0
        self._perf_time_ms = None  # set to time_ms function when enabled

    @property
    def active(self):
        """Return the topmost screen, or None."""
        return self._stack[-1] if self._stack else None

    def invalidate(self):
        """Mark the display as needing a full redraw on the next tick."""
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
        # Mark the newly-revealed screen as needing a redraw
        if self._stack:
            revealed = self._stack[-1]
            if hasattr(revealed, "_dirty"):
                revealed._dirty = True
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
        """One frame: scan → update → render-if-needed → show-if-needed."""
        self._frame += 1
        self.inp.scan()

        active = self.active
        if active:
            active.update(self.inp, self._frame)

        if self._overlay:
            self._overlay.update(self.inp, self._frame)

        # Check if anything needs drawing
        screen_dirty = self._dirty
        if not screen_dirty and active:
            screen_dirty = active.needs_redraw()
        overlay_dirty = False
        if self._overlay:
            nr = getattr(self._overlay, "needs_redraw", None)
            overlay_dirty = nr() if nr else True

        if not screen_dirty and not overlay_dirty:
            if self.debug_perf:
                self._perf_total += 1
                self._perf_report()
            return  # nothing changed — skip render + SPI push

        # Clear on screen transitions
        if self._dirty:
            self.tft.fill(self.theme.BLACK)
            self._dirty = False

        takes_over = self._overlay and getattr(self._overlay, "takes_over", False)
        if active and not takes_over:
            active.render(self.tft, self.theme, self._frame)

        if self._overlay:
            self._overlay.render(self.tft, self.theme, self._frame)

        self.tft.show()

        if self.debug_perf:
            self._perf_total += 1
            self._perf_drawn += 1
            self._perf_report()

    def _perf_report(self):
        """Print perf stats every 100 frames."""
        if self._perf_total % 100 != 0:
            return
        total = self._perf_total
        drawn = self._perf_drawn
        pct = drawn * 100 // max(1, total)
        active = self.active
        name = active.__class__.__name__ if active else "none"
        print(
            "PERF f={} drawn={}/{}({}%) screen={}".format(
                self._frame, drawn, total, pct, name
            )
        )
        self._perf_total = 0
        self._perf_drawn = 0
