# bodn/ui/mystery_secondary.py — Recipe book for Mystery Box
#
# 128x128 content zone with two stacked grids:
#   Top:    1 x 8 single-cap tiles (one per button cap)
#   Bottom: 2 x 4 magic-pair tiles (one per COLOR_ALCHEMY_MAGIC entry)
#
# Each tile is a coloured square once unlocked, otherwise a dim "?" placeholder.
# Magic tiles also show two tiny dots in their corner indicating the cap pair
# that produced them, so the kid has a hint for what to try next.

from bodn.ui.screen import Screen
from bodn.ui.secondary import CONTENT_SIZE
from bodn.mystery_rules import BASE_COLORS, COLOR_ALCHEMY_MAGIC

# Layout
_PAD = 4
_TOP_Y = 6
_TOP_H = 22
_GAP = 8
_BOT_Y = _TOP_Y + _TOP_H + _GAP  # 40
_BOT_H = CONTENT_SIZE - _BOT_Y - _PAD  # ~84
_FOOTER_H = 12

_MAGIC_KEYS = sorted(COLOR_ALCHEMY_MAGIC.keys())  # stable order


class MysterySecondary(Screen):
    """Discovery grid for Mystery Box on the 128x128 secondary display."""

    def __init__(self):
        self._singles = set()
        self._magic = set()
        self._highlight = None  # ('single', i) or ('magic', (a, b)) — pulses
        self._highlight_ticks = 0
        self._dirty = True

    # -- API used by MysteryScreen --

    def set_state(self, singles, magic, highlight=None):
        """Push the current discovery sets and an optional new-unlock highlight."""
        if singles != self._singles or magic != self._magic:
            self._singles = set(singles)
            self._magic = set(magic)
            self._dirty = True
        if highlight is not None and highlight != self._highlight:
            self._highlight = highlight
            self._highlight_ticks = 0
            self._dirty = True

    # -- Screen lifecycle --

    def enter(self, display):
        self._dirty = True

    def needs_redraw(self):
        if self._dirty:
            return True
        if self._highlight is not None:
            self._highlight_ticks += 1
            # Pulse for ~30 ticks (~1.5 s on the secondary tick) then stop.
            if self._highlight_ticks > 30:
                self._highlight = None
                self._dirty = True
                return True
            return True  # repaint highlight cell each tick
        return False

    def render(self, tft, theme, frame):
        self._dirty = False
        w = CONTENT_SIZE
        tft.fill_rect(0, 0, w, w, theme.BLACK)
        self._draw_singles(tft, theme, frame)
        self._draw_magic(tft, theme, frame)
        self._draw_footer(tft, theme)

    # -- Internals --

    def _draw_singles(self, tft, theme, frame):
        n = len(BASE_COLORS)
        cell_w = (CONTENT_SIZE - 2 * _PAD) // n
        for i in range(n):
            x = _PAD + i * cell_w
            self._draw_tile(
                tft,
                theme,
                x,
                _TOP_Y,
                cell_w - 1,
                _TOP_H,
                BASE_COLORS[i] if i in self._singles else None,
                self._highlight == ("single", i),
                frame,
            )

    def _draw_magic(self, tft, theme, frame):
        # 2 rows x 4 cols
        cols = 4
        rows = 2
        cell_w = (CONTENT_SIZE - 2 * _PAD) // cols
        cell_h = (_BOT_H - _FOOTER_H) // rows
        for idx, pair in enumerate(_MAGIC_KEYS):
            r = idx // cols
            c = idx % cols
            x = _PAD + c * cell_w
            y = _BOT_Y + r * cell_h
            colour = COLOR_ALCHEMY_MAGIC[pair] if pair in self._magic else None
            self._draw_tile(
                tft,
                theme,
                x,
                y,
                cell_w - 2,
                cell_h - 2,
                colour,
                self._highlight == ("magic", pair),
                frame,
            )
            # Hint dots: two small swatches showing which caps make this combo,
            # visible whether or not the tile is unlocked. Helps the kid plan.
            self._draw_pair_hint(tft, theme, x + 2, y + cell_h - 6, pair)

    def _draw_tile(self, tft, theme, x, y, w, h, colour, highlight, frame):
        if colour is None:
            tft.rect(x, y, w, h, theme.DIM)
            # Centred "?"
            cx = x + w // 2 - 4
            cy = y + h // 2 - 4
            tft.text("?", cx, cy, theme.MUTED)
            return
        r, g, b = colour
        if highlight:
            # Pulse brighter/darker around the base colour.
            phase = (frame * 6) & 0xFF
            v = phase if phase < 128 else 255 - phase
            scale_q = 160 + (v >> 1)  # 160-224
            r = (r * scale_q) >> 8
            g = (g * scale_q) >> 8
            b = (b * scale_q) >> 8
        tft.fill_rect(x, y, w, h, tft.rgb(r, g, b))
        if highlight:
            tft.rect(x - 1, y - 1, w + 2, h + 2, theme.WHITE)
        else:
            tft.rect(x, y, w, h, theme.MUTED)

    def _draw_pair_hint(self, tft, theme, x, y, pair):
        a, b = pair
        ar, ag, ab = BASE_COLORS[a]
        br, bg, bb = BASE_COLORS[b]
        tft.fill_rect(x, y, 4, 4, tft.rgb(ar, ag, ab))
        tft.fill_rect(x + 5, y, 4, 4, tft.rgb(br, bg, bb))

    def _draw_footer(self, tft, theme):
        found = len(self._singles) + len(self._magic)
        total = len(BASE_COLORS) + len(COLOR_ALCHEMY_MAGIC)
        label = "{}/{}".format(found, total)
        # Right-aligned in the footer.
        x = CONTENT_SIZE - _PAD - len(label) * 8
        y = CONTENT_SIZE - _FOOTER_H + 2
        colour = theme.YELLOW if found == total else theme.MUTED
        tft.text(label, x, y, colour)
