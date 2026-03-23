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

        # Face circle (filled, centered in 128×128)
        cx, cy = 64, 58
        r = 38
        _fill_circle(tft, cx, cy, r, theme.AMBER)

        # Ears (triangles via stacked hlines)
        _fill_triangle(tft, 30, 22, 18, 4, 42, 22, theme.AMBER)
        _fill_triangle(tft, 98, 22, 86, 4, 110, 22, theme.AMBER)
        # Inner ears
        _fill_triangle(tft, 30, 24, 22, 12, 38, 24, theme.ORANGE)
        _fill_triangle(tft, 98, 24, 90, 12, 106, 24, theme.ORANGE)

        # Eyes
        if e == SLEEPY:
            # Closed eyes — horizontal lines
            tft.hline(46, 55, 14, theme.BLACK)
            tft.hline(68, 55, 14, theme.BLACK)
            tft.hline(46, 56, 14, theme.BLACK)
            tft.hline(68, 56, 14, theme.BLACK)
        elif e == HAPPY:
            # Happy eyes — upward arcs (^  ^)
            for dx in range(12):
                dy = -(4 - abs(dx - 6)) if abs(dx - 6) <= 4 else 0
                tft.fill_rect(47 + dx, 52 + dy, 2, 2, theme.BLACK)
                tft.fill_rect(69 + dx, 52 + dy, 2, 2, theme.BLACK)
        elif e == CURIOUS:
            # Wide eyes — larger circles
            _fill_circle(tft, 53, 54, 7, theme.WHITE)
            _fill_circle(tft, 75, 54, 7, theme.WHITE)
            _fill_circle(tft, 53, 54, 4, theme.BLACK)
            _fill_circle(tft, 75, 54, 4, theme.BLACK)
            # Highlight
            tft.fill_rect(50, 51, 2, 2, theme.WHITE)
            tft.fill_rect(72, 51, 2, 2, theme.WHITE)
        else:
            # Neutral — simple circles
            _fill_circle(tft, 53, 54, 5, theme.WHITE)
            _fill_circle(tft, 75, 54, 5, theme.WHITE)
            _fill_circle(tft, 53, 54, 3, theme.BLACK)
            _fill_circle(tft, 75, 54, 3, theme.BLACK)

        # Nose — small pink diamond
        nose_color = theme.MAGENTA
        tft.fill_rect(62, 64, 4, 3, nose_color)

        # Mouth
        if e == HAPPY:
            # Big smile
            for dx in range(20):
                dy = (dx - 10) * (dx - 10) // 15
                tft.fill_rect(54 + dx, 72 + dy, 2, 2, theme.BLACK)
        elif e == CURIOUS:
            # Small 'o'
            _fill_circle(tft, 64, 73, 3, theme.BLACK)
            _fill_circle(tft, 64, 73, 1, theme.AMBER)
        else:
            # Neutral/sleepy — gentle curve
            for dx in range(14):
                dy = (dx - 7) * (dx - 7) // 20
                tft.fill_rect(57 + dx, 72 + dy, 2, 1, theme.BLACK)

        # Whiskers
        wc = theme.BLACK if e != SLEEPY else theme.MUTED
        # Left
        tft.hline(14, 60, 28, wc)
        tft.hline(16, 66, 26, wc)
        tft.hline(18, 72, 24, wc)
        # Right
        tft.hline(86, 60, 28, wc)
        tft.hline(86, 66, 26, wc)
        tft.hline(86, 72, 24, wc)


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
