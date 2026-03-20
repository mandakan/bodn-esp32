# bodn/ui/secondary.py — two-zone renderer for the secondary display
#
# Layout (128×160):
#   Content zone: y=0..127   (128×128 square — game visuals, ambient clock, etc.)
#   Status strip: y=128..159 (128×32 — always-visible clock + session timer)


CONTENT_H = 128
STATUS_Y = 128
STATUS_H = 32


class SecondaryDisplay:
    """Manages the secondary display as two independent zones.

    - **Content** (128×128 square): swappable per game mode via set_content().
    - **Status strip** (128×32): persistent clock + session bar via set_status().

    Each zone tracks its own dirty state. A single tft.show() is issued
    only when at least one zone was redrawn.
    """

    def __init__(self, tft, theme):
        self.tft = tft
        self.theme = theme
        self._content = None
        self._status = None
        self._frame = 0
        self._content_dirty = True
        self._status_dirty = True

    # -- Zone geometry (content screens read these in enter()) --

    content_y = 0
    content_w = 128
    content_h = CONTENT_H
    status_y = STATUS_Y
    status_h = STATUS_H

    # -- Content zone --

    def set_content(self, screen):
        """Set the 128×128 content screen (or None for blank)."""
        if self._content:
            self._content.exit()
        self._content = screen
        self._content_dirty = True
        if self._content:
            self._content.enter(self)

    # -- Status strip --

    def set_status(self, widget):
        """Set the 32px status strip widget."""
        if self._status:
            self._status.exit()
        self._status = widget
        self._status_dirty = True
        if self._status:
            self._status.enter(self)

    # -- Legacy alias --

    def set_screen(self, screen):
        """Backward-compatible alias for set_content()."""
        self.set_content(screen)

    # -- Invalidation --

    def invalidate(self, zone="both"):
        """Force a redraw. zone: 'content', 'status', or 'both'."""
        if zone in ("content", "both"):
            self._content_dirty = True
        if zone in ("status", "both"):
            self._status_dirty = True

    # -- Tick --

    def tick(self, inp=None):
        """One frame: update both zones, redraw only dirty ones, single show()."""
        self._frame += 1
        redraw = False

        # Update
        if self._content and inp:
            self._content.update(inp, self._frame)
        if self._status and inp:
            self._status.update(inp, self._frame)

        # Content zone
        content_needs = False
        if self._content_dirty:
            content_needs = True
        elif self._content:
            nr = getattr(self._content, "needs_redraw", None)
            content_needs = nr() if nr else False

        if content_needs:
            self.tft.fill_rect(0, 0, self.content_w, CONTENT_H, self.theme.BLACK)
            if self._content:
                self._content.render(self.tft, self.theme, self._frame)
            self._content_dirty = False
            redraw = True

        # Status strip
        status_needs = False
        if self._status_dirty:
            status_needs = True
        elif self._status:
            nr = getattr(self._status, "needs_redraw", None)
            status_needs = nr() if nr else False

        if status_needs:
            self.tft.fill_rect(0, STATUS_Y, self.content_w, STATUS_H, self.theme.BLACK)
            if self._status:
                self._status.render(self.tft, self.theme, self._frame)
            self._status_dirty = False
            redraw = True

        if redraw:
            self.tft.show()
