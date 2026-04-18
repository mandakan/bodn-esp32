"""Tone Lab rule engine — pure-logic tests."""

import pytest

from bodn.tone_explorer_rules import (
    EFFECT_BEND_DOWN,
    EFFECT_BEND_UP,
    EFFECT_HARMONY,
    EFFECT_OCTAVE_DOWN,
    EFFECT_OCTAVE_UP,
    EFFECT_STUTTER,
    EFFECT_TREMOLO,
    EFFECT_VIBRATO,
    MINI_BUTTON_EFFECT,
    NOTES_PER_OCTAVE,
    NUM_PITCHES,
    NUM_TIMBRES,
    PENTATONIC_HZ,
    ToneExplorer,
)


def test_pentatonic_table_is_monotonic():
    """Frequencies must strictly increase so low→high spatial mapping holds."""
    for a, b in zip(PENTATONIC_HZ, PENTATONIC_HZ[1:]):
        assert a < b
    # Octave should (approximately) double between the two halves.
    for i in range(NOTES_PER_OCTAVE):
        low = PENTATONIC_HZ[i]
        high = PENTATONIC_HZ[i + NOTES_PER_OCTAVE]
        assert 1.95 < high / low < 2.05


def test_initial_state_is_middle_sine():
    e = ToneExplorer()
    assert e.pitch_idx == 3           # G4 — middle-ish of low octave
    assert e.timbre_idx == 0
    assert e.effects_mask == 0
    assert e.octave_shift == 0
    assert e.playing is False
    assert e.base_freq_hz == PENTATONIC_HZ[3]


def test_arcade_press_snaps_pitch_within_octave():
    e = ToneExplorer()
    e.on_arcade_press(0)
    assert e.pitch_idx == 0
    assert e.base_freq_hz == PENTATONIC_HZ[0]
    e.on_arcade_press(4)
    assert e.pitch_idx == 4
    assert e.base_freq_hz == PENTATONIC_HZ[4]


def test_arcade_press_respects_octave_toggle():
    e = ToneExplorer()
    e.on_octave_toggle(True)           # high octave
    assert e.octave_shift == 1
    e.on_arcade_press(0)
    assert e.pitch_idx == NOTES_PER_OCTAVE   # first note of high octave
    e.on_arcade_press(4)
    assert e.pitch_idx == NUM_PITCHES - 1


def test_arcade_press_ignores_out_of_range():
    e = ToneExplorer()
    before = e.pitch_idx
    e.on_arcade_press(-1)
    e.on_arcade_press(5)
    assert e.pitch_idx == before


def test_pitch_encoder_clamps_and_sets_playing():
    e = ToneExplorer()
    e.on_pitch_delta(-99)
    assert e.pitch_idx == 0
    assert e.playing is True
    e.on_pitch_delta(99)
    assert e.pitch_idx == NUM_PITCHES - 1


def test_pitch_encoder_zero_delta_is_noop():
    e = ToneExplorer()
    e.on_pitch_delta(0)
    assert e.playing is False


def test_timbre_encoder_clamps():
    e = ToneExplorer()
    e.on_timbre_delta(-99)
    assert e.timbre_idx == 0
    e.on_timbre_delta(99)
    assert e.timbre_idx == NUM_TIMBRES - 1


def test_timbre_affects_waveform_and_shape():
    e = ToneExplorer()
    wave0 = e.waveform_id
    shape0 = e.blob_shape_id
    e.on_timbre_delta(NUM_TIMBRES - 1)   # to the fuzzy end
    assert e.waveform_id != wave0
    assert e.blob_shape_id != shape0


def test_octave_toggle_preserves_scale_step():
    """Switching octave should keep the 'which note in the scale' feel."""
    e = ToneExplorer()
    e.on_arcade_press(2)                 # E in the low octave
    step = e.pitch_idx % NOTES_PER_OCTAVE
    assert step == 2
    e.on_octave_toggle(True)
    assert e.pitch_idx % NOTES_PER_OCTAVE == step
    assert e.pitch_idx == NOTES_PER_OCTAVE + 2
    e.on_octave_toggle(False)
    assert e.pitch_idx == 2


def test_mini_button_toggles_effect_bit():
    e = ToneExplorer()
    for idx, bit in enumerate(MINI_BUTTON_EFFECT):
        e.on_mini_button(idx, True)
        assert e.effects_mask & bit
        e.on_mini_button(idx, False)
        assert not (e.effects_mask & bit)


def test_multiple_effects_stack():
    e = ToneExplorer()
    e.on_mini_button(0, True)   # vibrato
    e.on_mini_button(1, True)   # tremolo
    e.on_mini_button(6, True)   # stutter
    assert e.is_effect(EFFECT_VIBRATO)
    assert e.is_effect(EFFECT_TREMOLO)
    assert e.is_effect(EFFECT_STUTTER)


def test_vibrato_params_follow_bit():
    e = ToneExplorer()
    assert e.vibrato_params() == (0.0, 0)
    e.on_mini_button(0, True)
    rate, depth = e.vibrato_params()
    assert rate > 0 and depth > 0
    e.on_mini_button(0, False)
    assert e.vibrato_params() == (0.0, 0)


def test_bend_direction_is_signed():
    e = ToneExplorer()
    e.on_mini_button(2, True)   # bend up
    rate_up, limit = e.bend_params()
    assert rate_up > 0 and limit > 0
    e.on_mini_button(2, False)
    e.on_mini_button(3, True)   # bend down
    rate_down, _ = e.bend_params()
    assert rate_down < 0


def test_octave_jump_cents_signed():
    e = ToneExplorer()
    assert e.octave_jump_cents() == 0
    e.on_mini_button(4, True)   # octave up
    assert e.octave_jump_cents() > 0
    e.on_mini_button(4, False)
    e.on_mini_button(5, True)   # octave down
    assert e.octave_jump_cents() < 0


def test_octave_jump_doubles_or_halves_freq():
    e = ToneExplorer()
    base = e.base_freq_hz
    assert e.effective_freq_hz() == base
    e.on_mini_button(4, True)   # octave up
    assert e.effective_freq_hz() == base * 2
    e.on_mini_button(4, False)
    e.on_mini_button(5, True)   # octave down
    assert e.effective_freq_hz() == base // 2


def test_harmony_freq_is_pentatonic_fifth():
    e = ToneExplorer()
    assert e.harmony_freq_hz() == 0
    e.on_mini_button(7, True)
    h = e.harmony_freq_hz()
    # 3:2 ratio within integer rounding
    expected = (e.base_freq_hz * 3) // 2
    assert h == expected
    # Perfect fifth above pentatonic root is still consonant for 4yo ears.
    assert 1.45 < h / e.base_freq_hz < 1.55


def test_panic_clears_effects_and_playing():
    e = ToneExplorer()
    e.on_arcade_press(1)
    e.on_mini_button(0, True)
    assert e.playing is True
    assert e.effects_mask != 0
    e.on_panic()
    assert e.effects_mask == 0
    assert e.playing is False


def test_reset_timbre_snaps_to_smooth_sine():
    e = ToneExplorer()
    e.on_timbre_delta(3)
    assert e.timbre_idx != 0
    e.on_reset_timbre()
    assert e.timbre_idx == 0


def test_viz_toggle_flips_flag():
    e = ToneExplorer()
    assert e.viz_big_scope is False
    e.on_viz_toggle(True)
    assert e.viz_big_scope is True
    e.on_viz_toggle(False)
    assert e.viz_big_scope is False


def test_params_can_be_overridden_per_instance():
    e = ToneExplorer(params={"vibrato_depth_cents": 99})
    e.on_mini_button(0, True)
    _, depth = e.vibrato_params()
    assert depth == 99


def test_mini_button_out_of_range_is_ignored():
    e = ToneExplorer()
    e.on_mini_button(-1, True)
    e.on_mini_button(8, True)
    e.on_mini_button(99, True)
    assert e.effects_mask == 0
