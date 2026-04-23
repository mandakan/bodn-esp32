# bodn/ui/settings.py — parent-facing settings screen

from micropython import const
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered, draw_label, make_label_sprite, blit_sprite
from bodn.i18n import t, get_language, set_language, available
from bodn.neo import neo

NAV = const(0)  # config.ENC_NAV
ADJ = const(1)  # config.ENC_A — value adjustment encoder

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
    ("nfc_provision", "settings_nfc", "action"),
    ("icon_browser", "settings_icons", "action"),
    ("back", "settings_back", "action"),
]

_SLEEP_OPTIONS = [0, 60, 120, 300, 600]
_VOLUME_OPTIONS = [10, 25, 50, 75, 100]
_TZ_OPTIONS = list(range(-12, 15))  # UTC-12 .. UTC+14


class SettingsScreen(Screen):
    """Simple settings menu with toggleable options.

    Nav encoder rotates through items.
    Nav encoder button = confirm (toggle or activate).
    Adjustment encoder (ENC_A) changes the selected value directly.
    """

    def __init__(self, settings, wifi_ctrl):
        self._settings = settings
        self._wifi_ctrl = wifi_ctrl
        self._index = 0
        self._manager = None
        self._dirty = True
        self._leds_on = True

    def enter(self, manager):
        self._manager = manager
        self._dirty = True
        self._full_clear = True
        self._prev_index = -1
        self._prev_scroll = -1

        # Pre-render sprites for scaled / extended-char text
        theme = manager.theme
        self._title_sprite = make_label_sprite(
            t("settings_title"), theme.WHITE, scale=2
        )
        self._on_sprite = make_label_sprite(t("on"), theme.BLACK)
        self._off_sprite = make_label_sprite(t("off"), theme.BLACK)

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

    def _activate(self, key, step=1):
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
        if key == "nfc_provision":
            if self._manager:
                from bodn.ui.nfc_provision import NFCProvisionScreen

                self._manager.push(NFCProvisionScreen(self._settings))
            return
        if key == "icon_browser":
            if self._manager:
                from bodn.ui.icon_browser import IconBrowserScreen

                self._manager.push(IconBrowserScreen())
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
                (idx + step) % len(_SLEEP_OPTIONS)
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
            self._settings["encoder_sensitivity"] = opts[(idx + step) % len(opts)]
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
            self._settings["volume"] = _VOLUME_OPTIONS[
                (idx + step) % len(_VOLUME_OPTIONS)
            ]
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
            self._settings["tz_offset"] = _TZ_OPTIONS[(idx + step) % len(_TZ_OPTIONS)]
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
            new_lang = langs[(idx + step) % len(langs)]
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
                neo.all_off()
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

        # Adjustment encoder changes the value of the selected item
        adj_delta = inp.enc_delta[ADJ]
        if adj_delta != 0:
            key, _, item_type = _ITEMS[self._index]
            if item_type in ("cycle", "bool", "lang"):
                step = 1 if adj_delta > 0 else -1
                self._activate(key, step)

        # Nav encoder button or any play button → activate selected item
        if inp.enc_btn_pressed[NAV] or inp.any_btn_pressed():
            key = _ITEMS[self._index][0]
            self._activate(key)

    @property
    def leds_enabled(self):
        return self._leds_on

    def render(self, tft, theme, frame):
        self._dirty = False

        w = theme.width
        h = theme.height
        title_h = 28
        row_h = 24
        menu_h = h - title_h - 4
        visible = menu_h // row_h

        n = len(_ITEMS)
        half = visible // 2
        scroll = self._index - half
        scroll = max(0, min(scroll, n - visible))

        scroll_changed = scroll != self._prev_scroll

        if self._full_clear:
            self._full_clear = False
            tft.fill(theme.BLACK)
            # Title (cached sprite, blitted once)
            _, tw, _ = self._title_sprite
            blit_sprite(tft, self._title_sprite, (w - tw) // 2, 8)
            # Draw all visible rows
            for i in range(scroll, min(scroll + visible, n)):
                self._render_row(tft, theme, i, scroll, title_h, row_h, w)
        elif scroll_changed:
            # Scroll changed — redraw all visible rows (each row clears
            # its own background, so no full-screen fill needed).
            tft.reset_dirty()
            for i in range(scroll, min(scroll + visible, n)):
                self._render_row(tft, theme, i, scroll, title_h, row_h, w)
        else:
            # Only redraw the old and new selected rows
            old_idx = self._prev_index
            new_idx = self._index
            if old_idx != new_idx:
                if scroll <= old_idx < scroll + visible:
                    self._render_row(tft, theme, old_idx, scroll, title_h, row_h, w)
                if scroll <= new_idx < scroll + visible:
                    self._render_row(tft, theme, new_idx, scroll, title_h, row_h, w)
            else:
                # Value toggled on the same row
                self._render_row(tft, theme, new_idx, scroll, title_h, row_h, w)

        self._prev_index = self._index
        self._prev_scroll = scroll

        # Scroll indicators
        if scroll > 0:
            draw_centered(tft, "^", title_h - 10, theme.MUTED, w)
        if scroll + visible < n:
            draw_centered(tft, "v", h - 12, theme.MUTED, w)

    def _render_row(self, tft, theme, i, scroll, title_h, row_h, w):
        """Draw a single menu row, clearing its background first."""
        key, label_key, item_type = _ITEMS[i]
        y = title_h + (i - scroll) * row_h
        selected = i == self._index

        # Clear row background
        tft.fill_rect(0, y - 2, w, row_h, theme.BLACK)

        # Highlight bar for selected item
        if selected:
            tft.fill_rect(4, y - 2, w - 8, row_h - 2, theme.DIM)

        # Label
        color = theme.WHITE if selected else theme.MUTED
        if item_type == "lang":
            label = t(label_key, get_language().upper())
        else:
            label = t(label_key)
        draw_label(tft, label, 12, y + 2, color)

        # Value indicator
        if item_type == "bool":
            value = self._get_value(key)
            if value:
                tft.fill_rect(w - 40, y, 28, row_h - 6, theme.GREEN)
                blit_sprite(tft, self._on_sprite, w - 36, y + 2)
            else:
                tft.fill_rect(w - 40, y, 28, row_h - 6, theme.RED)
                blit_sprite(tft, self._off_sprite, w - 38, y + 2)
        elif item_type == "cycle":
            val_str = str(self._get_value(key))
            tx = w - 8 - len(val_str) * 8
            tft.text(val_str, tx, y + 2, theme.WHITE if selected else theme.MUTED)
