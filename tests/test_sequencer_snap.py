"""Tests for Sequencer live-input quantization (_snap_step).

The snap maps a button-press timestamp (captured by the input scanner
and preserved all the way through consume()) to the nearest grid step.
It uses the C clock's fractional position (via clock_get_pos) and
subtracts _REC_OFFSET_MS so the snap target matches what the user
heard at the moment of pressing.
"""

from bodn.sequencer_rules import PLAYING, STOPPED
from bodn.ui.sequencer import SequencerScreen, _REC_OFFSET_MS


def _make_screen_playing(bpm=90, n_steps=8, frac=0.0):
    """Build a SequencerScreen with its engine forced into PLAYING state
    at a known fractional playhead position, without invoking enter()."""
    s = SequencerScreen(overlay=None)
    eng = s._engine
    eng.set_bpm(bpm)
    if n_steps != eng.n_steps:
        eng.set_steps(n_steps)
    eng.state = PLAYING
    eng.step = int(frac) % n_steps
    eng._frac = frac
    return s


def test_snap_falls_back_when_stopped():
    s = SequencerScreen(overlay=None)
    assert s._engine.state == STOPPED
    # Regardless of timestamps, a stopped clock uses nearest_step() = 0.
    assert s._snap_step(press_ts_ms=0, now_ms=0) == 0


def test_snap_same_instant_compensates_audio_latency():
    """A press whose timestamp equals 'now' still gets the rec-offset
    pushed back in time, so at frac=0 a late-ish press snaps to the
    previous step (n_steps - 1)."""
    s = _make_screen_playing(bpm=90, frac=0.0)
    ms_per_step = s._engine._ms_per_step  # 333ms at 90bpm
    assert ms_per_step > _REC_OFFSET_MS  # sanity
    # press_ts == now → age = _REC_OFFSET_MS (≈20ms).
    # frac_at_press = 0 - 20/333 = -0.06 → wraps to ~7.94 in an 8-step grid
    # → rounds to step 0 again (snap does not "jump backwards" for a
    # press essentially on the downbeat).
    assert s._snap_step(press_ts_ms=100, now_ms=100) == 0


def test_snap_rounds_forward_when_past_midpoint():
    """A press 60% of the way through step 2 should snap to step 3,
    not step 2 — this is the behaviour the old floor-snap lacked."""
    s = _make_screen_playing(bpm=90, frac=2.6)
    # Fresh press — compensate only the rec offset, which at 90 BPM is
    # 20/333 ≈ 0.06 step back → 2.54 → rounds to 3.
    assert s._snap_step(press_ts_ms=100, now_ms=100) == 3


def test_snap_uses_old_timestamp_to_undo_frame_delay():
    """The timestamp comes from the 500Hz scanner, but the UI frame may
    run ~16ms later.  Using ts_ms recovers the original snap target."""
    s = _make_screen_playing(bpm=90, frac=3.15)
    # Assume the scanner saw the press 50ms ago; subtracting 50ms + 20ms
    # rec offset → 70/333 ≈ 0.21 step back → 2.94 → rounds to step 3.
    assert s._snap_step(press_ts_ms=30, now_ms=100) == 3


def test_snap_wraps_across_loop_boundary():
    """A press late in step 7 of an 8-step loop, where the playhead has
    already wrapped to a tiny positive frac in the new bar, must still
    snap to the logical target (step 0)."""
    s = _make_screen_playing(bpm=90, n_steps=8, frac=0.1)
    # frac_at_press = 0.1 - 20/333 ≈ 0.04 → rounds to step 0.  Good.
    assert s._snap_step(press_ts_ms=100, now_ms=100) == 0

    # Same scenario but with a real delay: 50ms ago, frac=0.1
    # frac_at_press = 0.1 - 70/333 ≈ -0.11 → wraps to ~7.89 → rounds to 0
    # (since 7.89 rounds up to 8 → mod 8 = 0).
    assert s._snap_step(press_ts_ms=50, now_ms=100) == 0


def test_snap_wraps_to_last_step_when_press_earlier_in_bar():
    """A press whose back-compensated position lands unambiguously in
    the previous bar must resolve to the correct modular step index."""
    s = _make_screen_playing(bpm=90, n_steps=8, frac=0.1)
    # 200ms ago → 0.1 - 220/333 ≈ -0.56 → wraps to ~7.44 → rounds to 7.
    assert s._snap_step(press_ts_ms=0, now_ms=200) == 7


def test_snap_still_works_in_16_step_grid():
    s = _make_screen_playing(bpm=120, n_steps=16, frac=10.7)
    # 120bpm → ms_per_step = 60000/(120*2) = 250ms
    # frac_at_press = 10.7 - 20/250 = 10.62 → rounds to 11.
    assert s._snap_step(press_ts_ms=0, now_ms=0) == 11
