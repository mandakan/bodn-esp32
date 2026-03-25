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
    ("encoder_sensitivity", "settings_encoder", "cycle"),
    ("tz_offset", "settings_tz", "cycle"),
    ("audio_enabled", "settings_audio", "bool"),
    ("volume", "settings_volume", "cycle"),
    ("wifi", "settings_wifi", "bool"),
    ("leds", "settings_leds", "bool"),
    ("language", "pause_lang", "lang"),
    ("debug_input", "settings_debug", "bool"),
    ("debug_perf", "settings_perf", "bool"),
    ("admin_url", "settings_admin", "action"),
    ("standby", "settings_standby", "action"),
    ("diag", "settings_diag", "action"),
    ("back", "settings_back", "action"),
]

_SLEEP_OPTIONS = [0, 60, 120, 300, 600]
_VOLUME_OPTIONS = [10, 25, 50, 75, 100]
_TZ_OPTIONS = list(range(-12, 15))  # UTC-12 .. UTC+14


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
        if key == "encoder_sensitivity":
            val = self._settings.get("encoder_sensitivity", config.ENCODER_SENS_DEFAULT)
            idx = 0
            for i in range(len(config.ENCODER_SENS_OPTIONS)):
                if config.ENCODER_SENS_OPTIONS[i] == val:
                    idx = i
                    break
            return t("sens_" + config.ENCODER_SENS_LABELS[idx])
        if key == "volume":
            return "{}%".format(self._settings.get("volume", 30))
        if key == "tz_offset":
            off = self._settings.get("tz_offset", 1)
            return "UTC{:+d}".format(off)
        if key in ("debug_input", "debug_perf", "sessions_enabled", "audio_enabled"):
            return self._settings.get(key, key in ("sessions_enabled", "audio_enabled"))
        return False

    def _activate(self, key):
        if key == "back":
            if self._manager:
                self._manager.pop()
            return
        if key == "admin_url":
            if self._manager:
                from bodn.ui.admin_qr import AdminQRScreen

                self._manager.push(AdminQRScreen(self._settings))
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
        if key == "encoder_sensitivity":
            opts = config.ENCODER_SENS_OPTIONS
            cur = self._settings.get("encoder_sensitivity", config.ENCODER_SENS_DEFAULT)
            idx = 0
            for i in range(len(opts)):
                if opts[i] == cur:
                    idx = i
                    break
            self._settings["encoder_sensitivity"] = opts[(idx + 1) % len(opts)]
            try:
                from bodn.storage import save_settings

                save_settings(self._settings)
            except Exception:
                pass
            self._dirty = True
            return
        if key == "volume":
            cur = self._settings.get("volume", 30)
            idx = 0
            for i in range(len(_VOLUME_OPTIONS)):
                if _VOLUME_OPTIONS[i] == cur:
                    idx = i
                    break
            self._settings["volume"] = _VOLUME_OPTIONS[(idx + 1) % len(_VOLUME_OPTIONS)]
            try:
                from bodn.storage import save_settings

                save_settings(self._settings)
            except Exception:
                pass
            self._dirty = True
            return
        if key == "tz_offset":
            cur = self._settings.get("tz_offset", 1)
            idx = 13  # default index for UTC+1
            for i in range(len(_TZ_OPTIONS)):
                if _TZ_OPTIONS[i] == cur:
                    idx = i
                    break
            self._settings["tz_offset"] = _TZ_OPTIONS[(idx + 1) % len(_TZ_OPTIONS)]
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
        elif key == "audio_enabled":
            self._settings["audio_enabled"] = not self._settings.get(
                "audio_enabled", True
            )
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
        title_h = 28 if landscape else 24
        draw_centered(tft, t("settings_title"), 8, theme.WHITE, w, scale=2)

        # Menu items — scroll to keep selection centered
        row_h = 24 if landscape else 20
        menu_h = h - title_h - 4  # available height for menu items
        visible = menu_h // row_h  # how many items fit on screen

        # Calculate scroll offset to center the selected item
        n = len(_ITEMS)
        half = visible // 2
        scroll = self._index - half
        scroll = max(0, min(scroll, n - visible))

        for i in range(scroll, min(scroll + visible, n)):
            key, label_key, item_type = _ITEMS[i]
            y = title_h + (i - scroll) * row_h
            selected = i == self._index

            # Highlight bar for selected item
            if selected:
                tft.fill_rect(4, y - 2, w - 8, row_h - 2, theme.DIM)

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

        # Scroll indicators
        if scroll > 0:
            draw_centered(tft, "^", title_h - 10, theme.MUTED, w)
        if scroll + visible < n:
            draw_centered(tft, "v", h - 12, theme.MUTED, w)
