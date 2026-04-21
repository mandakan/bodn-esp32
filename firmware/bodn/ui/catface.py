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


class CatFaceScreen(Screen):
    """A cat face that reacts to game state.

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

        # --- Ears (drawn first, face overlaps the base) ---
        # Outer (amber) and inner (pink) triangles
        _fill_triangle(tft, 28, 24, 18, 4, 44, 22, theme.AMBER)
        _fill_triangle(tft, 100, 24, 110, 4, 84, 22, theme.AMBER)
        _fill_triangle(tft, 32, 23, 26, 12, 40, 21, theme.MAGENTA)
        _fill_triangle(tft, 96, 23, 102, 12, 88, 21, theme.MAGENTA)

        # --- Head ---
        cx, cy = 64, 60
        _fill_circle(tft, cx, cy, 40, theme.AMBER)

        # --- Eyes ---
        if e == SLEEPY:
            # Closed crescents — gentle downward arcs (⌒  ⌒)
            for ex, ey in (_EYE_L, _EYE_R):
                for dx in range(-7, 8):
                    dy = (49 - dx * dx) // 14  # peak ~3 at centre, 0 at corners
                    tft.fill_rect(ex + dx, ey + dy, 1, 2, theme.BLACK)
        elif e == HAPPY:
            # Closed smiling eyes — upside-down U (^  ^)
            for ex, ey in (_EYE_L, _EYE_R):
                for dx in range(-7, 8):
                    dy = -((49 - dx * dx) // 14)  # peak upward in centre
                    tft.fill_rect(ex + dx, ey + dy, 1, 2, theme.BLACK)
        elif e == SURPRISED:
            # Wide open eyes with big pupils
            for ex, ey in (_EYE_L, _EYE_R):
                _fill_circle(tft, ex, ey, 9, theme.WHITE)
                _fill_circle(tft, ex, ey, 6, theme.BLACK)
                tft.fill_rect(ex - 3, ey - 3, 2, 2, theme.WHITE)
        elif e == CURIOUS:
            # Alert eyes, pupils nudged up and slightly inward
            for (cx_e, cy_e), px in ((_EYE_L, 1), (_EYE_R, -1)):
                _fill_circle(tft, cx_e, cy_e, 7, theme.WHITE)
                _fill_circle(tft, cx_e + px, cy_e - 1, 4, theme.BLACK)
                tft.fill_rect(cx_e - 2, cy_e - 3, 2, 2, theme.WHITE)
        else:
            # NEUTRAL — soft round eyes with highlight
            for ex, ey in (_EYE_L, _EYE_R):
                _fill_circle(tft, ex, ey, 6, theme.WHITE)
                _fill_circle(tft, ex, ey, 4, theme.BLACK)
                tft.fill_rect(ex - 2, ey - 2, 2, 2, theme.WHITE)

        # --- Nose (pink triangle) ---
        _fill_triangle(tft, 60, 68, 68, 68, 64, 72, theme.MAGENTA)

        # --- Mouth ---
        # Y increases downward, so a smile has centre at higher y than corners.
        if e == HAPPY:
            # Open smile with a hint of tongue and blush
            for dx in range(-11, 12):
                depth = 7 - (dx * dx) // 17
                if depth > 0:
                    tft.fill_rect(64 + dx, _MOUTH_Y, 1, depth, theme.BLACK)
            _fill_circle(tft, 64, _MOUTH_Y + 5, 3, theme.RED)
            _fill_circle(tft, 34, 70, 5, theme.MAGENTA)
            _fill_circle(tft, 94, 70, 5, theme.MAGENTA)
        elif e == SURPRISED:
            # Round open mouth
            _fill_circle(tft, 64, _MOUTH_Y + 3, 4, theme.BLACK)
        elif e == SLEEPY:
            # Tiny relaxed line
            tft.hline(60, _MOUTH_Y + 2, 8, theme.BLACK)
            tft.hline(60, _MOUTH_Y + 3, 8, theme.BLACK)
        elif e == CURIOUS:
            # Small 'o'
            _fill_circle(tft, 64, _MOUTH_Y + 2, 3, theme.BLACK)
        else:
            # NEUTRAL — gentle smile (kid-friendly default; no more sad cat)
            for dx in range(-8, 9):
                depth = 3 - (dx * dx) // 22
                if depth > 0:
                    tft.fill_rect(64 + dx, _MOUTH_Y + 1, 1, depth, theme.BLACK)

        # --- Whiskers ---
        wc = theme.MUTED if e == SLEEPY else theme.BLACK
        # Left
        tft.hline(12, 62, 28, wc)
        tft.hline(14, 68, 26, wc)
        tft.hline(16, 74, 22, wc)
        # Right
        tft.hline(88, 62, 28, wc)
        tft.hline(88, 68, 26, wc)
        tft.hline(90, 74, 22, wc)

        # --- Sleep Zs ---
        if e == SLEEPY:
            _draw_z(tft, 92, 28, 8, theme.MUTED)
            _draw_z(tft, 104, 14, 6, theme.MUTED)


def _draw_z(tft, x, y, size, color):
    """Tiny 'Z' glyph for sleep indicator."""
    tft.hline(x, y, size, color)
    tft.hline(x, y + size - 1, size, color)
    # Diagonal via short hlines
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
    # Sort by y
    pts = sorted([(x0, y0), (x1, y1), (x2, y2)], key=lambda p: p[1])
    (ax, ay), (bx, by), (cx, cy) = pts

    if ay == cy:
        return

    for y in range(ay, cy + 1):
        # Interpolate x on edges
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
