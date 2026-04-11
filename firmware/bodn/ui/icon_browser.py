# bodn/ui/icon_browser.py — browse available OpenMoji emoji sprites
#
# Shows one emoji at a time with metadata (name, codepoint, size).
# NAV encoder cycles through icons, ENC_A cycles through sizes.
# Any button press exits.

import os

from micropython import const
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered, load_emoji, make_label_sprite, blit_sprite
from bodn.i18n import t

NAV = const(0)
ADJ = const(1)

_SIZES = (48, 32, 24)


class IconBrowserScreen(Screen):
    """Browse available emoji sprites from the SD card."""

    def __init__(self):
        self._manager = None
        self._dirty = True
        self._icons = []  # list of (name, codepoint, label)
        self._index = 0
        self._size_idx = 0  # index into _SIZES
        self._title_sprite = None

    def enter(self, manager):
        self._manager = manager
        self._dirty = True
        self._index = 0
        self._size_idx = 0
        self._title_sprite = make_label_sprite(t("settings_icons"), 0xFFFF, scale=2)
        self._scan_icons()

    def _scan_icons(self):
        """Discover available emoji by scanning /sd/sprites/ for BDF files."""
        self._icons = []
        try:
            entries = []
            for base in ("/sd/sprites", "/sprites"):
                try:
                    entries = os.listdir(base)
                    break
                except OSError:
                    continue

            # Parse unique icon names from filenames like emoji_cat_48.bdf
            seen = {}
            for name in sorted(entries):
                if not name.startswith("emoji_") or not name.endswith(".bdf"):
                    continue
                parts = name[6:-4].rsplit("_", 1)
                if len(parts) != 2:
                    continue
                icon_name = parts[0]
                if icon_name not in seen:
                    seen[icon_name] = True
                    self._icons.append(icon_name)
        except Exception:
            self._icons = []

    def needs_redraw(self):
        return self._dirty

    def update(self, inp, frame):
        if not self._icons:
            if inp.any_btn_pressed() or inp.enc_btn_pressed[NAV]:
                self._manager.pop()
            return

        changed = False

        # NAV encoder: cycle icons
        delta = inp.enc_delta[NAV]
        if delta != 0:
            n = len(self._icons)
            step = 1 if delta > 0 else -1
            self._index = (self._index + step) % n
            changed = True

        # ADJ encoder: cycle sizes
        delta_a = inp.enc_delta[ADJ]
        if delta_a != 0:
            step = 1 if delta_a > 0 else -1
            self._size_idx = (self._size_idx + step) % len(_SIZES)
            changed = True

        if changed:
            self._dirty = True

        # Any button: exit
        if inp.any_btn_pressed() or inp.enc_btn_pressed[NAV]:
            self._manager.pop()

    def render(self, tft, theme, frame):
        self._dirty = False
        w = theme.width
        h = theme.height
        tft.fill(theme.BLACK)

        # Title
        if self._title_sprite:
            _, tw, _ = self._title_sprite
            blit_sprite(tft, self._title_sprite, (w - tw) // 2, 6)

        if not self._icons:
            draw_centered(tft, "No emoji found", h // 2 - 4, theme.MUTED, w)
            draw_centered(tft, "Check SD card", h // 2 + 10, theme.MUTED, w)
            return

        name = self._icons[self._index]
        size = _SIZES[self._size_idx]

        # Load and render emoji
        emoji = load_emoji(name, size)
        if emoji:
            asset, ew, eh = emoji
            try:
                from bodn.ui.draw import sprite

                ex = (w - ew) // 2
                ey = 32 + (64 - eh) // 2  # centered in a 64px area below title
                # Draw a subtle background rect to show icon bounds
                tft.rect(ex - 2, ey - 2, ew + 4, eh + 4, theme.DIM)
                sprite(tft, ex, ey, asset, 0, 0xFFFF)
            except Exception:
                draw_centered(tft, "[render error]", 60, theme.RED, w)
        else:
            draw_centered(tft, "[not found]", 60, theme.MUTED, w)

        # Info lines below icon
        info_y = 104

        # Name
        draw_centered(tft, name, info_y, theme.WHITE, w)

        # Size info
        size_text = "{}x{} px".format(size, size)
        draw_centered(tft, size_text, info_y + 14, theme.MUTED, w)

        # Size selector indicator
        sel_y = info_y + 32
        total_w = 0
        labels = []
        for i, s in enumerate(_SIZES):
            label = "{}px".format(s)
            labels.append(label)
            total_w += len(label) * 8 + 12
        total_w -= 12  # no trailing gap

        sx = (w - total_w) // 2
        for i, label in enumerate(labels):
            col = theme.CYAN if i == self._size_idx else theme.DIM
            tft.text(label, sx, sel_y, col)
            sx += len(label) * 8 + 12

        # Index counter
        counter = "{} / {}".format(self._index + 1, len(self._icons))
        draw_centered(tft, counter, h - 28, theme.MUTED, w)

        # Nav hint
        draw_centered(tft, "< turn > size  btn=back", h - 14, theme.DIM, w)
