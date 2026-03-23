# bodn/ui/secondary.py — two-zone renderer for the secondary display
#
# Portrait layout (128×160):
#   Content zone: y=0..127   (128×128 square — game visuals, ambient clock, etc.)
#   Status strip: y=128..159 (128×32 — always-visible clock + session timer)
#
# Landscape layout (160×128):
#   Status strip: x=0..31    (32×128 — vertical clock + session info)
#   Content zone: x=32..159  (128×128 square — same content, shifted right)
#
# Content screens always render into a 128×128 space at (0,0).
# A lightweight viewport wrapper offsets all drawing calls so the
# orientation change is transparent to content screens.

from micropython import const

CONTENT_SIZE = const(128)  # content zone is always 128×128
STATUS_THICK = const(32)  # status strip thickness (width or height)


class _Viewport:
    """Thin wrapper that offsets drawing calls into a sub-region of the tft.

    Content screens draw at (0,0) and the viewport translates to the
    correct physical position.  Exposes .width and .height matching
    the zone so screens can use them for centering.
    """

    __slots__ = ("_tft", "_xo", "_yo", "width", "height")

    def __init__(self, tft, x_off, y_off, w, h):
        self._tft = tft
        self._xo = x_off
        self._yo = y_off
        self.width = w
        self.height = h

    def fill_rect(self, x, y, w, h, c):
        self._tft.fill_rect(x + self._xo, y + self._yo, w, h, c)

    def hline(self, x, y, w, c):
        self._tft.hline(x + self._xo, y + self._yo, w, c)

    def vline(self, x, y, h, c):
        self._tft.vline(x + self._xo, y + self._yo, h, c)

    def text(self, s, x, y, c):
        self._tft.text(s, x + self._xo, y + self._yo, c)

    def rect(self, x, y, w, h, c):
        self._tft.rect(x + self._xo, y + self._yo, w, h, c)

    def pixel(self, x, y, c):
        self._tft.pixel(x + self._xo, y + self._yo, c)


class SecondaryDisplay:
    """Manages the secondary display as two independent zones.

    - **Content** (128×128 square): swappable per game mode via set_content().
    - **Status strip** (32px): persistent clock + session bar via set_status().

    Each zone tracks its own dirty state. A single tft.show() is issued
    only when at least one zone was redrawn.

    The ``landscape`` flag controls layout direction:
    - Portrait:  content on top, status on bottom (128×32 horizontal strip)
    - Landscape: status on left (32×128 vertical strip), content on right
    """

    def __init__(self, tft, theme, landscape=False):
        self.tft = tft
        self.theme = theme
        self.landscape = landscape
        self._content = None
        self._status = None
        self._frame = 0
        self._content_dirty = True
        self._status_dirty = True

        # Compute zone geometry
        if landscape:
            # Status on the left, content on the right
            self._status_vp = _Viewport(tft, 0, 0, STATUS_THICK, CONTENT_SIZE)
            self._content_vp = _Viewport(
                tft, STATUS_THICK, 0, CONTENT_SIZE, CONTENT_SIZE
            )
            self._status_rect = (0, 0, STATUS_THICK, CONTENT_SIZE)
            self._content_rect = (STATUS_THICK, 0, CONTENT_SIZE, CONTENT_SIZE)
        else:
            # Content on top, status on the bottom
            self._content_vp = _Viewport(tft, 0, 0, CONTENT_SIZE, CONTENT_SIZE)
            self._status_vp = _Viewport(
                tft, 0, CONTENT_SIZE, CONTENT_SIZE, STATUS_THICK
            )
            self._content_rect = (0, 0, CONTENT_SIZE, CONTENT_SIZE)
            self._status_rect = (0, CONTENT_SIZE, CONTENT_SIZE, STATUS_THICK)

    # -- Zone geometry (read by content / status screens) --

    content_w = CONTENT_SIZE
    content_h = CONTENT_SIZE

    @property
    def content_y(self):
        return self._content_rect[1]

    @property
    def status_y(self):
        return self._status_rect[1]

    @property
    def status_w(self):
        return self._status_vp.width

    @property
    def status_h(self):
        return self._status_vp.height

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
        """Set the status strip widget."""
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
        """One frame: update both zones, redraw only dirty ones, single show().

        Full zone clears (fill_rect) only happen on transitions (set_content /
        set_status).  Normal redraws delegate clearing to the screen itself,
        so screens that track partial changes can skip unchanged regions.
        """
        self._frame += 1
        redraw = False

        # Update
        if self._content and inp:
            self._content.update(inp, self._frame)
        if self._status and inp:
            self._status.update(inp, self._frame)

        # Content zone
        cx, cy, cw, ch = self._content_rect
        content_needs = False
        if self._content_dirty:
            content_needs = True
        elif self._content:
            nr = getattr(self._content, "needs_redraw", None)
            content_needs = nr() if nr else False

        if content_needs:
            if self._content_dirty:
                self.tft.fill_rect(cx, cy, cw, ch, self.theme.BLACK)
                self._content_dirty = False
            if self._content:
                self._content.render(self._content_vp, self.theme, self._frame)
            redraw = True

        # Status strip
        sx, sy, sw, sh = self._status_rect
        status_needs = False
        if self._status_dirty:
            status_needs = True
        elif self._status:
            nr = getattr(self._status, "needs_redraw", None)
            status_needs = nr() if nr else False

        if status_needs:
            if self._status_dirty:
                self.tft.fill_rect(sx, sy, sw, sh, self.theme.BLACK)
                self._status_dirty = False
            if self._status:
                self._status.render(self._status_vp, self.theme, self._frame)
            redraw = True

        if redraw:
            if content_needs and not status_needs:
                self.tft.show_rect(cx, cy, cw, ch)
            elif status_needs and not content_needs:
                self.tft.show_rect(sx, sy, sw, sh)
            else:
                self.tft.show()
