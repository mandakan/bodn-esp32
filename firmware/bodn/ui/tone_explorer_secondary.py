# bodn/ui/tone_explorer_secondary.py — Tone Lab status/overflow display
#
# Always shows the current note name, timbre, and the active-effects ribbon.
# When the primary display is dedicated to the big scope, the blob moves here
# so the child still sees the shape-of-sound cross-modal binding.


from bodn.ui.screen import Screen
from bodn.ui.secondary import CONTENT_SIZE
from bodn.ui.widgets import draw_centered
from bodn.i18n import t, capitalize
from bodn.tone_explorer_rules import (
    MINI_BUTTON_EFFECT,
    NOTES_PER_OCTAVE,
    TIMBRE_TABLE,
)

_SCALE_NAMES = ("C", "D", "E", "G", "A")  # pentatonic major


class ToneExplorerSecondary(Screen):
    """128×128 status panel for the Tone Lab."""

    def __init__(self):
        self._pitch_idx = -1
        self._timbre_idx = -1
        self._effects_mask = -1
        self._viz_big_scope = False
        self._dirty = True

    def enter(self, display):
        self._dirty = True

    def update_state(self, pitch_idx, timbre_idx, effects_mask, viz_big_scope):
        """Called by the primary screen when engine state changes."""
        if (
            pitch_idx != self._pitch_idx
            or timbre_idx != self._timbre_idx
            or effects_mask != self._effects_mask
            or viz_big_scope != self._viz_big_scope
        ):
            self._pitch_idx = pitch_idx
            self._timbre_idx = timbre_idx
            self._effects_mask = effects_mask
            self._viz_big_scope = viz_big_scope
            self._dirty = True

    def needs_redraw(self):
        return self._dirty

    def render(self, tft, theme, frame):
        self._dirty = False
        w = CONTENT_SIZE
        tft.fill_rect(0, 0, w, w, theme.BLACK)

        # Note name + octave indicator — big centre element.
        if self._pitch_idx >= 0:
            step = self._pitch_idx % NOTES_PER_OCTAVE
            octave_mark = "'" if self._pitch_idx >= NOTES_PER_OCTAVE else ""
            label = _SCALE_NAMES[step] + octave_mark
            draw_centered(tft, label, 16, theme.CYAN, w, scale=4)

        # Timbre name — small subtitle.
        if 0 <= self._timbre_idx < len(TIMBRE_TABLE):
            key = TIMBRE_TABLE[self._timbre_idx][2]
            draw_centered(tft, capitalize(t(key)), 66, theme.YELLOW, w)

        # Active-effect ribbon — 8 slots across the bottom.
        y = 90
        slot_w = w // 10
        for i, bit in enumerate(MINI_BUTTON_EFFECT):
            x = slot_w + i * slot_w
            colour = theme.BTN_565[i] if (self._effects_mask & bit) else theme.DIM
            tft.fill_rect(x, y, slot_w - 3, 12, colour)

        # Viz hint — tiny marker showing which display owns the scope.
        if self._viz_big_scope:
            draw_centered(tft, t("tone_explorer_scope_big_hint"), 110, theme.MUTED, w)
