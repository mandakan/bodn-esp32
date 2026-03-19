# bodn/ui/home.py — home screen with mode selection

from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.icons import MODE_ICONS
from bodn.ui.widgets import draw_icon, draw_centered

NAV = config.ENC_NAV


class HomeScreen(Screen):
    """Displays available modes and lets the user select one.

    Nav encoder (index 0) rotation cycles through modes.
    Nav encoder button or any play button enters the selected mode.
    """

    def __init__(self, mode_screens, session_mgr, order=None):
        self._mode_screens = mode_screens
        self._session_mgr = session_mgr
        self._names = order if order else list(mode_screens.keys())
        self._index = 0
        self._manager = None
        self._error = None
        self._error_mode = None

    def enter(self, manager):
        self._manager = manager

    def update(self, inp, frame):
        if not self._names:
            return

        # Nav encoder rotation cycles modes (one step per detent, circular)
        delta = inp.enc_delta[NAV]
        if delta != 0:
            step = 1 if delta > 0 else -1
            self._index = (self._index + step) % len(self._names)
            # Re-center encoder so it never hits the clamp limits
            mid = self._manager.inp._encoders[NAV]._max // 2
            self._manager.inp._encoders[NAV].value = mid
            self._manager.inp._prev_enc_pos[NAV] = mid

        # Nav encoder button or any play button → enter mode
        if inp.any_btn_pressed() or inp.enc_btn_pressed[NAV]:
            name = self._names[self._index]
            factory = self._mode_screens[name]
            try:
                screen = factory()
                self._session_mgr.try_wake(name)
                self._manager.push(screen)
            except Exception as e:
                self._error = str(e)
                self._error_mode = name

    def render(self, tft, theme, frame):
        tft.fill(theme.BLACK)

        # Show error on screen if a mode failed to load
        if self._error:
            tft.text("ERR: " + self._error_mode, 4, 4, theme.RED)
            # Word-wrap error message
            msg = self._error
            y = 20
            while msg and y < theme.height - 16:
                tft.text(msg[:theme.width // 8], 4, y, theme.WHITE)
                msg = msg[theme.width // 8:]
                y += 12
            tft.text("press to clear", 4, theme.height - 12, theme.MUTED)
            if self._manager and self._manager.inp.any_btn_pressed():
                self._error = None
            return

        if not self._names:
            draw_centered(tft, "No modes", theme.CENTER_Y, theme.MUTED, theme.width)
            return

        name = self._names[self._index]
        landscape = theme.width > theme.height

        if landscape:
            self._render_landscape(tft, theme, frame, name)
        else:
            self._render_portrait(tft, theme, frame, name)

    def _render_landscape(self, tft, theme, frame, name):
        """Landscape layout: centered, icon above mode name."""
        w = theme.width
        h = theme.height

        # Title — centered at top
        draw_centered(tft, "~ Bodn ~", 8, theme.WHITE, w, scale=2)

        # Icon — centered
        icon_data = MODE_ICONS.get(name)
        icon_scale = 4
        icon_size = 16 * icon_scale
        if icon_data:
            ix = (w - icon_size) // 2
            iy = 40
            draw_icon(tft, icon_data, ix, iy, 16, 16, theme.CYAN, scale=icon_scale)

        # Mode name — centered below icon
        name_y = 40 + icon_size + 12
        draw_centered(tft, name.upper(), name_y, theme.CYAN, w, scale=2)

        # Arrow hints
        n = len(self._names)
        if n > 1:
            draw_centered(tft, "< turn to browse >", name_y + 24, theme.MUTED, w)

        # Sessions remaining — bottom center
        remaining = self._session_mgr.sessions_remaining
        color = theme.GREEN if remaining > 0 else theme.RED
        draw_centered(tft, "{} plays left".format(remaining), h - 20, color, w)

    def _render_portrait(self, tft, theme, frame, name):
        """Portrait layout: icon centered, stacked vertically."""
        draw_centered(tft, "~ Bodn ~", theme.HEADER_Y, theme.WHITE, theme.width)

        icon_data = MODE_ICONS.get(name)
        if icon_data:
            icon_scale = 3
            icon_size = 16 * icon_scale
            ix = (theme.width - icon_size) // 2
            iy = theme.CENTER_Y - icon_size // 2 - 8
            draw_icon(tft, icon_data, ix, iy, 16, 16, theme.CYAN, scale=icon_scale)

        draw_centered(tft, name.upper(), theme.CENTER_Y + 24, theme.WHITE, theme.width)

        n = len(self._names)
        if n > 1:
            tft.text("<", 2, theme.CENTER_Y - 4, theme.MUTED)
            tft.text(">", theme.width - 10, theme.CENTER_Y - 4, theme.MUTED)

        remaining = self._session_mgr.sessions_remaining
        color = theme.GREEN if remaining > 0 else theme.RED
        tft.text("{} plays left".format(remaining), 16, theme.height - 16, color)
