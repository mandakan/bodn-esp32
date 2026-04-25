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
    EV_NONE,
    EV_NEW_SINGLE,
    EV_NEW_MAGIC,
    EV_NEW_MOD,
    EV_COMPLETE,
    COMBO_WINDOW_MS,
    DISPLAY_HOLD_MS,
    MAGIC_HOLD_MS,
    MOD_INVERT_AT,
    MOD_MIRROR_AT,
    MOD_HUE_SINGLES,
    MOD_INVERT,
    MOD_MIRROR,
    MOD_HUE,
    BASE_COLORS,
    COLOR_ALCHEMY_MAGIC,
    mix_rgb,
)

DT = 33


def test_mix_rgb():
    assert mix_rgb((255, 0, 0), (0, 0, 255)) == (127, 0, 127)
    assert mix_rgb((0, 0, 0), (255, 255, 255)) == (127, 127, 127)
    assert mix_rgb((100, 200, 50), (100, 200, 50)) == (100, 200, 50)


def test_initial_state_is_idle():
    engine = MysteryEngine()
    assert engine.output_type == OUT_IDLE
    assert engine.output_color == (0, 0, 0)
    assert engine.discovery_count == 0


def test_single_button_press_uses_cap_palette():
    engine = MysteryEngine()
    out_type, color = engine.update(0, dt=DT)
    assert out_type == OUT_SINGLE
    # Button 0 is the green cap (matches theme.BTN_RGB).
    assert color == BASE_COLORS[0] == (0, 200, 0)


def test_single_button_tracks_discovery():
    engine = MysteryEngine()
    engine.update(3, dt=DT)
    assert engine.discovery_count == 1
    # Same button again doesn't add a new discovery
    engine.update(3, dt=DT)
    assert engine.discovery_count == 1


def test_two_button_mix_for_non_magic_pair():
    engine = MysteryEngine()
    # Pair (5, 7) is teal + sky — not in the magic dict, so it averages.
    engine.update(5, dt=DT)
    out_type, color = engine.update(7, dt=200)
    assert out_type == OUT_MIX
    assert color == mix_rgb(BASE_COLORS[5], BASE_COLORS[7])


def test_magic_combo():
    engine = MysteryEngine()
    # Green (0) + Blue (1) is in the magic dict -> cyan.
    engine.update(0, dt=DT)
    out_type, color = engine.update(1, dt=200)
    assert out_type == OUT_MAGIC
    assert color == COLOR_ALCHEMY_MAGIC[(0, 1)]
    assert (0, 1) in engine.magic_discovered


def test_combo_window_expires():
    engine = MysteryEngine()
    engine.update(0, dt=DT)
    out_type, color = engine.update(1, dt=COMBO_WINDOW_MS + 100)
    assert out_type == OUT_SINGLE
    assert color == BASE_COLORS[1]


def test_output_expires_to_idle():
    engine = MysteryEngine()
    engine.update(0, dt=DT)
    assert engine.output_type == OUT_SINGLE
    engine.update(-1, dt=DISPLAY_HOLD_MS + 100)
    assert engine.output_type == OUT_IDLE


def test_magic_holds_longer():
    engine = MysteryEngine()
    engine.update(0, dt=DT)
    engine.update(1, dt=100)  # magic combo
    assert engine.output_type == OUT_MAGIC
    engine.update(-1, dt=DISPLAY_HOLD_MS + 100)
    assert engine.output_type == OUT_MAGIC
    engine.update(-1, dt=MAGIC_HOLD_MS)
    assert engine.output_type == OUT_IDLE


def test_same_button_twice_is_single():
    engine = MysteryEngine()
    engine.update(3, dt=DT)
    out_type, color = engine.update(3, dt=100)
    assert out_type == OUT_SINGLE
    assert color == BASE_COLORS[3]


def test_make_static_leds_idle_returns_n_leds():
    from bodn.patterns import N_LEDS, N_STICKS

    engine = MysteryEngine()
    leds = engine.make_static_leds(brightness=128)
    assert len(leds) == N_LEDS
    assert any(sum(c) > 0 for c in leds[:N_STICKS])


def test_make_static_leds_single_all_same_color():
    from bodn.patterns import N_STICKS

    engine = MysteryEngine()
    engine.update(0, dt=DT)
    leds = engine.make_static_leds(brightness=255)
    stick_leds = leds[:N_STICKS]
    assert all(led == stick_leds[0] for led in stick_leds)
    assert stick_leds[0][1] > 0  # base colour is green so green channel is non-zero


def test_discovery_count_accumulates():
    engine = MysteryEngine()
    engine.update(2, dt=DT)
    engine.update(-1, dt=COMBO_WINDOW_MS + 100)
    engine.update(5, dt=DT)
    engine.update(-1, dt=COMBO_WINDOW_MS + 100)
    engine.update(6, dt=DT)
    assert engine.discovery_count == 3
    # A magic combo bumps the count by one (the pair counts; the singles
    # in the pair are counted only on the *first* press of each).
    engine.update(-1, dt=COMBO_WINDOW_MS + 100)
    engine.update(0, dt=DT)
    engine.update(1, dt=100)
    # 3 prior singles + green single + magic = 5.
    assert engine.discovery_count == 5


def test_total_discoverable():
    engine = MysteryEngine()
    assert engine.total_discoverable == len(BASE_COLORS) + len(COLOR_ALCHEMY_MAGIC)
    assert engine.total_discoverable == 16


def test_invert_modifier_requires_unlock():
    engine = MysteryEngine()
    engine.update(0, dt=DT)  # discover green
    engine.sw_invert = True
    # Locked: invert ignored, colour unchanged.
    assert engine.display_color == BASE_COLORS[0]
    engine._invert_unlocked = True
    assert engine.display_color != BASE_COLORS[0]


def test_hue_modifier_requires_unlock():
    engine = MysteryEngine()
    engine.update(0, dt=DT)
    engine.hue_shift = 85
    assert engine.display_color == BASE_COLORS[0]  # locked
    engine._hue_unlocked = True
    assert engine.display_color != BASE_COLORS[0]


def test_modifiers_affect_leds_when_unlocked():
    engine = MysteryEngine()
    engine.update(0, dt=DT)
    leds_normal = list(engine.make_static_leds(brightness=200))
    engine._invert_unlocked = True
    engine.sw_invert = True
    leds_inverted = list(engine.make_static_leds(brightness=200))
    assert leds_normal[0] != leds_inverted[0]


def test_mirror_modifier_requires_unlock():
    engine = MysteryEngine()
    engine.update(0, dt=DT)
    engine.update(1, dt=DT)
    engine.sw_mirror = True
    # Without unlock, mirror_active is False so the buffer isn't mirrored.
    assert engine.mirror_active is False
    engine._mirror_unlocked = True
    assert engine.mirror_active is True


def test_invert_unlocks_at_threshold():
    engine = MysteryEngine()
    # Discover MOD_INVERT_AT distinct singles in a row.
    for i in range(MOD_INVERT_AT):
        engine.update(i, dt=DT)
        engine.update(-1, dt=COMBO_WINDOW_MS + 100)
    assert engine.discovery_count == MOD_INVERT_AT
    assert engine.invert_unlocked is True
    assert engine.last_mod_unlock == MOD_INVERT


def test_mirror_unlocks_at_higher_threshold():
    engine = MysteryEngine()
    # Burn through 8 singles + 2 magic combos to clear MOD_MIRROR_AT.
    for i in range(8):
        engine.update(i, dt=DT)
        engine.update(-1, dt=COMBO_WINDOW_MS + 100)
    assert engine.discovery_count == 8
    # Two magic pairs to reach 10 total discoveries.
    for pair in list(COLOR_ALCHEMY_MAGIC.keys())[:2]:
        a, b = pair
        engine.update(a, dt=DT)
        engine.update(b, dt=200)
        engine.update(-1, dt=COMBO_WINDOW_MS + 100)
    assert engine.discovery_count >= MOD_MIRROR_AT
    assert engine.mirror_unlocked is True


def test_hue_unlocks_after_all_singles():
    engine = MysteryEngine()
    for i in range(MOD_HUE_SINGLES - 1):
        engine.update(i, dt=DT)
        engine.update(-1, dt=COMBO_WINDOW_MS + 100)
    assert engine.hue_unlocked is False
    engine.update(MOD_HUE_SINGLES - 1, dt=DT)
    assert engine.hue_unlocked is True


def test_event_stream():
    engine = MysteryEngine()
    engine.update(0, dt=DT)
    assert engine.consume_event() == EV_NEW_SINGLE
    assert engine.consume_event() == EV_NONE  # consumed
    engine.update(-1, dt=COMBO_WINDOW_MS + 100)
    engine.update(0, dt=DT)
    engine.update(1, dt=200)  # magic
    # First a new magic event -- but if the modifier threshold trips on the
    # same press, EV_NEW_MAGIC takes precedence over EV_NEW_MOD.
    ev = engine.consume_event()
    assert ev in (EV_NEW_MAGIC, EV_NEW_MOD)


def test_complete_event_when_all_found():
    engine = MysteryEngine()
    # Force every single + magic into discovered sets.
    for i in range(len(BASE_COLORS)):
        engine.singles_discovered.add(i)
    for pair in list(COLOR_ALCHEMY_MAGIC.keys())[:-1]:
        engine.magic_discovered.add(pair)
    last_pair = list(COLOR_ALCHEMY_MAGIC.keys())[-1]
    a, b = last_pair
    engine.update(a, dt=DT)
    engine.consume_event()
    engine.update(b, dt=200)
    assert engine.is_complete is True
    assert engine.consume_event() == EV_COMPLETE


def test_to_state_round_trip():
    engine = MysteryEngine()
    engine.update(0, dt=DT)
    engine.update(-1, dt=COMBO_WINDOW_MS + 100)
    engine.update(1, dt=DT)
    engine.update(2, dt=200)
    state = engine.to_state()

    restored = MysteryEngine()
    restored.load_state(state)
    assert restored.singles_discovered == engine.singles_discovered
    assert restored.magic_discovered == engine.magic_discovered
    assert restored.invert_unlocked == engine.invert_unlocked
    assert restored.mirror_unlocked == engine.mirror_unlocked
    assert restored.hue_unlocked == engine.hue_unlocked


def test_load_state_promotes_gates_for_legacy_data():
    # Persisted state from before modifier gates existed: lots of finds, no flags.
    engine = MysteryEngine()
    engine.load_state(
        {
            "singles": list(range(8)),
            "magic": [list(p) for p in list(COLOR_ALCHEMY_MAGIC.keys())[:2]],
        }
    )
    # discovery_count is 10 -> all three gates should latch.
    assert engine.invert_unlocked is True
    assert engine.mirror_unlocked is True
    assert engine.hue_unlocked is True
