# bodn/ui/nfc_provision.py — NFC card set viewer and provisioning screen
#
# Shows available NFC card sets loaded from /sd/nfc/.
# Actual tag scanning is stubbed until PN532 hardware is available (#121).

from micropython import const
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered, make_label_sprite, blit_sprite
from bodn.i18n import t

NAV = const(0)


class NFCProvisionScreen(Screen):
    """NFC card provisioning screen.

    Scrollable list of available card sets.  Selecting one shows card
    count and dimensions.  Tag writing is stubbed until the PN532
    hardware reader is wired up (issue #121).
    """

    def __init__(self, settings):
        self._settings = settings
        self._index = 0
        self._manager = None
        self._dirty = True
        self._full_clear = True
        self._sets = []  # list of (mode, card_count, dims) tuples
        self._state = "menu"  # "menu" | "detail"
        self._title_sprite = None

    def enter(self, manager):
        self._manager = manager
        self._dirty = True
        self._full_clear = True
        self._index = 0
        self._state = "menu"
        self._title_sprite = make_label_sprite(t("settings_nfc"), 0xFFFF, scale=2)
        self._load_sets()

    def _load_sets(self):
        try:
            from bodn.nfc import list_card_sets, load_card_set

            self._sets = []
            for mode in list_card_sets():
                cs = load_card_set(mode)
                if cs:
                    cards = cs.get("cards", [])
                    dims = cs.get("dimensions", [])
                    self._sets.append((mode, len(cards), ", ".join(dims)))
        except Exception:
            self._sets = []

    def needs_redraw(self):
        return self._dirty

    def update(self, inp, frame):
        if self._state == "menu":
            delta = inp.enc_delta[NAV]
            if delta != 0:
                n = len(self._sets) + 1  # +1 for "Back"
                step = 1 if delta > 0 else -1
                self._index = (self._index + step) % n
                self._dirty = True

            if inp.enc_btn_pressed[NAV] or inp.any_btn_pressed():
                if self._index == len(self._sets):
                    self._manager.pop()
                elif self._sets:
                    self._state = "detail"
                    self._dirty = True
                    self._full_clear = True

        elif self._state == "detail":
            if inp.enc_btn_pressed[NAV] or inp.any_btn_pressed():
                self._state = "menu"
                self._dirty = True
                self._full_clear = True

    def render(self, tft, theme, frame):
        self._dirty = False
        w = theme.width
        h = theme.height

        if self._full_clear:
            tft.fill(theme.BLACK)
            self._full_clear = False

        if self._state == "menu":
            self._render_menu(tft, theme, w, h)
        elif self._state == "detail":
            self._render_detail(tft, theme, w, h)

    def _render_menu(self, tft, theme, w, h):
        # Title
        if self._title_sprite:
            _, tw, _ = self._title_sprite
            blit_sprite(tft, self._title_sprite, (w - tw) // 2, 8)

        title_h = 28
        row_h = 20
        y0 = title_h + 4
        available_h = h - y0 - 4
        visible = available_h // row_h

        n = len(self._sets) + 1  # +1 for back
        half = visible // 2
        scroll = max(0, min(self._index - half, n - visible))

        for vi in range(visible):
            idx = scroll + vi
            if idx >= n:
                break
            y = y0 + vi * row_h
            selected = idx == self._index

            # Clear row
            bg = theme.DIM if selected else theme.BLACK
            tft.fill_rect(0, y, w, row_h, bg)

            if idx < len(self._sets):
                mode, count, dims = self._sets[idx]
                label = "{} ({})".format(mode, count)
            else:
                label = t("settings_back")

            tft.text(label, 8, y + 6, theme.WHITE if selected else theme.MUTED)

    def _render_detail(self, tft, theme, w, h):
        if self._index >= len(self._sets):
            return
        mode, count, dims = self._sets[self._index]

        tft.fill(theme.BLACK)
        draw_centered(tft, mode.upper(), 30, theme.WHITE, w)
        draw_centered(tft, "{} cards".format(count), 50, theme.MUTED, w)
        if dims:
            draw_centered(tft, dims, 66, theme.MUTED, w)

        # NFC hardware status
        y_msg = h // 2
        try:
            from bodn.nfc import NFCReader

            reader = NFCReader()
            if reader.available():
                draw_centered(tft, "NFC ready", y_msg, theme.GREEN, w)
            else:
                draw_centered(tft, "No NFC reader", y_msg, theme.MUTED, w)
                draw_centered(tft, "See issue #121", y_msg + 14, theme.MUTED, w)
        except Exception:
            draw_centered(tft, "NFC not available", y_msg, theme.MUTED, w)

        draw_centered(tft, "Press to go back", h - 20, theme.MUTED, w)
