# bodn/ui/nfc_provision.py — NFC card set viewer and bulk provisioning screen
#
# Parent-facing admin screen for writing BODN NDEF data to NFC tags.
# Flow: select card set → scroll through cards → tap tag to write each one.
# Encoder scrolls cards (skip/redo), any button writes, NAV press goes back.

import time

from micropython import const
from bodn.ui.screen import Screen
from bodn.ui.widgets import (
    draw_centered,
    make_label_sprite,
    blit_sprite,
    load_emoji,
)
from bodn.i18n import t, capitalize

NAV = const(0)

# Write flow states
_IDLE = const(0)  # waiting for button press to start write
_WRITING = const(1)  # write in progress
_OK = const(2)  # write succeeded — show checkmark briefly
_FAIL = const(3)  # write failed — show error briefly

_RESULT_DISPLAY_MS = const(1200)  # how long to show OK/FAIL before advancing

# Emoji codepoint → name lookup (built from card set manifest)
_ICON_NAMES = {
    "1F431": "cat",
    "1F436": "dog",
    "1F430": "rabbit",
    "1F426": "bird",
    "1F41F": "fish",
    "1F434": "horse",
    "1F404": "cow",
    "1F438": "frog",
}


class NFCProvisionScreen(Screen):
    """NFC card provisioning screen.

    States:
      menu   — scrollable list of available card sets
      detail — card set overview (count, dims, NFC status)
      write  — guided bulk-write: one card at a time, tap tag to write
    """

    def __init__(self, settings):
        self._settings = settings
        self._index = 0
        self._manager = None
        self._dirty = True
        self._full_clear = True
        self._sets = []  # list of (mode, card_set_dict) tuples
        self._state = "menu"
        self._title_sprite = None
        # Write flow
        self._reader = None
        self._cards = []
        self._card_idx = 0
        self._write_state = _IDLE
        self._write_ms = 0
        self._written_count = 0
        self._cur_emoji = None  # cached (asset, w, h) for current card
        self._cur_emoji_icon = None  # codepoint of cached emoji

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
                    self._sets.append((mode, cs))
        except Exception:
            self._sets = []

    def _init_reader(self):
        if self._reader is None:
            try:
                from bodn.nfc import NFCReader

                self._reader = NFCReader()
            except Exception:
                self._reader = None

    def _load_card_emoji(self, card):
        """Load emoji for a card, caching to avoid reloads on redraw."""
        icon = card.get("icon")
        if icon == self._cur_emoji_icon:
            return self._cur_emoji
        self._cur_emoji_icon = icon
        self._cur_emoji = None
        if icon:
            name = _ICON_NAMES.get(icon) or card.get("label_en")
            if name:
                self._cur_emoji = load_emoji(name, 48)
        return self._cur_emoji

    def needs_redraw(self):
        return self._dirty

    def update(self, inp, frame):
        if self._state == "menu":
            self._update_menu(inp)
        elif self._state == "detail":
            self._update_detail(inp)
        elif self._state == "write":
            self._update_write(inp)

    def _any_press(self, inp):
        """Return True if any button (mini, arcade, or encoder) was pressed."""
        return (
            inp.enc_btn_pressed[NAV] or inp.any_btn_pressed() or inp.any_arc_pressed()
        )

    def _update_menu(self, inp):
        delta = inp.enc_delta[NAV]
        if delta != 0:
            n = len(self._sets) + 1  # +1 for "Back"
            step = 1 if delta > 0 else -1
            self._index = (self._index + step) % n
            self._dirty = True

        if self._any_press(inp):
            if self._index == len(self._sets):
                self._manager.pop()
            elif self._sets:
                self._state = "detail"
                self._dirty = True
                self._full_clear = True

    def _update_detail(self, inp):
        # Encoder long-press or second press → back to menu
        if inp.enc_btn_pressed[NAV]:
            self._state = "menu"
            self._dirty = True
            self._full_clear = True
            return

        if inp.any_btn_pressed() or inp.any_arc_pressed():
            # Enter write mode if NFC is available
            self._init_reader()
            if self._reader and self._reader.available():
                mode, cs = self._sets[self._index]
                self._cards = cs.get("cards", [])
                self._card_idx = 0
                self._write_state = _IDLE
                self._written_count = 0
                self._cur_emoji = None
                self._cur_emoji_icon = None
                self._state = "write"
                self._dirty = True
                self._full_clear = True

    def _update_write(self, inp):
        now = time.ticks_ms()

        # OK/FAIL display timer → advance to next card or back to idle
        if self._write_state in (_OK, _FAIL):
            if time.ticks_diff(now, self._write_ms) >= _RESULT_DISPLAY_MS:
                if self._write_state == _OK:
                    # Auto-advance to next card
                    if self._card_idx < len(self._cards) - 1:
                        self._card_idx += 1
                self._write_state = _IDLE
                self._dirty = True
                self._full_clear = True
            return

        # NAV press → back to detail
        if inp.enc_btn_pressed[NAV]:
            self._state = "detail"
            self._dirty = True
            self._full_clear = True
            return

        # Encoder scroll → skip/redo cards
        delta = inp.enc_delta[NAV]
        if delta != 0 and self._write_state == _IDLE:
            n = len(self._cards)
            step = 1 if delta > 0 else -1
            self._card_idx = max(0, min(self._card_idx + step, n - 1))
            self._dirty = True
            self._full_clear = True

        # Any button → write current card to tag
        if self._write_state == _IDLE:
            if inp.any_btn_pressed() or inp.any_arc_pressed():
                self._do_write()

    def _do_write(self):
        if not self._cards or self._card_idx >= len(self._cards):
            return
        card = self._cards[self._card_idx]
        mode, _ = self._sets[self._index]
        card_id = card.get("id", "")

        self._write_state = _WRITING
        self._dirty = True

        # Pause the background scan task while we hold the I2C bus for
        # the full detect→write sequence — otherwise a cooperative scan
        # can drop in between our NTAG writes and corrupt the transfer.
        from bodn.nfc import encode_tag_data, suspend_scan

        suspend_scan(True)
        try:
            data = encode_tag_data(mode, card_id)
            ok = self._reader.write(data)
            if ok:
                self._write_state = _OK
                self._written_count += 1
            else:
                print("NFC: write returned False for", card_id)
                self._write_state = _FAIL
        except Exception as e:
            print("NFC: write error:", e)
            self._write_state = _FAIL
        finally:
            suspend_scan(False)

        self._write_ms = time.ticks_ms()
        self._dirty = True
        self._full_clear = True

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

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
        elif self._state == "write":
            self._render_write(tft, theme, w, h)

    def _render_menu(self, tft, theme, w, h):
        if self._title_sprite:
            _, tw, _ = self._title_sprite
            blit_sprite(tft, self._title_sprite, (w - tw) // 2, 8)

        title_h = 28
        row_h = 20
        y0 = title_h + 4
        available_h = h - y0 - 4
        visible = available_h // row_h

        n = len(self._sets) + 1
        half = visible // 2
        scroll = max(0, min(self._index - half, n - visible))

        for vi in range(visible):
            idx = scroll + vi
            if idx >= n:
                break
            y = y0 + vi * row_h
            selected = idx == self._index

            bg = theme.DIM if selected else theme.BLACK
            tft.fill_rect(0, y, w, row_h, bg)

            if idx < len(self._sets):
                mode, cs = self._sets[idx]
                count = len(cs.get("cards", []))
                label = "{} ({})".format(mode, count)
            else:
                label = t("settings_back")

            tft.text(label, 8, y + 6, theme.WHITE if selected else theme.MUTED)

    def _render_detail(self, tft, theme, w, h):
        if self._index >= len(self._sets):
            return
        mode, cs = self._sets[self._index]
        cards = cs.get("cards", [])
        dims = cs.get("dimensions", [])

        draw_centered(tft, capitalize(mode), 30, theme.WHITE, w)
        draw_centered(tft, "{} cards".format(len(cards)), 50, theme.MUTED, w)
        if dims:
            draw_centered(tft, ", ".join(dims), 66, theme.MUTED, w)

        # NFC status
        y_msg = h // 2
        self._init_reader()
        if self._reader and self._reader.available():
            draw_centered(tft, t("nfc_ready"), y_msg, theme.GREEN, w)
            draw_centered(tft, t("nfc_press_write"), y_msg + 16, theme.MUTED, w)
        else:
            draw_centered(tft, t("nfc_no_reader"), y_msg, theme.MUTED, w)

        draw_centered(tft, t("nfc_nav_back"), h - 20, theme.MUTED, w)

    def _render_write(self, tft, theme, w, h):
        if not self._cards:
            return
        mode, _ = self._sets[self._index]
        card = self._cards[self._card_idx]
        card_id = card.get("id", "?")
        label = card.get("label_sv") or card.get("label_en") or card_id
        colour = card.get("colour", "")
        n = len(self._cards)

        # Header: mode + progress
        draw_centered(tft, capitalize(mode), 8, theme.MUTED, w)
        progress = "{}/{}".format(self._card_idx + 1, n)
        draw_centered(tft, progress, 22, theme.DIM, w)

        # Emoji icon — centered, large
        emoji = self._load_card_emoji(card)
        y_emoji = 40
        if emoji:
            try:
                import _draw

                asset, ew, eh = emoji
                _draw.draw(tft, asset, (w - ew) // 2, y_emoji, 0)
                tft.mark_dirty((w - ew) // 2, y_emoji, ew, eh)
            except Exception:
                emoji = None

        # Card label + colour below emoji (or centred if no emoji)
        y_text = y_emoji + 56 if emoji else h // 2 - 20
        draw_centered(tft, label, y_text, theme.WHITE, w)
        if colour:
            draw_centered(tft, colour, y_text + 14, theme.MUTED, w)

        # Card ID in small text
        draw_centered(tft, card_id, y_text + 30, theme.DIM, w)

        # Write state feedback
        y_status = h - 56
        if self._write_state == _IDLE:
            draw_centered(tft, t("nfc_tap_tag"), y_status, theme.AMBER, w)
        elif self._write_state == _WRITING:
            draw_centered(tft, t("nfc_writing"), y_status, theme.AMBER, w)
        elif self._write_state == _OK:
            draw_centered(tft, t("nfc_write_ok"), y_status, theme.GREEN, w)
        elif self._write_state == _FAIL:
            draw_centered(tft, t("nfc_write_fail"), y_status, theme.RED, w)

        # Footer: written count + nav hint
        footer_y = h - 20
        if self._written_count > 0:
            draw_centered(
                tft,
                "{} {}".format(self._written_count, t("nfc_written")),
                footer_y - 14,
                theme.DIM,
                w,
            )
        draw_centered(tft, t("nfc_scroll_hint"), footer_y, theme.DIM, w)
