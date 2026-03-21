"""Tests for FlodeEngine — Flöde game logic."""

from bodn.flode_rules import FlodeEngine, PLAYING, COMPLETE, CELEBRATE, MAX_LEVEL


def make_rand(sequence):
    """Create a deterministic rand_fn from a list of return values."""
    it = iter(sequence)
    return lambda n: next(it) % n


def test_start_level_one():
    eng = FlodeEngine(rand_fn=make_rand([1, 0]))
    eng.start_level(1)
    assert eng.level == 1
    assert eng.num_segments == 1
    assert eng.num_positions == 3
    assert eng.state == PLAYING
    assert len(eng.positions) == 1


def test_positions_differ_from_target():
    # Target=1, segment should not start at 1
    eng = FlodeEngine(rand_fn=make_rand([1, 0]))
    eng.start_level(1)
    assert eng.target == 1
    assert eng.positions[0] != eng.target


def test_shift_moves_segment():
    eng = FlodeEngine(rand_fn=make_rand([1, 0]))
    eng.start_level(1)
    # Position starts at 0 (rand(2)=0, since 0 < target=1, stays 0)
    assert eng.positions[0] == 0
    changed = eng.shift(1)
    assert changed
    assert eng.positions[0] == 1


def test_shift_clamped_at_bounds():
    eng = FlodeEngine(rand_fn=make_rand([1, 0]))
    eng.start_level(1)
    # At position 0, can't go lower
    changed = eng.shift(-1)
    assert not changed
    assert eng.positions[0] == 0


def test_shift_to_target_completes():
    eng = FlodeEngine(rand_fn=make_rand([1, 0]))
    eng.start_level(1)
    # target=1, position=0, shift +1 should complete
    eng.shift(1)
    assert eng.state == COMPLETE


def test_flow_reaches_partial():
    # 2 segments: target=0, positions=[0, 2]
    eng = FlodeEngine(rand_fn=make_rand([0, 0, 1]))
    eng.start_level(2)
    assert eng.target == 0
    # First segment at 0 (rand(2)=0 → 0 >= 0 → +1 → 1)... let me check
    # Actually: target = rand(3) = 0
    # seg0: rand(2) = 0, 0 >= 0 → 0+1=1
    # seg1: rand(2) = 1, 1 >= 0 → 1+1=2
    assert eng.positions[0] == 1  # misaligned
    assert eng.flow_reaches() == 0

    # Fix first segment
    eng.shift(-1)  # 1 → 0
    assert eng.flow_reaches() == 1  # first aligned, second still off


def test_select_delta_wraps():
    eng = FlodeEngine(rand_fn=make_rand([0, 1, 1]))
    eng.start_level(2)
    assert eng.selected == 0
    eng.select_delta(1)
    assert eng.selected == 1
    eng.select_delta(1)
    assert eng.selected == 0  # wraps


def test_select_delta_single_segment():
    eng = FlodeEngine(rand_fn=make_rand([1, 0]))
    eng.start_level(1)
    changed = eng.select_delta(1)
    assert not changed
    assert eng.selected == 0


def test_select_delta_backward():
    eng = FlodeEngine(rand_fn=make_rand([0, 1, 1]))
    eng.start_level(2)
    eng.select_delta(-1)
    assert eng.selected == 1  # wraps from 0 to last


def test_shift_ignored_when_complete():
    eng = FlodeEngine(rand_fn=make_rand([1, 0]))
    eng.start_level(1)
    eng.shift(1)  # completes
    assert eng.state == COMPLETE
    changed = eng.shift(-1)
    assert not changed


def test_celebration_lifecycle():
    eng = FlodeEngine(rand_fn=make_rand([1, 0]))
    eng.start_level(1)
    eng.shift(1)
    assert eng.state == COMPLETE

    eng.start_celebration()
    assert eng.state == CELEBRATE

    # Not done yet
    for _ in range(59):
        assert not eng.update_celebration()

    # Done at frame 60
    assert eng.update_celebration()


def test_celebrate_progress():
    eng = FlodeEngine(rand_fn=make_rand([1, 0]))
    eng.start_level(1)
    eng.shift(1)
    eng.start_celebration()

    assert eng.celebrate_progress == 0
    for _ in range(30):
        eng.update_celebration()
    assert eng.celebrate_progress == 50


def test_has_next_level():
    eng = FlodeEngine(rand_fn=make_rand([0] * 50))
    eng.start_level(1)
    assert eng.has_next_level()

    eng.start_level(MAX_LEVEL)
    assert not eng.has_next_level()


def test_level_clamped_to_max():
    eng = FlodeEngine(rand_fn=make_rand([0] * 50))
    eng.start_level(99)
    assert eng.level == MAX_LEVEL


def test_multi_segment_completion():
    # 3 segments, 4 positions
    # target=2, all segments start misaligned
    rand_vals = [2, 0, 0, 0]  # target=2, seg0=0, seg1=0, seg2=0
    eng = FlodeEngine(rand_fn=make_rand(rand_vals))
    eng.start_level(3)
    assert eng.target == 2
    assert eng.state == PLAYING

    # Fix each segment
    for i in range(3):
        eng.selected = i
        while eng.positions[i] != eng.target:
            eng.shift(1)

    assert eng.state == COMPLETE
    assert eng.flow_reaches() == 3


def test_selected_segment_shift():
    """Only the selected segment should move."""
    rand_vals = [1, 0, 0]
    eng = FlodeEngine(rand_fn=make_rand(rand_vals))
    eng.start_level(2)

    pos0_before = eng.positions[0]
    eng.select_delta(1)  # select segment 1
    eng.shift(1)

    assert eng.positions[0] == pos0_before  # unchanged
