# bodn/ui/screen.py — Screen base class and ScreenManager

import gc


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

    def on_reveal(self):
        """Called when this screen becomes active again because the screen above it was popped.

        The default implementation resets _full_clear (if present) so that the
        first render after returning is a full redraw. Override for additional
        state that needs resetting on reveal.
        """
        if hasattr(self, "_full_clear"):
            self._full_clear = True

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

    # -- NFC tag routing protocol --
    # Screens that handle NFC cards override nfc_modes with the set of
    # tag mode strings they subscribe to.  When a tag is scanned whose
    # mode is in this set, on_nfc_tag() is called instead of switching
    # game modes.
    nfc_modes = frozenset()

    def on_nfc_tag(self, parsed):
        """Handle an NFC tag routed to this screen.

        *parsed* is a dict with keys (prefix, version, mode, id).
        Return True if consumed, False to fall through to mode switch.
        """
        return False


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
        self._show_needed = False  # framebuffer changed, just push SPI (no re-render)
        self._dirty_rect = None  # (x, y, w, h) bounding box for partial push
        self._prev_takes_over = False  # track overlay takeover transitions
        self._frames_skipped = 0  # consecutive render skips (for diagnostics)
        # Perf counters (enabled via debug_perf setting)
        self.debug_perf = False
        self._perf_total = 0
        self._perf_drawn = 0
        self._perf_skipped = 0
        self._perf_time_ms = None  # set to time_ms function when enabled

    @property
    def active(self):
        """Return the topmost screen, or None."""
        return self._stack[-1] if self._stack else None

    def invalidate(self):
        """Mark the display as needing a full redraw on the next tick."""
        self._dirty = True

    def invalidate_rect(self, x, y, w, h):
        """Mark a rectangle as needing a push on the next tick.

        Multiple calls are merged into the bounding-box union. Does NOT
        trigger a re-render — only a show_rect() push. Use after direct
        framebuffer writes (progress bars, timers, etc.).
        """
        if self._dirty_rect is None:
            self._dirty_rect = (x, y, w, h)
        else:
            ox, oy, ow, oh = self._dirty_rect
            nx = min(ox, x)
            ny = min(oy, y)
            nx2 = max(ox + ow, x + w)
            ny2 = max(oy + oh, y + h)
            self._dirty_rect = (nx, ny, nx2 - nx, ny2 - ny)

    def request_show(self, x=None, y=None, w=None, h=None):
        """Request a push on the next tick without a full re-render.

        With x/y/w/h: only that rectangle is pushed (show_rect).
        Without arguments: the full buffer is pushed (show).

        Use this after writing directly to the framebuffer (e.g. a small
        partial update like a progress bar). The ScreenManager will NOT
        re-render the active screen or overlay.
        """
        self._show_needed = True
        if x is not None:
            self.invalidate_rect(x, y, w, h)

    def push(self, screen):
        """Push a screen onto the stack."""
        gc.collect()
        self._stack.append(screen)
        self._dirty = True
        # Reset gesture detector so leftover button state (e.g. the press
        # that selected this mode on the home screen) doesn't bleed into
        # the new screen's first frame.
        self.inp.gestures.reset()
        screen.enter(self)

    def pop(self):
        """Pop the topmost screen. Returns it, or None if stack is empty."""
        if not self._stack:
            return None
        screen = self._stack.pop()
        screen.exit()
        gc.collect()
        self._dirty = True
        # Notify the newly-revealed screen so it can reset partial-draw state
        if self._stack:
            revealed = self._stack[-1]
            if hasattr(revealed, "_dirty"):
                revealed._dirty = True
            revealed.on_reveal()
        return screen

    def replace(self, screen):
        """Replace the topmost screen (lateral navigation)."""
        if self._stack:
            self._stack[-1].exit()
            self._stack[-1] = screen
        else:
            self._stack.append(screen)
        gc.collect()
        self._dirty = True
        screen.enter(self)

    def set_overlay(self, overlay):
        """Set a single overlay drawn after the main screen."""
        self._overlay = overlay

    # ------------------------------------------------------------------
    # Split-phase API (used by priority-ordered main loop)
    # ------------------------------------------------------------------

    def consume_and_update(self):
        """Phase 1: consume input + run game logic.  Always call this.

        Returns True if a render is needed (dirty screen, overlay, or
        pending show-only push).
        """
        self._frame += 1
        self.inp.consume()

        active = self.active
        if active:
            active.update(self.inp, self._frame)

        # Re-read: update() may have pushed or popped screens
        active = self.active

        if self._overlay:
            self._overlay.update(self.inp, self._frame)

        return self._needs_render(active)

    def _needs_render(self, active=None):
        """Check whether any visual update is needed this frame."""
        if self._dirty or self._show_needed:
            return True
        if active is None:
            active = self.active
        if active and active.needs_redraw():
            return True
        if self._overlay:
            nr = getattr(self._overlay, "needs_redraw", None)
            if nr and nr():
                return True
        return False

    def render_and_show(self):
        """Phase 2: render + SPI push.  Only call when budget allows.

        Handles both full render paths and show-only partial pushes.
        """
        active = self.active

        # Detect overlay takeover transitions: when the overlay stops taking
        # over, the framebuffer still has stale overlay content. Force a full
        # clear so the active screen repaints from scratch.
        takes_over = self._overlay and getattr(self._overlay, "takes_over", False)
        if self._prev_takes_over and not takes_over:
            self._dirty = True
            if active and hasattr(active, "_dirty"):
                active._dirty = True
        self._prev_takes_over = takes_over

        # Check if anything needs drawing
        screen_dirty = self._dirty
        if not screen_dirty and active:
            screen_dirty = active.needs_redraw()
        overlay_dirty = False
        if self._overlay:
            nr = getattr(self._overlay, "needs_redraw", None)
            overlay_dirty = nr() if nr else True

        if not screen_dirty and not overlay_dirty:
            # No re-render needed — handle show-only push
            if self._show_needed:
                self._show_needed = False
                dirty_rect = self._dirty_rect
                self._dirty_rect = None
                if dirty_rect is not None:
                    self.tft.show_rect(*dirty_rect)
                else:
                    self.tft.show()
            self._frames_skipped = 0
            if self.debug_perf:
                self._perf_total += 1
                self._perf_drawn += 1
                self._perf_report()
            return

        # Full render path
        self._show_needed = False
        self._dirty_rect = None

        # Clear on screen transitions
        if self._dirty:
            self.tft.fill(self.theme.BLACK)
            self._dirty = False

        takes_over = self._overlay and getattr(self._overlay, "takes_over", False)
        if active and not takes_over:
            active.render(self.tft, self.theme, self._frame)

        if self._overlay:
            self._overlay.render(self.tft, self.theme, self._frame)

        # Push only the dirty region to the display (auto-tracked by ST7735)
        self.tft.show_dirty()

        self._frames_skipped = 0
        if self.debug_perf:
            self._perf_total += 1
            self._perf_drawn += 1
            self._perf_report()

    def skip_render(self):
        """Record a skipped frame (called by main loop when budget exhausted)."""
        self._frames_skipped += 1
        if self.debug_perf:
            self._perf_total += 1
            self._perf_skipped += 1
            self._perf_report()

    # ------------------------------------------------------------------
    # Legacy single-call API (used by secondary display and tests)
    # ------------------------------------------------------------------

    def tick(self):
        """One frame: consume → update → render-if-needed → show-if-needed."""
        self._frame += 1
        self.inp.consume()

        active = self.active
        if active:
            active.update(self.inp, self._frame)

        # Re-read: update() may have pushed or popped screens
        active = self.active

        if self._overlay:
            self._overlay.update(self.inp, self._frame)

        # Detect overlay takeover transitions (see render_and_show)
        takes_over = self._overlay and getattr(self._overlay, "takes_over", False)
        if self._prev_takes_over and not takes_over:
            self._dirty = True
            if active and hasattr(active, "_dirty"):
                active._dirty = True
        self._prev_takes_over = takes_over

        # Check if anything needs drawing
        screen_dirty = self._dirty
        if not screen_dirty and active:
            screen_dirty = active.needs_redraw()
        overlay_dirty = False
        if self._overlay:
            nr = getattr(self._overlay, "needs_redraw", None)
            overlay_dirty = nr() if nr else True

        if not screen_dirty and not overlay_dirty:
            # No re-render needed. Check if a show-only push was requested
            # (e.g. partial framebuffer update like a progress bar).
            if self._show_needed:
                self._show_needed = False
                dirty_rect = self._dirty_rect
                self._dirty_rect = None
                if dirty_rect is not None:
                    self.tft.show_rect(*dirty_rect)
                else:
                    self.tft.show()
                if self.debug_perf:
                    self._perf_total += 1
                    self._perf_drawn += 1
                    self._perf_report()
            elif self.debug_perf:
                self._perf_total += 1
                self._perf_report()
            return

        # Full render path
        self._show_needed = False
        self._dirty_rect = None

        # Clear on screen transitions
        if self._dirty:
            self.tft.fill(self.theme.BLACK)
            self._dirty = False

        takes_over = self._overlay and getattr(self._overlay, "takes_over", False)
        if active and not takes_over:
            active.render(self.tft, self.theme, self._frame)

        if self._overlay:
            self._overlay.render(self.tft, self.theme, self._frame)

        # Push only the dirty region to the display (auto-tracked by ST7735)
        self.tft.show_dirty()

        if self.debug_perf:
            self._perf_total += 1
            self._perf_drawn += 1
            self._perf_report()

    def _perf_report(self):
        """Print perf stats every 50 frames (~1.5s)."""
        if self._perf_total < 50:
            return
        total = self._perf_total
        drawn = self._perf_drawn
        skipped = self._perf_skipped
        pct = drawn * 100 // max(1, total)
        active = self.active
        name = active.__class__.__name__ if active else "none"
        print(
            "PERF f={} drawn={}/{}({}%) skip={} screen={}".format(
                self._frame, drawn, total, pct, skipped, name
            )
        )
        self._perf_total = 0
        self._perf_drawn = 0
        self._perf_skipped = 0
