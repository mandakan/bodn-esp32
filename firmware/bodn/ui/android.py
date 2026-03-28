# bodn/ui/android.py — "Stellar" android face for the secondary display
#
# Represents the on-board AI in spaceship mode.
# Same interface as CatFaceScreen — drop-in replacement for the content zone.
#
# Emotions:
#   NEUTRAL   — cruising, all clear       (cyan visor eyes, flat mouth)
#   CURIOUS   — scenario active / hint    (yellow asymmetric eyes, scanning bar)
#   HAPPY     — scenario success          (green arc eyes, segmented smile)
#   SURPRISED — scenario announced        (white round eyes, "!" panel)

from bodn.ui.screen import Screen
from bodn.ui.secondary import CONTENT_SIZE

# Emotion constants — string values match catface.py for interoperability
NEUTRAL = "neutral"
CURIOUS = "curious"
HAPPY = "happy"
SURPRISED = "surprised"


class AndroidFaceScreen(Screen):
    """Robot face representing Stellar, the spaceship AI.

    Designed for the 128×128 content zone of the secondary display.
    Call set_emotion() to change the expression.
    """

    def __init__(self):
        self._emotion = NEUTRAL
        self._dirty = True

    def enter(self, display):
        self._dirty = True

    def set_emotion(self, emotion):
        if emotion != self._emotion:
            self._emotion = emotion
            self._dirty = True

    def needs_redraw(self):
        return self._dirty

    def render(self, tft, theme, frame):
        self._dirty = False
        tft.fill_rect(0, 0, CONTENT_SIZE, CONTENT_SIZE, theme.BLACK)
        e = self._emotion

        # --- Antenna ---
        # Stem
        tft.fill_rect(61, 6, 6, 16, theme.MUTED)
        # Ball — colour signals ship status
        ant_col = (
            theme.WHITE
            if e == SURPRISED
            else (theme.GREEN if e == HAPPY else theme.CYAN)
        )
        _fill_circle(tft, 64, 7, 6, ant_col)

        # --- Head — dark steel rectangle with double cyan border ---
        hx, hy, hw, hh = 12, 22, 104, 90
        tft.fill_rect(hx, hy, hw, hh, theme.DIM)
        tft.rect(hx, hy, hw, hh, theme.CYAN)
        tft.rect(hx + 1, hy + 1, hw - 2, hh - 2, theme.CYAN)

        # Corner rivets
        for rx, ry in ((20, 29), (108, 29), (20, 105), (108, 105)):
            _fill_circle(tft, rx, ry, 3, theme.MUTED)

        # Ear ports (side rectangles)
        tft.fill_rect(8, 52, 4, 20, theme.MUTED)
        tft.rect(8, 52, 4, 20, theme.CYAN)
        tft.fill_rect(116, 52, 4, 20, theme.MUTED)
        tft.rect(116, 52, 4, 20, theme.CYAN)

        # --- Eyes ---
        # Visor-style: two horizontal rectangles in the upper face area.
        # Shape and colour change per emotion.
        eye_y = 54  # vertical centre of eye area
        lx = 26  # left eye rect x
        rx = 74  # right eye rect x
        ew = 28  # eye width
        eh = 12  # eye height (neutral)

        if e == NEUTRAL:
            # Flat cyan visor bars with a scan line
            eye_col = theme.CYAN
            tft.fill_rect(lx, eye_y - eh // 2, ew, eh, eye_col)
            tft.hline(lx, eye_y, ew, theme.BLACK)
            tft.fill_rect(rx, eye_y - eh // 2, ew, eh, eye_col)
            tft.hline(rx, eye_y, ew, theme.BLACK)

        elif e == CURIOUS:
            # Yellow, asymmetric: right eye taller (one raised eyebrow)
            eye_col = theme.YELLOW
            tft.fill_rect(lx, eye_y - eh // 2, ew, eh, eye_col)
            tft.fill_rect(lx + 2, eye_y - eh // 2 + 3, ew - 4, eh - 6, theme.DIM)
            tft.fill_rect(rx, eye_y - eh, ew, eh + 6, eye_col)
            tft.fill_rect(rx + 2, eye_y - eh + 3, ew - 4, eh, theme.DIM)

        elif e == HAPPY:
            # Green upward arcs (^ ^) — tent function, 2-pixel stroke
            eye_col = theme.GREEN
            half = ew // 2
            peak = eh - 2
            for dx in range(ew):
                dist = abs(dx - half)
                dy = peak - (peak * dist // half)
                tft.fill_rect(lx + dx, eye_y - dy, 2, dy + 4, eye_col)
                tft.fill_rect(rx + dx, eye_y - dy, 2, dy + 4, eye_col)

        elif e == SURPRISED:
            # Round white eyes with black pupils and highlight
            eye_col = theme.WHITE
            ecx_l = lx + ew // 2
            ecx_r = rx + ew // 2
            _fill_circle(tft, ecx_l, eye_y, ew // 2, eye_col)
            _fill_circle(tft, ecx_r, eye_y, ew // 2, eye_col)
            # Pupils
            _fill_circle(tft, ecx_l, eye_y, ew // 5, theme.BLACK)
            _fill_circle(tft, ecx_r, eye_y, ew // 5, theme.BLACK)
            # Highlights
            tft.fill_rect(ecx_l - 7, eye_y - 6, 4, 4, theme.WHITE)
            tft.fill_rect(ecx_r - 7, eye_y - 6, 4, 4, theme.WHITE)

        # --- Mouth display panel ---
        mx, my, mw, mh = 24, 82, 80, 18
        tft.fill_rect(mx, my, mw, mh, theme.BLACK)
        tft.rect(mx, my, mw, mh, theme.CYAN)

        if e == NEUTRAL:
            # Centered double dash — steady state
            mid = my + mh // 2
            tft.hline(mx + 18, mid - 1, mw - 36, theme.CYAN)
            tft.hline(mx + 18, mid, mw - 36, theme.CYAN)

        elif e == CURIOUS:
            # Scanning bar (partial fill, left-aligned) + cursor block
            tft.fill_rect(mx + 3, my + 5, 36, mh - 10, theme.YELLOW)
            tft.fill_rect(mx + 41, my + 5, 7, mh - 10, theme.AMBER)

        elif e == HAPPY:
            # Five green segments — segmented smile
            seg_w = 10
            gap = 4
            total = 5 * seg_w + 4 * gap
            sx = mx + (mw - total) // 2
            for i in range(5):
                tft.fill_rect(
                    sx + i * (seg_w + gap), my + 4, seg_w, mh - 8, theme.GREEN
                )

        elif e == SURPRISED:
            # "!" — white bar + dot
            bx = mx + mw // 2 - 4
            tft.fill_rect(bx, my + 2, 8, mh - 8, theme.WHITE)
            tft.fill_rect(bx, my + mh - 5, 8, 3, theme.WHITE)

        # --- Decorative panel lines at head top ---
        tft.hline(hx + 8, hy + 7, 18, theme.MUTED)
        tft.hline(hx + hw - 26, hy + 7, 18, theme.MUTED)


def _fill_circle(tft, cx, cy, r, color):
    """Draw a filled circle using horizontal lines."""
    for dy in range(-r, r + 1):
        dx = 0
        while dx * dx + dy * dy <= r * r:
            dx += 1
        dx -= 1
        if dx >= 0:
            tft.hline(cx - dx, cy + dy, 2 * dx + 1, color)
