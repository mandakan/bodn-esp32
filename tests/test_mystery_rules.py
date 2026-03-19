# tests/test_mystery_rules.py — host-side tests for the Mystery Box rule engine

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "firmware"))

from bodn.mystery_rules import (
    MysteryEngine,
    OUT_IDLE,
    OUT_SINGLE,
    OUT_MIX,
    OUT_MAGIC,
    COMBO_WINDOW,
    DISPLAY_HOLD,
    MAGIC_HOLD,
    mix_rgb,
)


def test_mix_rgb():
    assert mix_rgb((255, 0, 0), (0, 0, 255)) == (127, 0, 127)
    assert mix_rgb((0, 0, 0), (255, 255, 255)) == (127, 127, 127)
    assert mix_rgb((100, 200, 50), (100, 200, 50)) == (100, 200, 50)


def test_initial_state_is_idle():
    engine = MysteryEngine()
    assert engine.output_type == OUT_IDLE
    assert engine.output_color == (0, 0, 0)
    assert engine.discovery_count == 0


def test_single_button_press():
    engine = MysteryEngine()
    out_type, color = engine.update(0, frame=1)
    assert out_type == OUT_SINGLE
    assert color == (255, 0, 0)  # Button 0 = Red


def test_single_button_tracks_discovery():
    engine = MysteryEngine()
    engine.update(3, frame=1)
    assert engine.discovery_count == 1
    # Same button again doesn't add a new discovery
    engine.update(3, frame=5)
    assert engine.discovery_count == 1


def test_two_button_mix():
    engine = MysteryEngine()
    # Press button 1 (Green)
    engine.update(1, frame=1)
    # Press button 3 (Yellow) within combo window
    out_type, color = engine.update(3, frame=10)
    assert out_type == OUT_MIX
    # Green (0,255,0) + Yellow (255,255,0) → (127,255,0)
    assert color == (127, 255, 0)


def test_magic_combo():
    engine = MysteryEngine()
    # Red (0) + Blue (2) = magic combo → Purple
    engine.update(0, frame=1)
    out_type, color = engine.update(2, frame=10)
    assert out_type == OUT_MAGIC
    assert color == (128, 0, 255)
    # Should be tracked as a discovery
    assert (0, 2) in engine.discoveries


def test_combo_window_expires():
    engine = MysteryEngine()
    engine.update(0, frame=1)
    # Wait beyond combo window, then press another button
    late_frame = 1 + COMBO_WINDOW + 5
    out_type, color = engine.update(2, frame=late_frame)
    # Should be a single press, not a combo
    assert out_type == OUT_SINGLE
    assert color == (0, 0, 255)  # Blue


def test_output_expires_to_idle():
    engine = MysteryEngine()
    engine.update(0, frame=1)
    assert engine.output_type == OUT_SINGLE
    # Advance past display hold
    engine.update(-1, frame=1 + DISPLAY_HOLD + 5)
    assert engine.output_type == OUT_IDLE


def test_magic_holds_longer():
    engine = MysteryEngine()
    engine.update(0, frame=1)
    engine.update(2, frame=5)  # magic combo
    assert engine.output_type == OUT_MAGIC
    # Still visible after DISPLAY_HOLD
    engine.update(-1, frame=5 + DISPLAY_HOLD + 1)
    assert engine.output_type == OUT_MAGIC
    # Gone after MAGIC_HOLD
    engine.update(-1, frame=5 + MAGIC_HOLD + 5)
    assert engine.output_type == OUT_IDLE


def test_same_button_twice_is_single():
    engine = MysteryEngine()
    engine.update(3, frame=1)
    out_type, color = engine.update(3, frame=5)
    assert out_type == OUT_SINGLE
    assert color == (255, 255, 0)  # Yellow


def test_make_leds_idle_returns_n_leds():
    from bodn.patterns import N_LEDS

    engine = MysteryEngine()
    leds = engine.make_leds(frame=10, brightness=128)
    assert len(leds) == N_LEDS
    # Should have some non-zero values (ambient glow)
    assert any(sum(c) > 0 for c in leds)


def test_make_leds_single_all_same_color():
    from bodn.patterns import N_LEDS

    engine = MysteryEngine()
    engine.update(0, frame=1)
    leds = engine.make_leds(frame=1, brightness=255)
    assert len(leds) == N_LEDS
    # All LEDs should be the same color (red-ish)
    assert all(led == leds[0] for led in leds)
    assert leds[0][0] > 0  # has red component


def test_discovery_count_accumulates():
    engine = MysteryEngine()
    # Press 3 different single buttons
    engine.update(0, frame=1)
    engine.update(-1, frame=COMBO_WINDOW + 10)
    engine.update(1, frame=COMBO_WINDOW + 20)
    engine.update(-1, frame=2 * COMBO_WINDOW + 30)
    engine.update(2, frame=2 * COMBO_WINDOW + 40)
    assert engine.discovery_count == 3

    # Now do a magic combo
    engine.update(-1, frame=3 * COMBO_WINDOW + 50)
    engine.update(0, frame=3 * COMBO_WINDOW + 60)
    engine.update(2, frame=3 * COMBO_WINDOW + 65)
    assert engine.discovery_count == 4  # 3 singles + 1 magic


def test_total_discoverable():
    engine = MysteryEngine()
    # 8 single colors + 8 magic pairs = 16
    assert engine.total_discoverable == 16


def test_invert_modifier():
    engine = MysteryEngine()
    engine.update(0, frame=1)  # Red
    normal = engine.display_color

    engine.sw_invert = True
    inverted = engine.display_color
    # Inverted red should be cyan-ish (255-255, 255-0, 255-0) = (0, 255, 255)
    assert inverted[0] < normal[0]
    assert inverted[1] > normal[1]
    assert inverted[2] > normal[2]


def test_lighten_modifier():
    engine = MysteryEngine()
    engine.update(2, frame=1)  # Blue = (0, 0, 255)
    normal = engine.display_color

    engine.sw_lighten = True
    lightened = engine.display_color
    # Lightened blue should have higher R and G
    assert lightened[0] > normal[0]
    assert lightened[1] > normal[1]


def test_hue_shift_modifier():
    engine = MysteryEngine()
    engine.update(0, frame=1)  # Red
    normal = engine.display_color

    engine.hue_shift = 85  # ~1/3 rotation
    shifted = engine.display_color
    assert shifted != normal


def test_modifiers_affect_leds():
    from bodn.patterns import N_LEDS

    engine = MysteryEngine()
    engine.update(0, frame=1)  # Red
    leds_normal = list(engine.make_leds(frame=1, brightness=200))

    engine.sw_invert = True
    leds_inverted = list(engine.make_leds(frame=1, brightness=200))
    # LED colors should differ
    assert leds_normal[0] != leds_inverted[0]


def test_mirror_modifier():
    from bodn.patterns import N_LEDS

    engine = MysteryEngine()
    engine.update(0, frame=1)
    # MIX output creates an expanding pattern from center — not symmetric
    engine.update(1, frame=2)  # combo
    engine.sw_mirror = True
    leds = engine.make_leds(frame=3, brightness=200)
    # First and last LED should match
    assert leds[0] == leds[N_LEDS - 1]
