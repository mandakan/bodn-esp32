# bodn/ui/theme.py — colours and layout constants

from bodn.i18n import t


class Theme:
    """Colour palette and layout metrics for the Bodn UI.

    Takes an rgb_fn (ST7735.rgb) so this module has no hardware imports
    and can be tested on the host.
    """

    def __init__(self, width, height, rgb_fn):
        self.width = width
        self.height = height
        self.rgb = rgb_fn

        # Semantic colours (RGB565, byte-swapped)
        self.BLACK = rgb_fn(0, 0, 0)
        self.WHITE = rgb_fn(255, 255, 255)
        self.RED = rgb_fn(255, 0, 0)
        self.GREEN = rgb_fn(0, 255, 0)
        self.BLUE = rgb_fn(0, 0, 255)
        self.YELLOW = rgb_fn(255, 255, 0)
        self.CYAN = rgb_fn(0, 255, 255)
        self.MAGENTA = rgb_fn(255, 0, 255)
        self.ORANGE = rgb_fn(255, 128, 0)
        self.PURPLE = rgb_fn(128, 0, 255)
        self.AMBER = rgb_fn(255, 191, 0)
        self.MUTED = rgb_fn(160, 160, 160)  # readable from angles
        self.DIM = rgb_fn(80, 80, 80)  # subtle indicators only

        # One colour per mini button — matches physical cap colours
        # (config.BUTTON_COLORS: green, blue, white, yellow, red, black, green, blue)
        self.BTN_RGB = [
            (0, 200, 0),  # 0: green
            (0, 100, 255),  # 1: blue
            (255, 255, 255),  # 2: white
            (255, 220, 0),  # 3: yellow
            (255, 0, 0),  # 4: red
            (0, 160, 140),  # 5: black cap → dark teal (visible on dark bg)
            (0, 220, 120),  # 6: green₂ → teal-green (distinct from 0)
            (80, 160, 255),  # 7: blue₂ → sky blue (distinct from 1)
        ]
        self.BTN_565 = [rgb_fn(r, g, b) for r, g, b in self.BTN_RGB]

        # One colour per arcade button — matches physical cap colours
        # (config.ARCADE_COLORS: green, blue, white, yellow, red)
        self.ARC_RGB = [
            (60, 220, 60),  # 0: green
            (60, 100, 255),  # 1: blue
            (255, 255, 255),  # 2: white
            (255, 220, 60),  # 3: yellow
            (255, 60, 60),  # 4: red
        ]
        self.ARC_565 = [rgb_fn(r, g, b) for r, g, b in self.ARC_RGB]
        # Layout metrics
        self.FONT_W = 8
        self.FONT_H = 8
        self.font_scale = 2 if width < 200 else 3
        self.HEADER_Y = 3
        self.CONTENT_Y = 16
        self.CENTER_X = width // 2
        self.CENTER_Y = height // 2

    @property
    def BTN_NAMES(self):
        """Button colour labels — translated on access so language switches take effect."""
        return [
            t("btn_green"),
            t("btn_blue"),
            t("btn_white"),
            t("btn_yellow"),
            t("btn_red"),
            t("btn_teal"),
            t("btn_mint"),
            t("btn_sky"),
        ]
