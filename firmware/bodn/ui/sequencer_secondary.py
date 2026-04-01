# bodn/ui/sequencer_secondary.py — secondary display content for Sequencer mode
#
# Shows BPM (large), play/pause state, and step count on the 128×128 zone.

from bodn.ui.screen import Screen
from bodn.ui.secondary import CONTENT_SIZE
from bodn.ui.widgets import draw_centered
from bodn.i18n import t


class SequencerSecondary(Screen):
    """Info panel for the sequencer on the 128×128 secondary display."""

    def __init__(self):
        self._bpm = 90
        self._playing = False
        self._n_steps = 8
        self._dirty = True

    def enter(self, display):
        self._dirty = True

    def update_state(self, bpm, playing, n_steps):
        """Called by SequencerScreen each frame when values change."""
        if bpm != self._bpm or playing != self._playing or n_steps != self._n_steps:
            self._bpm = bpm
            self._playing = playing
            self._n_steps = n_steps
            self._dirty = True

    def needs_redraw(self):
        return self._dirty

    def render(self, tft, theme, frame):
        self._dirty = False
        w = CONTENT_SIZE  # 128
        tft.fill_rect(0, 0, w, w, theme.BLACK)

        # BPM — big centred number
        draw_centered(tft, str(self._bpm), 16, theme.CYAN, w, scale=3)
        draw_centered(tft, t("seq_bpm"), 44, theme.MUTED, w)

        # Play/pause state
        if self._playing:
            color = theme.GREEN
            label = t("seq_playing")
        else:
            color = theme.YELLOW
            label = t("seq_paused")
        draw_centered(tft, label, 68, color, w, scale=2)

        # Step count
        draw_centered(tft, t("seq_steps", self._n_steps), 96, theme.MUTED, w)
