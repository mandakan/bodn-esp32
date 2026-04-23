# bodn/ui/launch_splash.py — full-screen "Loading <mode>" splash for the
# NFC launch path when the active screen has no loading UI of its own
# (mode → mode replace; HomeScreen uses its own carousel feedback).
#
# Extracted from main.py so the MicroPython Unix port can import and
# exercise it in tests — the closure-state idiom has to stay
# MicroPython-safe (no function-attribute assignment).

from bodn.i18n import t, capitalize
from bodn.ui.widgets import (
    draw_centered,
    blit_sprite,
    make_emoji_sprite,
    make_icon_sprite,
)
from bodn.ui.icons import MODE_ICONS


def _build_mode_icon(mode_name, theme):
    """Build a mode icon sprite using the same pipeline as HomeScreen —
    emoji first, 1-bit icon fallback.  Returns (fb, w, h) or None.
    """
    if not mode_name:
        return None
    spr = make_emoji_sprite(mode_name, 96)
    if spr is None:
        spr = make_emoji_sprite(mode_name, 48)
    if spr is not None:
        return spr
    icon_data = MODE_ICONS.get(mode_name)
    if icon_data is None:
        return None
    return make_icon_sprite(icon_data, 16, 16, theme.CYAN, scale=4)


def make_launch_splash(manager, mode_name):
    """Return an ``on_progress(loaded, total)`` callback that paints a
    full-screen "Loading <mode>" splash with a progress bar.

    Mirrors the home carousel: mode icon on top, label below, bar
    underneath.  First call clears the whole screen and pushes the
    full frame; later calls update only the bar zone via ``show_rect``
    to avoid flashing.
    """
    tft = manager.tft
    theme = manager.theme
    w = theme.width
    h = theme.height

    label = capitalize(t("mode_" + mode_name) if mode_name else t("home_loading"))
    icon_sprite = _build_mode_icon(mode_name, theme)
    icon_h = icon_sprite[2] if icon_sprite else 0

    # Layout: icon → gap → label → gap → bar, vertically centred.
    label_scale = 2
    label_h = 8 * label_scale
    bar_h = 8
    gap = 12
    block_h = icon_h + (gap if icon_h else 0) + label_h + gap + bar_h
    block_y = (h - block_h) // 2
    icon_y = block_y
    label_y = icon_y + icon_h + (gap if icon_h else 0)
    bar_mx = 40
    bar_w = w - bar_mx * 2
    bar_y = label_y + label_h + gap
    zone_y = bar_y - 4
    zone_h = bar_h + 8

    # MicroPython doesn't support assigning attributes to function
    # objects, so closure state lives in a list cell the inner function
    # can mutate.  state = [first_call, first_push]
    state = [True, True]

    def _paint(loaded, total):
        if state[0]:
            tft.fill(theme.BLACK)
            if icon_sprite is not None:
                _, iw, _ = icon_sprite
                blit_sprite(tft, icon_sprite, (w - iw) // 2, icon_y)
            draw_centered(tft, label, label_y, theme.WHITE, w, scale=label_scale)
            state[0] = False
        tft.fill_rect(bar_mx, bar_y, bar_w, bar_h, theme.BLACK)
        tft.rect(bar_mx, bar_y, bar_w, bar_h, theme.DIM)
        if total > 0:
            fill_w = bar_w * loaded // total
            if fill_w > 0:
                tft.fill_rect(bar_mx, bar_y, fill_w, bar_h, theme.CYAN)
        if state[1]:
            tft.show()
            state[1] = False
        else:
            tft.show_rect(0, zone_y, w, zone_h)

    return _paint
