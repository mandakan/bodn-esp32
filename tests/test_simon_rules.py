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
    SHOW_STEP_FRAMES,
    SHOW_GAP_FRAMES,
    WIN_FRAMES,
    FAIL_FRAMES,
    MAX_FAILS,
    NUM_BUTTONS,
    BTN_COLORS,
)


def test_initial_state_is_ready():
    eng = SimonEngine()
    assert eng.state == READY
    assert eng.score == 0
    assert eng.high_score == 0
    assert eng.sequence == []


def test_any_button_starts_game():
    eng = SimonEngine()
    eng.update(0, frame=1)
    assert eng.state == SHOWING
    assert len(eng.sequence) == 2  # default start_length


def test_custom_start_length():
    eng = SimonEngine(start_length=3)
    eng.update(0, frame=1)
    assert len(eng.sequence) == 3


def test_sequence_uses_valid_buttons():
    eng = SimonEngine()
    eng.update(0, frame=1)
    for btn in eng.sequence:
        assert 0 <= btn < NUM_BUTTONS


def test_showing_transitions_to_waiting():
    eng = SimonEngine(start_length=1)
    eng.update(0, frame=0)
    assert eng.state == SHOWING

    # Advance past the single step (show + gap)
    step_total = SHOW_STEP_FRAMES + SHOW_GAP_FRAMES
    eng.update(-1, frame=step_total + 1)
    assert eng.state == WAITING


def test_correct_button_advances():
    eng = SimonEngine(start_length=1)
    eng.update(0, frame=0)

    # Skip through showing phase
    step_total = SHOW_STEP_FRAMES + SHOW_GAP_FRAMES
    eng.update(-1, frame=step_total + 1)
    assert eng.state == WAITING

    # Press the correct button
    expected = eng.sequence[0]
    eng.update(expected, frame=step_total + 10)
    assert eng.state == WIN
    assert eng.score == 1


def test_wrong_button_fails():
    eng = SimonEngine(start_length=1)
    eng.update(0, frame=0)

    step_total = SHOW_STEP_FRAMES + SHOW_GAP_FRAMES
    eng.update(-1, frame=step_total + 1)
    assert eng.state == WAITING

    # Press a wrong button
    expected = eng.sequence[0]
    wrong = (expected + 1) % NUM_BUTTONS
    eng.update(wrong, frame=step_total + 10)
    assert eng.state == FAIL


def test_fail_replays_sequence():
    eng = SimonEngine(start_length=1)
    eng.update(0, frame=0)

    step_total = SHOW_STEP_FRAMES + SHOW_GAP_FRAMES
    eng.update(-1, frame=step_total + 1)

    expected = eng.sequence[0]
    wrong = (expected + 1) % NUM_BUTTONS
    fail_frame = step_total + 10
    eng.update(wrong, frame=fail_frame)
    assert eng.state == FAIL

    # After FAIL_FRAMES, should go back to SHOWING (same sequence)
    seq_before = list(eng.sequence)
    eng.update(-1, frame=fail_frame + FAIL_FRAMES + 1)
    assert eng.state == SHOWING
    assert eng.sequence == seq_before  # same sequence replayed


def test_win_grows_sequence():
    eng = SimonEngine(start_length=1)
    eng.update(0, frame=0)
    orig_len = len(eng.sequence)

    step_total = SHOW_STEP_FRAMES + SHOW_GAP_FRAMES
    eng.update(-1, frame=step_total + 1)

    expected = eng.sequence[0]
    win_frame = step_total + 10
    eng.update(expected, frame=win_frame)
    assert eng.state == WIN

    # After WIN_FRAMES, sequence should grow and start showing
    eng.update(-1, frame=win_frame + WIN_FRAMES + 1)
    assert eng.state == SHOWING
    assert len(eng.sequence) == orig_len + 1


def test_high_score_tracks_best():
    eng = SimonEngine(start_length=1)
    eng.update(0, frame=0)

    # Complete first round
    step_total = SHOW_STEP_FRAMES + SHOW_GAP_FRAMES
    eng.update(-1, frame=step_total + 1)
    eng.update(eng.sequence[0], frame=step_total + 10)
    assert eng.high_score == 1

    # Complete second round
    f = step_total + 10 + WIN_FRAMES + 1
    eng.update(-1, frame=f)  # starts showing round 2
    f2 = f + 2 * step_total + 1
    eng.update(-1, frame=f2)  # done showing
    assert eng.state == WAITING
    eng.update(eng.sequence[0], frame=f2 + 1)
    eng.update(eng.sequence[1], frame=f2 + 5)
    assert eng.high_score == 2


def test_max_fails_triggers_game_over():
    eng = SimonEngine(start_length=1)
    eng.update(0, frame=0)

    step_total = SHOW_STEP_FRAMES + SHOW_GAP_FRAMES
    frame = step_total + 1

    for i in range(MAX_FAILS):
        # Advance to WAITING
        eng.update(-1, frame=frame)
        if eng.state == SHOWING:
            frame += step_total + 1
            eng.update(-1, frame=frame)
        assert eng.state == WAITING, (
            f"Expected WAITING on fail #{i + 1}, got {eng.state}"
        )

        # Press wrong button
        expected = eng.sequence[0]
        wrong = (expected + 1) % NUM_BUTTONS
        eng.update(wrong, frame=frame + 1)
        assert eng.state == FAIL
        frame = frame + 1 + FAIL_FRAMES + 1

    eng.update(-1, frame=frame)
    assert eng.state == GAME_OVER


def test_game_over_restarts_on_press():
    eng = SimonEngine(start_length=1)
    eng.state = GAME_OVER
    eng._state_frame = 0

    eng.update(0, frame=100)
    assert eng.state == SHOWING
    assert len(eng.sequence) == 1


def test_active_button_during_showing():
    eng = SimonEngine(start_length=2)
    eng.update(0, frame=0)
    assert eng.state == SHOWING

    # During the first step, active_button should be sequence[0]
    eng.update(-1, frame=5)
    assert eng.active_button == eng.sequence[0]

    # During the gap, active_button should be -1
    eng.update(-1, frame=SHOW_STEP_FRAMES + 2)
    assert eng.active_button == -1


def test_make_leds_returns_n_leds():
    from bodn.patterns import N_LEDS

    eng = SimonEngine()
    for state_setup in [
        lambda: None,  # READY
        lambda: eng.update(0, frame=0),  # SHOWING
    ]:
        eng.reset()
        state_setup()
        leds = eng.make_leds(frame=5, brightness=128)
        assert len(leds) == N_LEDS


def test_make_leds_win_is_colorful():
    from bodn.patterns import N_LEDS

    eng = SimonEngine()
    eng.state = WIN
    eng._state_frame = 0
    leds = eng.make_leds(frame=10, brightness=200)
    # Should have diverse colors (rainbow)
    unique = set(leds)
    assert len(unique) > 1


def test_no_button_press_stays_in_state():
    eng = SimonEngine()
    eng.update(-1, frame=1)
    assert eng.state == READY

    eng.update(0, frame=5)
    assert eng.state == SHOWING
    eng.update(-1, frame=6)
    assert eng.state == SHOWING


def test_input_progress():
    eng = SimonEngine(start_length=2)
    eng.update(0, frame=0)

    step_total = SHOW_STEP_FRAMES + SHOW_GAP_FRAMES
    frame = 2 * step_total + 1
    eng.update(-1, frame=frame)
    assert eng.state == WAITING
    assert eng.input_progress == 0.0

    eng.update(eng.sequence[0], frame=frame + 5)
    assert eng.input_progress == 0.5


def test_reset_clears_state():
    eng = SimonEngine()
    eng.update(0, frame=0)
    eng.score = 5
    eng.high_score = 10

    eng.reset()
    assert eng.state == READY
    assert eng.score == 0
    assert eng.sequence == []
    # high_score is also reset (new game)
    assert eng.high_score == 0
