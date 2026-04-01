"""Tests for the sequencer engine (pure logic, no hardware)."""

from bodn.sequencer_rules import (
    SequencerEngine,
    STOPPED,
    PLAYING,
    DEFAULT_BPM,
    MIN_BPM,
    MAX_BPM,
    BPM_STEP,
    NUM_PERC_TRACKS,
    MELODY_FREQS,
)


def test_initial_state():
    eng = SequencerEngine()
    assert eng.state == STOPPED
    assert eng.n_steps == 8
    assert eng.bpm == DEFAULT_BPM
    assert eng.step == 0
    assert all(eng.perc[t][s] == 0 for t in range(NUM_PERC_TRACKS) for s in range(8))
    assert all(eng.melody[s] == 0 for s in range(8))


def test_toggle_perc_on_off():
    eng = SequencerEngine()
    step, val = eng.toggle_perc(0, step=3)
    assert step == 3
    assert val == 1
    assert eng.perc[0][3] == 1

    step, val = eng.toggle_perc(0, step=3)
    assert val == 0
    assert eng.perc[0][3] == 0


def test_toggle_perc_independent_tracks():
    eng = SequencerEngine()
    eng.toggle_perc(0, step=2)
    eng.toggle_perc(1, step=2)
    assert eng.perc[0][2] == 1
    assert eng.perc[1][2] == 1
    assert eng.perc[2][2] == 0


def test_set_melody_and_erase():
    eng = SequencerEngine()
    # Set note on step 4 with button 2
    step, val = eng.set_melody(2, step=4)
    assert step == 4
    assert val == 3  # btn_idx + 1
    assert eng.melody[4] == 3

    # Same button erases
    step, val = eng.set_melody(2, step=4)
    assert val == 0
    assert eng.melody[4] == 0


def test_set_melody_overwrite():
    eng = SequencerEngine()
    eng.set_melody(2, step=4)
    assert eng.melody[4] == 3

    # Different button overwrites
    step, val = eng.set_melody(5, step=4)
    assert val == 6  # btn_idx + 1
    assert eng.melody[4] == 6


def test_advance_steps():
    eng = SequencerEngine(n_steps=8)
    eng.start()
    ms_per_step = eng._ms_per_step

    # Advance exactly one step
    advanced = eng.advance(ms_per_step)
    assert advanced is True
    assert eng.step == 1
    assert eng.step_advanced is True

    # Partial advance — should not tick
    advanced = eng.advance(ms_per_step // 2)
    assert advanced is False
    assert eng.step == 1

    # Complete the step
    advanced = eng.advance(ms_per_step - ms_per_step // 2)
    assert advanced is True
    assert eng.step == 2


def test_advance_wraps():
    eng = SequencerEngine(n_steps=4)
    eng.start()
    ms_per_step = eng._ms_per_step

    for _ in range(4):
        eng.advance(ms_per_step)
    assert eng.step == 0  # wrapped


def test_advance_stopped_does_nothing():
    eng = SequencerEngine()
    eng.advance(10000)
    assert eng.step == 0
    assert eng.step_advanced is False


def test_quantization():
    eng = SequencerEngine(n_steps=8)
    eng.start()
    ms_per_step = eng._ms_per_step

    # Advance to step 3 + 70% of next step (closer to step 4)
    eng.advance(ms_per_step * 3 + int(ms_per_step * 0.7))
    assert eng.nearest_step() == 4

    # Complete the remaining 30% to land on step 4
    eng.advance(ms_per_step - int(ms_per_step * 0.7))
    assert eng.step == 4
    # Just past step boundary — nearest is still 4
    assert eng.nearest_step() == 4


def test_bpm_clamping():
    eng = SequencerEngine()
    eng.set_bpm(200)
    assert eng.bpm == MAX_BPM

    eng.set_bpm(30)
    assert eng.bpm == MIN_BPM

    eng.set_bpm(100)
    assert eng.bpm == 100


def test_set_steps_8_to_16():
    eng = SequencerEngine(n_steps=8)
    eng.toggle_perc(0, step=0)
    eng.toggle_perc(0, step=4)
    eng.set_melody(3, step=2)

    eng.set_steps(16)
    assert eng.n_steps == 16
    assert len(eng.perc[0]) == 16
    assert len(eng.melody) == 16

    # First half preserved
    assert eng.perc[0][0] == 1
    assert eng.perc[0][4] == 1
    assert eng.melody[2] == 4

    # Second half is duplicate of first
    assert eng.perc[0][8] == 1
    assert eng.perc[0][12] == 1
    assert eng.melody[10] == 4


def test_set_steps_16_to_8():
    eng = SequencerEngine(n_steps=16)
    eng.toggle_perc(0, step=2)
    eng.toggle_perc(0, step=14)  # will be truncated

    eng.set_steps(8)
    assert eng.n_steps == 8
    assert len(eng.perc[0]) == 8
    assert eng.perc[0][2] == 1
    # Step 14 is gone
    assert all(eng.perc[0][s] == 0 for s in range(8) if s != 2)


def test_set_steps_same_is_noop():
    eng = SequencerEngine(n_steps=8)
    eng.toggle_perc(0, step=3)
    eng.set_steps(8)
    assert eng.perc[0][3] == 1  # unchanged


def test_clear_all():
    eng = SequencerEngine()
    eng.toggle_perc(0, step=1)
    eng.toggle_perc(2, step=5)
    eng.set_melody(4, step=3)
    eng.start()
    eng.advance(eng._ms_per_step * 3)

    eng.clear_all()
    assert eng.step == 0
    assert all(eng.perc[t][s] == 0 for t in range(NUM_PERC_TRACKS) for s in range(8))
    assert all(eng.melody[s] == 0 for s in range(8))


def test_get_step_sounds():
    eng = SequencerEngine()
    eng.toggle_perc(0, step=2)
    eng.toggle_perc(3, step=2)
    eng.set_melody(5, step=2)

    perc_active, mel_val = eng.get_step_sounds(2)
    assert perc_active == [True, False, False, True, False]
    assert mel_val == 6  # btn 5 + 1

    perc_active, mel_val = eng.get_step_sounds(0)
    assert perc_active == [False] * 5
    assert mel_val == 0


def test_start_stop():
    eng = SequencerEngine()
    assert eng.state == STOPPED

    eng.start()
    assert eng.state == PLAYING

    eng.stop()
    assert eng.state == STOPPED


def test_dirty_steps_tracked():
    eng = SequencerEngine()
    eng.toggle_perc(0, step=3)
    eng.set_melody(1, step=5)
    assert 3 in eng.dirty_steps
    assert 5 in eng.dirty_steps

    eng.dirty_steps.clear()
    assert len(eng.dirty_steps) == 0


def test_toggle_perc_uses_nearest_step():
    """When no explicit step is given, toggle_perc uses quantized position."""
    eng = SequencerEngine(n_steps=8)
    eng.start()
    # Advance to step 2
    eng.advance(eng._ms_per_step * 2)
    assert eng.step == 2

    step, val = eng.toggle_perc(0)
    assert step == 2
    assert val == 1


def test_melody_freqs_length():
    assert len(MELODY_FREQS) == 8


def test_timing_formula():
    eng = SequencerEngine(n_steps=8)
    eng.set_bpm(90)
    # 60000 * 4 / (90 * 8) = 333ms
    assert eng._ms_per_step == 333

    eng.set_bpm(120)
    # 60000 * 4 / (120 * 8) = 250ms
    assert eng._ms_per_step == 250

    eng16 = SequencerEngine(n_steps=16)
    eng16.set_bpm(90)
    # 60000 * 4 / (90 * 16) = 166ms
    assert eng16._ms_per_step == 166
