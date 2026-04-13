# bodn/ui/soundboard_secondary.py — secondary display content for Soundboard mode
#
# Shows the current bank name, volume bar, and a pulsing note icon during playback.

from bodn.ui.screen import Screen
from bodn.ui.secondary import CONTENT_SIZE
from bodn.ui.widgets import draw_centered, draw_progress_bar
from bodn.i18n import t


class SoundboardSecondary(Screen):
    """Status panel for the soundboard on the 128×128 secondary display."""

    def __init__(self):
        self._bank_name = ""
        self._volume = 50
        self._muted = False
        self._playing = False
        self._dirty = True

    def enter(self, display):
        self._dirty = True

    def update(self, bank_name, volume, muted, playing):
        """Called by SoundboardScreen each frame when state changes."""
        if (
            bank_name != self._bank_name
            or volume != self._volume
            or muted != self._muted
            or playing != self._playing
        ):
            self._bank_name = bank_name
            self._volume = volume
            self._muted = muted
            self._playing = playing
            self._dirty = True

    def needs_redraw(self):
        return self._dirty

    def render(self, tft, theme, frame):
        self._dirty = False
        w = CONTENT_SIZE  # 128
        tft.fill_rect(0, 0, w, w, theme.BLACK)

        # Bank name — large, centered
        name = self._bank_name
        # Truncate to fit 8 chars × 2 scale = 128px
        if len(name) > 8:
            name = name[:8]
        draw_centered(tft, name.capitalize(), 12, theme.CYAN, w, scale=2)

        # Musical note indicator — animates during playback
        note_color = theme.YELLOW if self._playing else theme.DIM
        if self._playing:
            # Simple pulse animation
            phase = (frame * 4) & 0xFF
            v = phase if phase < 128 else 255 - phase
            r = (0xFF * v) >> 8
            g = (0xFF * v) >> 8
            note_color = tft.rgb(r, g, 0)
        # Draw a simple note symbol (vertical bar + horizontal flag)
        cx = w // 2
        tft.fill_rect(cx - 1, 42, 3, 28, note_color)  # stem
        tft.fill_rect(cx - 1, 70, 10, 6, note_color)  # note head
        tft.fill_rect(cx + 2, 42, 10, 10, note_color)  # flag

        # Volume / mute indicator
        if self._muted:
            draw_centered(tft, t("sb_muted"), 86, theme.RED, w, scale=2)
        else:
            vol_label = t("sb_volume", self._volume)
            draw_centered(tft, vol_label, 84, theme.WHITE, w)
            # Volume bar
            bar_w = 100
            bar_x = (w - bar_w) // 2
            draw_progress_bar(
                tft,
                bar_x,
                96,
                bar_w,
                8,
                self._volume,
                100,
                theme.CYAN,
                theme.DIM,
                border=theme.MUTED,
            )
