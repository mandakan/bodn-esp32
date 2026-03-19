# bodn/ui/settings.py — parent-facing settings screen

from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered

NAV = config.ENC_NAV

# Setting definitions: (key, label, type)
# type: "bool" = toggle, "action" = triggers an action
_ITEMS = [
    ("sessions_enabled", "Sessions", "bool"),
    ("wifi", "WiFi", "bool"),
    ("leds", "LEDs", "bool"),
    ("debug_input", "Debug log", "bool"),
    ("back", "< Back", "action"),
]


class SettingsScreen(Screen):
    """Simple settings menu with toggleable options.

    Nav encoder rotates through items.
    Nav encoder button = confirm (toggle or activate).
    Consistent with all other screens: encoder button = "do the thing".
    """

    def __init__(self, settings, np, wifi_ctrl):
        self._settings = settings
        self._np = np
        self._wifi_ctrl = wifi_ctrl
        self._index = 0
        self._manager = None
        self._dirty = True
        self._leds_on = True

    def enter(self, manager):
        self._manager = manager
        self._dirty = True

    def needs_redraw(self):
        return self._dirty

    def _get_value(self, key):
        if key == "wifi":
            return self._wifi_ctrl.is_active()
        if key == "leds":
            return self._leds_on
        if key in ("debug_input", "sessions_enabled"):
            return self._settings.get(key, key == "sessions_enabled")
        return False

    def _activate(self, key):
        if key == "back":
            if self._manager:
                self._manager.pop()
            return
        if key == "wifi":
            if self._wifi_ctrl.is_active():
                self._wifi_ctrl.disable()
            else:
                self._wifi_ctrl.enable()
        elif key == "leds":
            self._leds_on = not self._leds_on
            if not self._leds_on:
                for i in range(config.NEOPIXEL_COUNT):
                    self._np[i] = (0, 0, 0)
                self._np.write()
        elif key == "sessions_enabled":
            self._settings["sessions_enabled"] = not self._settings.get("sessions_enabled", True)
        elif key == "debug_input":
            self._settings["debug_input"] = not self._settings.get("debug_input", False)
        self._dirty = True

    def update(self, inp, frame):
        # Nav encoder rotation scrolls through items
        delta = inp.enc_delta[NAV]
        if delta != 0:
            step = 1 if delta > 0 else -1
            self._index = (self._index + step) % len(_ITEMS)
            mid = self._manager.inp._encoders[NAV]._max // 2
            self._manager.inp._encoders[NAV].value = mid
            self._manager.inp._prev_enc_pos[NAV] = mid
            self._dirty = True

        # Nav encoder button or any play button → activate selected item
        if inp.enc_btn_pressed[NAV] or inp.any_btn_pressed():
            key = _ITEMS[self._index][0]
            self._activate(key)

    @property
    def leds_enabled(self):
        return self._leds_on

    def render(self, tft, theme, frame):
        self._dirty = False
        tft.fill(theme.BLACK)

        w = theme.width
        h = theme.height
        landscape = w > h

        # Title
        draw_centered(tft, "Settings", 8, theme.WHITE, w, scale=2)

        # Menu items
        y_start = 40 if landscape else 30
        row_h = 24 if landscape else 20

        for i, (key, label, item_type) in enumerate(_ITEMS):
            y = y_start + i * row_h
            selected = i == self._index

            # Highlight bar for selected item
            if selected:
                tft.fill_rect(4, y - 2, w - 8, row_h - 2, theme.MUTED)

            # Label
            color = theme.WHITE if selected else theme.MUTED
            tft.text(label, 12, y + 2, color)

            # Value indicator (only for bool items)
            if item_type == "bool":
                value = self._get_value(key)
                if value:
                    tft.fill_rect(w - 40, y, 28, row_h - 6, theme.GREEN)
                    tft.text("ON", w - 36, y + 2, theme.BLACK)
                else:
                    tft.fill_rect(w - 40, y, 28, row_h - 6, theme.RED)
                    tft.text("OFF", w - 38, y + 2, theme.BLACK)
