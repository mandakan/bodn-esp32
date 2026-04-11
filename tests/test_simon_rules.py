# tests/test_simon_rules.py — host-side tests for the Pattern Copy engine

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "firmware"))

from bodn.simon_rules import (
    SimonEngine,
    READY,
    SHOWING,
    WAITING,
    WIN,
    FAIL,
    GAME_OVER,
    SHOW_STEP_MS,
    SHOW_GAP_MS,
    WIN_MS,
    FAIL_MS,
    MAX_FAILS,
    NUM_BUTTONS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tick(eng, dt=33, btn=-1):
    """Advance the engine by one tick (default ~30 fps)."""
    return eng.update(btn, dt)


def _advance_ms(eng, ms, tick_dt=33):
    """Advance the engine by approximately `ms` milliseconds in tick_dt steps."""
    elapsed = 0
    while elapsed < ms:
        step = min(tick_dt, ms - elapsed)
        eng.update(-1, step)
        elapsed += step


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_initial_state_is_ready():
    eng = SimonEngine()
    assert eng.state == READY
    assert eng.score == 0
    assert eng.high_score == 0
    assert eng.sequence == []


def test_any_button_starts_game():
    eng = SimonEngine()
    _tick(eng, btn=0)
    assert eng.state == SHOWING
    assert len(eng.sequence) == 2  # default start_length


def test_custom_start_length():
    eng = SimonEngine(start_length=3)
    _tick(eng, btn=0)
    assert len(eng.sequence) == 3


def test_sequence_uses_valid_buttons():
    eng = SimonEngine()
    _tick(eng, btn=0)
    for btn in eng.sequence:
        assert 0 <= btn < NUM_BUTTONS


def test_showing_transitions_to_waiting():
    eng = SimonEngine(start_length=1)
    _tick(eng, btn=0)
    assert eng.state == SHOWING

    # Advance past the single step (show + gap)
    _advance_ms(eng, SHOW_STEP_MS + SHOW_GAP_MS + 1)
    assert eng.state == WAITING


def test_correct_button_advances():
    eng = SimonEngine(start_length=1)
    _tick(eng, btn=0)

    # Skip through showing phase
    _advance_ms(eng, SHOW_STEP_MS + SHOW_GAP_MS + 1)
    assert eng.state == WAITING

    # Press the correct button
    expected = eng.sequence[0]
    _tick(eng, btn=expected)
    assert eng.state == WIN
    assert eng.score == 1


def test_wrong_button_fails():
    eng = SimonEngine(start_length=1)
    _tick(eng, btn=0)

    _advance_ms(eng, SHOW_STEP_MS + SHOW_GAP_MS + 1)
    assert eng.state == WAITING

    # Press a wrong button
    expected = eng.sequence[0]
    wrong = (expected + 1) % NUM_BUTTONS
    _tick(eng, btn=wrong)
    assert eng.state == FAIL


def test_fail_replays_sequence():
    eng = SimonEngine(start_length=1)
    _tick(eng, btn=0)

    _advance_ms(eng, SHOW_STEP_MS + SHOW_GAP_MS + 1)

    expected = eng.sequence[0]
    wrong = (expected + 1) % NUM_BUTTONS
    _tick(eng, btn=wrong)
    assert eng.state == FAIL

    # After FAIL_MS, should go back to SHOWING (same sequence)
    seq_before = list(eng.sequence)
    _advance_ms(eng, FAIL_MS + 1)
    assert eng.state == SHOWING
    assert eng.sequence == seq_before  # same sequence replayed


def test_win_grows_sequence():
    eng = SimonEngine(start_length=1)
    _tick(eng, btn=0)
    orig_len = len(eng.sequence)

    _advance_ms(eng, SHOW_STEP_MS + SHOW_GAP_MS + 1)

    expected = eng.sequence[0]
    _tick(eng, btn=expected)
    assert eng.state == WIN

    # After WIN_MS, sequence should grow and start showing
    _advance_ms(eng, WIN_MS + 1)
    assert eng.state == SHOWING
    assert len(eng.sequence) == orig_len + 1


def test_high_score_tracks_best():
    eng = SimonEngine(start_length=1)
    _tick(eng, btn=0)

    step_ms = SHOW_STEP_MS + SHOW_GAP_MS

    # Complete first round
    _advance_ms(eng, step_ms + 1)
    _tick(eng, btn=eng.sequence[0])
    assert eng.high_score == 1

    # Advance past WIN into round 2 showing
    _advance_ms(eng, WIN_MS + 1)
    assert eng.state == SHOWING

    # Advance past showing of 2-step sequence
    _advance_ms(eng, 2 * step_ms + 1)
    assert eng.state == WAITING

    _tick(eng, btn=eng.sequence[0])
    _tick(eng, btn=eng.sequence[1])
    assert eng.high_score == 2


def test_max_fails_triggers_game_over():
    eng = SimonEngine(start_length=1)
    _tick(eng, btn=0)

    step_ms = SHOW_STEP_MS + SHOW_GAP_MS

    for i in range(MAX_FAILS):
        # Advance to WAITING
        if eng.state == SHOWING:
            _advance_ms(eng, step_ms + 1)
        assert eng.state == WAITING, (
            f"Expected WAITING on fail #{i + 1}, got {eng.state}"
        )

        # Press wrong button
        expected = eng.sequence[0]
        wrong = (expected + 1) % NUM_BUTTONS
        _tick(eng, btn=wrong)
        assert eng.state == FAIL

        # Advance past fail duration
        _advance_ms(eng, FAIL_MS + 1)

    assert eng.state == GAME_OVER


def test_game_over_restarts_on_press():
    eng = SimonEngine(start_length=1)
    eng.state = GAME_OVER
    eng._state_ms = 0

    _tick(eng, btn=0)
    assert eng.state == SHOWING
    assert len(eng.sequence) == 1


def test_active_button_during_showing():
    eng = SimonEngine(start_length=2)
    _tick(eng, btn=0)
    assert eng.state == SHOWING

    # During the first step, active_button should be sequence[0]
    _advance_ms(eng, SHOW_STEP_MS // 2)
    assert eng.active_button == eng.sequence[0]

    # During the gap, active_button should be -1
    _advance_ms(eng, SHOW_STEP_MS // 2 + 10)
    assert eng.active_button == -1


def test_make_leds_returns_n_leds():
    from bodn.patterns import N_LEDS

    eng = SimonEngine()
    for state_setup in [
        lambda: None,  # READY
        lambda: _tick(eng, btn=0),  # SHOWING
    ]:
        eng.reset()
        state_setup()
        leds = eng.make_leds(frame=5, brightness=128)
        assert len(leds) == N_LEDS  # buffer is full size


def test_make_leds_win_is_colorful():
    from bodn.patterns import N_STICKS

    eng = SimonEngine()
    eng.state = WIN
    eng._state_ms = 0
    leds = eng.make_leds(frame=10, brightness=200)
    # Stick LEDs should have diverse colors (rainbow)
    unique = set(leds[:N_STICKS])
    assert len(unique) > 1


def test_no_button_press_stays_in_state():
    eng = SimonEngine()
    _tick(eng)
    assert eng.state == READY

    _tick(eng, btn=0)
    assert eng.state == SHOWING
    _tick(eng)
    assert eng.state == SHOWING


def test_input_progress():
    eng = SimonEngine(start_length=2)
    _tick(eng, btn=0)

    step_ms = SHOW_STEP_MS + SHOW_GAP_MS
    _advance_ms(eng, 2 * step_ms + 1)
    assert eng.state == WAITING
    assert eng.input_progress == 0.0

    _tick(eng, btn=eng.sequence[0])
    assert eng.input_progress == 0.5


def test_reset_clears_state():
    eng = SimonEngine()
    _tick(eng, btn=0)
    eng.score = 5
    eng.high_score = 10

    eng.reset()
    assert eng.state == READY
    assert eng.score == 0
    assert eng.sequence == []
    # high_score is also reset (new game)
    assert eng.high_score == 0
