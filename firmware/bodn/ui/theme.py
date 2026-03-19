# bodn/ui/theme.py — colours and layout constants


class Theme:
    """Colour palette and layout metrics for the Bodn UI.

    Takes an rgb_fn (ST7735.rgb) so this module has no hardware imports
    and can be tested on the host.
    """

    def __init__(self, width, height, rgb_fn):
        self.width = width
        self.height = height

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
        self.MUTED = rgb_fn(80, 80, 80)

        # One colour per button (RGB565)
        self.BTN_565 = [
            self.RED, self.GREEN, self.BLUE, self.YELLOW,
            self.CYAN, self.MAGENTA, self.ORANGE, self.PURPLE,
        ]
        # Same in RGB tuples (for NeoPixel)
        self.BTN_RGB = [
            (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0),
            (0, 255, 255), (255, 0, 255), (255, 128, 0), (128, 0, 255),
        ]
        self.BTN_NAMES = ["Red", "Grn", "Blu", "Yel", "Cyn", "Mag", "Org", "Pur"]

        # Layout metrics
        self.FONT_W = 8
        self.FONT_H = 8
        self.font_scale = 2 if width < 200 else 3
        self.HEADER_Y = 3
        self.CONTENT_Y = 16
        self.CENTER_X = width // 2
        self.CENTER_Y = height // 2
