# bodn/ui/catface.py — cat face for the secondary display content zone
#
# Draws a simple cat face in 128×128 using geometric primitives.
# The emotion can be changed by game modes via set_emotion().

from bodn.ui.screen import Screen
from bodn.ui.secondary import CONTENT_SIZE

# Emotion constants
NEUTRAL = "neutral"
CURIOUS = "curious"
HAPPY = "happy"
SLEEPY = "sleepy"
SURPRISED = "surprised"


# Eye centres (shared by all emotions so the face stays anchored)
_EYE_L = (52, 56)
_EYE_R = (76, 56)
_MOUTH_Y = 76

# Eye band covered by partial repaints during gaze animation.
# Wide enough to cover both eye whites + the highlight pixel.
_EYE_BAND = (40, 47, 48, 20)  # x, y, w, h

# Curious gaze cycle: (pupil_dx, pupil_dy) applied on top of the up-nudge.
# The pattern dwells on centre, darts left, back, right, back.
_GAZE_PATTERN = (
    (0, 0),  # centre (hold)
    (0, 0),  # centre (hold)
    (-2, 0),  # glance left
    (0, 0),  # centre
    (2, 0),  # glance right
    (0, 0),  # centre
)
# Ticks per gaze slot. needs_redraw() is called once per secondary tick
# (~20 fps in DMA mode, ~5 fps in blocking mode), so 18 ticks ≈ 0.9 s / slot
# when the display is fast and ~3.6 s / slot when blocking.
_GAZE_TICKS_PER_SLOT = 18


class CatFaceScreen(Screen):
    """A cat face that reacts to game state.

    Designed for the 128×128 content zone of the secondary display.
    Call set_emotion() to change the expression.  When the emotion is
    CURIOUS the pupils dart left/right on a slow cycle; only the eye
    band is repainted for the animation, so the rest of the face is
    untouched between emotion changes.
    """

    def __init__(self):
        self._emotion = NEUTRAL
        self._dirty = True
        self._eyes_dirty = False
        self._gaze_slot = 0
        self._anim_ticks = 0

    def enter(self, display):
        self._dirty = True
        # Restart gaze cycle each time the face becomes active.
        self._gaze_slot = 0
        self._anim_ticks = 0

    def set_emotion(self, emotion):
        if emotion != self._emotion:
            self._emotion = emotion
            self._dirty = True
            # Reset the cycle so the new emotion starts from centre.
            self._gaze_slot = 0
            self._anim_ticks = 0

    def needs_redraw(self):
        if self._dirty:
            return True
        if self._emotion == CURIOUS:
            # Advance the animation clock.  Slot changes mark the eye
            # band dirty so render() does a partial repaint.
            self._anim_ticks += 1
            new_slot = (self._anim_ticks // _GAZE_TICKS_PER_SLOT) % len(_GAZE_PATTERN)
            if new_slot != self._gaze_slot:
                self._gaze_slot = new_slot
                self._eyes_dirty = True
        return self._eyes_dirty

    def render(self, tft, theme, frame):
        if self._dirty:
            self._dirty = False
            self._eyes_dirty = False
            self._draw_full(tft, theme)
        elif self._eyes_dirty:
            self._eyes_dirty = False
            # Partial repaint: cover the eye band with the face colour
            # and redraw the current eye shape on top.
            bx, by, bw, bh = _EYE_BAND
            tft.fill_rect(bx, by, bw, bh, theme.AMBER)
            self._draw_eyes(tft, theme)

    # -- internal --

    def _draw_full(self, tft, theme):
        tft.fill_rect(0, 0, CONTENT_SIZE, CONTENT_SIZE, theme.BLACK)
        e = self._emotion

        # --- Ears (drawn first, face overlaps the base) ---
        _fill_triangle(tft, 28, 24, 18, 4, 44, 22, theme.AMBER)
        _fill_triangle(tft, 100, 24, 110, 4, 84, 22, theme.AMBER)
        _fill_triangle(tft, 32, 23, 26, 12, 40, 21, theme.MAGENTA)
        _fill_triangle(tft, 96, 23, 102, 12, 88, 21, theme.MAGENTA)

        # --- Head ---
        _fill_circle(tft, 64, 60, 40, theme.AMBER)

        # --- Eyes ---
        self._draw_eyes(tft, theme)

        # --- Nose (pink triangle) ---
        _fill_triangle(tft, 60, 68, 68, 68, 64, 72, theme.MAGENTA)

        # --- Mouth ---
        # Y increases downward, so a smile has centre at higher y than corners.
        if e == HAPPY:
            for dx in range(-11, 12):
                depth = 7 - (dx * dx) // 17
                if depth > 0:
                    tft.fill_rect(64 + dx, _MOUTH_Y, 1, depth, theme.BLACK)
            _fill_circle(tft, 64, _MOUTH_Y + 5, 3, theme.RED)
            _fill_circle(tft, 34, 70, 5, theme.MAGENTA)
            _fill_circle(tft, 94, 70, 5, theme.MAGENTA)
        elif e == SURPRISED:
            _fill_circle(tft, 64, _MOUTH_Y + 3, 4, theme.BLACK)
        elif e == SLEEPY:
            tft.hline(60, _MOUTH_Y + 2, 8, theme.BLACK)
            tft.hline(60, _MOUTH_Y + 3, 8, theme.BLACK)
        elif e == CURIOUS:
            _fill_circle(tft, 64, _MOUTH_Y + 2, 3, theme.BLACK)
        else:
            # NEUTRAL — gentle smile
            for dx in range(-8, 9):
                depth = 3 - (dx * dx) // 22
                if depth > 0:
                    tft.fill_rect(64 + dx, _MOUTH_Y + 1, 1, depth, theme.BLACK)

        # --- Whiskers ---
        wc = theme.MUTED if e == SLEEPY else theme.BLACK
        tft.hline(12, 62, 28, wc)
        tft.hline(14, 68, 26, wc)
        tft.hline(16, 74, 22, wc)
        tft.hline(88, 62, 28, wc)
        tft.hline(88, 68, 26, wc)
        tft.hline(90, 74, 22, wc)

        # --- Sleep Zs ---
        if e == SLEEPY:
            _draw_z(tft, 92, 28, 8, theme.MUTED)
            _draw_z(tft, 104, 14, 6, theme.MUTED)

    def _draw_eyes(self, tft, theme):
        e = self._emotion
        if e == SLEEPY:
            # Closed crescents — gentle downward arcs (⌒  ⌒)
            for ex, ey in (_EYE_L, _EYE_R):
                for dx in range(-7, 8):
                    dy = (49 - dx * dx) // 14
                    tft.fill_rect(ex + dx, ey + dy, 1, 2, theme.BLACK)
        elif e == HAPPY:
            # Closed smiling eyes — upside-down U (^  ^)
            for ex, ey in (_EYE_L, _EYE_R):
                for dx in range(-7, 8):
                    dy = -((49 - dx * dx) // 14)
                    tft.fill_rect(ex + dx, ey + dy, 1, 2, theme.BLACK)
        elif e == SURPRISED:
            for ex, ey in (_EYE_L, _EYE_R):
                _fill_circle(tft, ex, ey, 9, theme.WHITE)
                _fill_circle(tft, ex, ey, 6, theme.BLACK)
                tft.fill_rect(ex - 3, ey - 3, 2, 2, theme.WHITE)
        elif e == CURIOUS:
            gx, gy = _GAZE_PATTERN[self._gaze_slot]
            # px_bias keeps pupils slightly converged (cute "really looking" look).
            for (cx_e, cy_e), px in ((_EYE_L, 1), (_EYE_R, -1)):
                _fill_circle(tft, cx_e, cy_e, 7, theme.WHITE)
                _fill_circle(tft, cx_e + px + gx, cy_e - 1 + gy, 4, theme.BLACK)
                tft.fill_rect(cx_e - 2, cy_e - 3, 2, 2, theme.WHITE)
        else:
            # NEUTRAL — soft round eyes with highlight
            for ex, ey in (_EYE_L, _EYE_R):
                _fill_circle(tft, ex, ey, 6, theme.WHITE)
                _fill_circle(tft, ex, ey, 4, theme.BLACK)
                tft.fill_rect(ex - 2, ey - 2, 2, 2, theme.WHITE)


def _draw_z(tft, x, y, size, color):
    """Tiny 'Z' glyph for sleep indicator."""
    tft.hline(x, y, size, color)
    tft.hline(x, y + size - 1, size, color)
    for i in range(size):
        tft.fill_rect(x + size - 1 - i, y + i, 1, 1, color)


def _fill_circle(tft, cx, cy, r, color):
    """Draw a filled circle using horizontal lines."""
    for dy in range(-r, r + 1):
        # Integer sqrt approximation
        dx = 0
        while dx * dx + dy * dy <= r * r:
            dx += 1
        dx -= 1
        if dx >= 0:
            tft.hline(cx - dx, cy + dy, 2 * dx + 1, color)


def _fill_triangle(tft, x0, y0, x1, y1, x2, y2, color):
    """Fill a triangle by scanline (simple, not performance-critical)."""
    pts = sorted([(x0, y0), (x1, y1), (x2, y2)], key=lambda p: p[1])
    (ax, ay), (bx, by), (cx, cy) = pts

    if ay == cy:
        return

    for y in range(ay, cy + 1):
        if y < by:
            if by - ay > 0:
                xa = ax + (bx - ax) * (y - ay) // (by - ay)
            else:
                xa = ax
            xb = ax + (cx - ax) * (y - ay) // (cy - ay)
        else:
            if cy - by > 0:
                xa = bx + (cx - bx) * (y - by) // (cy - by)
            else:
                xa = bx
            xb = ax + (cx - ax) * (y - ay) // (cy - ay)

        if xa > xb:
            xa, xb = xb, xa
        tft.hline(xa, y, xb - xa + 1, color)
