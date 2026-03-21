# bodn/ui/settings.py — parent-facing settings screen

from micropython import const
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered
from bodn.i18n import t, get_language, set_language, available

NAV = const(0)  # config.ENC_NAV

# Setting definitions: (key, label_key, type)
# type: "bool" = toggle, "action" = triggers an action, "lang" = language cycler
_ITEMS = [
    ("sessions_enabled", "settings_sessions", "bool"),
    ("sleep_timeout_s", "settings_sleep", "cycle"),
    ("wifi", "settings_wifi", "bool"),
    ("leds", "settings_leds", "bool"),
    ("language", "pause_lang", "lang"),
    ("debug_input", "settings_debug", "bool"),
    ("debug_perf", "settings_perf", "bool"),
    ("standby", "settings_standby", "action"),
    ("diag", "settings_diag", "action"),
    ("back", "settings_back", "action"),
]

_SLEEP_OPTIONS = [0, 60, 120, 300, 600]


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
        if key == "sleep_timeout_s":
            val = self._settings.get("sleep_timeout_s", 300)
            if val == 0:
                return t("off")
            return t("sleep_min", val // 60)
        if key in ("debug_input", "debug_perf", "sessions_enabled"):
            return self._settings.get(key, key == "sessions_enabled")
        return False

    def _activate(self, key):
        if key == "back":
            if self._manager:
                self._manager.pop()
            return
        if key == "diag":
            if self._manager:
                from bodn.ui.diag import DiagScreen

                self._manager.push(DiagScreen())
            return
        if key == "standby":
            self._settings["_sleep_now"] = True
            return
        if key == "sleep_timeout_s":
            cur = self._settings.get("sleep_timeout_s", 300)
            idx = 0
            for i in range(len(_SLEEP_OPTIONS)):
                if _SLEEP_OPTIONS[i] == cur:
                    idx = i
                    break
            self._settings["sleep_timeout_s"] = _SLEEP_OPTIONS[
                (idx + 1) % len(_SLEEP_OPTIONS)
            ]
            try:
                from bodn.storage import save_settings

                save_settings(self._settings)
            except Exception:
                pass
            self._dirty = True
            return
        if key == "language":
            langs = available()
            cur = get_language()
            idx = 0
            for i in range(len(langs)):
                if langs[i] == cur:
                    idx = i
                    break
            new_lang = langs[(idx + 1) % len(langs)]
            set_language(new_lang)
            self._settings["language"] = new_lang
            try:
                from bodn.storage import save_settings

                save_settings(self._settings)
            except Exception:
                pass
            self._dirty = True
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
            self._settings["sessions_enabled"] = not self._settings.get(
                "sessions_enabled", True
            )
        elif key == "debug_input":
            self._settings["debug_input"] = not self._settings.get("debug_input", False)
        elif key == "debug_perf":
            val = not self._settings.get("debug_perf", False)
            self._settings["debug_perf"] = val
            if self._manager:
                self._manager.debug_perf = val
                print("debug_perf={}".format(val))
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
        draw_centered(tft, t("settings_title"), 8, theme.WHITE, w, scale=2)

        # Menu items
        y_start = 40 if landscape else 30
        row_h = 24 if landscape else 20

        for i, (key, label_key, item_type) in enumerate(_ITEMS):
            y = y_start + i * row_h
            selected = i == self._index

            # Highlight bar for selected item
            if selected:
                tft.fill_rect(4, y - 2, w - 8, row_h - 2, theme.MUTED)

            # Label
            color = theme.WHITE if selected else theme.MUTED
            if item_type == "lang":
                label = t(label_key, get_language().upper())
            else:
                label = t(label_key)
            tft.text(label, 12, y + 2, color)

            # Value indicator
            if item_type == "bool":
                value = self._get_value(key)
                if value:
                    tft.fill_rect(w - 40, y, 28, row_h - 6, theme.GREEN)
                    tft.text(t("on"), w - 36, y + 2, theme.BLACK)
                else:
                    tft.fill_rect(w - 40, y, 28, row_h - 6, theme.RED)
                    tft.text(t("off"), w - 38, y + 2, theme.BLACK)
            elif item_type == "cycle":
                val_str = str(self._get_value(key))
                tx = w - 8 - len(val_str) * 8
                tft.text(val_str, tx, y + 2, theme.WHITE if selected else theme.MUTED)
