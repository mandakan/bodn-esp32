# bodn/ui/garden_secondary.py — secondary display content for Garden of Life
#
# Tier 1: ambient mood — big sun when garden thrives, clouds when shrinking,
#         rain when empty.
# Tier 2+: target shape + generation counter (future).

from bodn.ui.screen import Screen
from bodn.ui.secondary import CONTENT_SIZE
from bodn.ui.widgets import draw_centered
from bodn.ui.catface import _fill_circle


class GardenSecondary(Screen):
    """Ambient mood display for the Garden of Life.

    Shows a simple weather scene reflecting garden health:
    - Sun (population growing or stable)
    - Clouds (population shrinking)
    - Rain (garden empty)
    """

    def __init__(self):
        self._population = 0
        self._generation = 0
        self._prev_population = 0
        self._dirty = True

    def enter(self, display):
        self._dirty = True

    def set_population(self, pop, gen):
        """Called by GardenScreen after each generation step."""
        if pop != self._population or gen != self._generation:
            self._prev_population = self._population
            self._population = pop
            self._generation = gen
            self._dirty = True

    def needs_redraw(self):
        return self._dirty

    def render(self, tft, theme, frame):
        self._dirty = False
        w = CONTENT_SIZE
        tft.fill_rect(0, 0, w, w, theme.BLACK)

        pop = self._population

        if pop == 0:
            # Rain — empty garden
            self._draw_rain(tft, theme, frame)
        elif pop < self._prev_population:
            # Clouds — shrinking
            self._draw_clouds(tft, theme)
        else:
            # Sun — thriving
            self._draw_sun(tft, theme)

        # Generation counter
        gen_text = "Gen {}".format(self._generation)
        draw_centered(tft, gen_text, 108, theme.WHITE, w)

        # Population display
        pop_text = "{} cells".format(pop)
        draw_centered(tft, pop_text, 118, theme.MUTED, w)

    def _draw_sun(self, tft, theme):
        """Happy sun — garden is thriving."""
        cx, cy = 64, 48
        # Sun rays
        ray_color = tft.rgb(255, 200, 0)
        # Sun body
        _fill_circle(tft, cx, cy, 24, tft.rgb(255, 220, 0))
        _fill_circle(tft, cx, cy, 20, tft.rgb(255, 240, 50))

        # Simple rays as rectangles
        tft.fill_rect(cx - 2, cy - 38, 4, 10, ray_color)  # top
        tft.fill_rect(cx - 2, cy + 28, 4, 10, ray_color)  # bottom
        tft.fill_rect(cx - 38, cy - 2, 10, 4, ray_color)  # left
        tft.fill_rect(cx + 28, cy - 2, 10, 4, ray_color)  # right
        # Diagonals
        tft.fill_rect(cx + 20, cy - 26, 4, 8, ray_color)
        tft.fill_rect(cx - 24, cy - 26, 4, 8, ray_color)
        tft.fill_rect(cx + 20, cy + 18, 4, 8, ray_color)
        tft.fill_rect(cx - 24, cy + 18, 4, 8, ray_color)

        # Smiley face on sun
        eye_color = tft.rgb(80, 60, 0)
        tft.fill_rect(cx - 8, cy - 6, 4, 4, eye_color)
        tft.fill_rect(cx + 4, cy - 6, 4, 4, eye_color)
        # Smile
        for dx in range(12):
            dy = (dx - 6) * (dx - 6) // 10
            tft.fill_rect(cx - 6 + dx, cy + 6 + dy, 2, 2, eye_color)

    def _draw_clouds(self, tft, theme):
        """Clouds — garden is shrinking."""
        cloud_color = tft.rgb(160, 160, 180)
        dark_cloud = tft.rgb(120, 120, 140)

        # Cloud 1 (bigger, foreground)
        _fill_circle(tft, 50, 45, 18, cloud_color)
        _fill_circle(tft, 70, 40, 22, cloud_color)
        _fill_circle(tft, 90, 45, 16, cloud_color)
        tft.fill_rect(32, 45, 76, 20, cloud_color)

        # Cloud 2 (smaller, background)
        _fill_circle(tft, 30, 70, 12, dark_cloud)
        _fill_circle(tft, 48, 66, 16, dark_cloud)
        _fill_circle(tft, 64, 70, 10, dark_cloud)
        tft.fill_rect(18, 70, 56, 14, dark_cloud)

    def _draw_rain(self, tft, theme, frame):
        """Rain — garden is empty."""
        cloud_color = tft.rgb(100, 100, 120)

        # Dark cloud
        _fill_circle(tft, 50, 30, 16, cloud_color)
        _fill_circle(tft, 70, 26, 20, cloud_color)
        _fill_circle(tft, 90, 30, 14, cloud_color)
        tft.fill_rect(34, 30, 70, 16, cloud_color)

        # Rain drops (animated with frame)
        drop_color = tft.rgb(80, 120, 255)
        for i in range(8):
            x = 36 + i * 10
            y_base = 54 + ((frame + i * 7) * 3) % 40
            tft.fill_rect(x, y_base, 2, 6, drop_color)

        # "Plant again!" prompt
        draw_centered(tft, "~", 88, theme.CYAN, CONTENT_SIZE, scale=2)
