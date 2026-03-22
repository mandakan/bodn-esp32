"""Tests for GestureDetector — tap, double-tap, long-press detection."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "firmware"))

from bodn.gesture import GestureDetector


def make(n=3, long_press_ms=1000, double_tap_ms=250):
    """Create a detector with sensible test defaults."""
    return GestureDetector(n, long_press_ms=long_press_ms, double_tap_ms=double_tap_ms)


def step(gd, held, pressed, released, now):
    """Convenience: update with plain lists."""
    gd.update(held, pressed, released, now)


# --- Initial state ---


def test_initial_state():
    gd = make()
    for i in range(3):
        assert not gd.tap[i]
        assert not gd.double_tap[i]
        assert not gd.long_press[i]
        assert not gd.holding[i]
        assert not gd.released[i]
        assert gd.long_progress[i] == 0.0


# --- Tap (double-tap disabled = default) ---


def test_tap_fires_on_release():
    """With double-tap disabled (default), tap fires immediately on release."""
    gd = make()
    # Press
    step(gd, [True, False, False], [True, False, False], [False, False, False], 0)
    assert not gd.tap[0]
    assert gd.holding[0]

    # Release at 100ms (well under long-press threshold)
    step(gd, [False, False, False], [False, False, False], [True, False, False], 100)
    assert gd.tap[0]
    assert gd.released[0]


def test_tap_is_one_shot():
    gd = make()
    step(gd, [True, False, False], [True, False, False], [False, False, False], 0)
    step(gd, [False, False, False], [False, False, False], [True, False, False], 100)
    assert gd.tap[0]

    # Next frame — tap should be cleared
    step(gd, [False, False, False], [False, False, False], [False, False, False], 150)
    assert not gd.tap[0]


def test_no_tap_after_long_press():
    """If button was held past threshold, release should NOT fire tap."""
    gd = make(long_press_ms=500)
    step(gd, [True, False, False], [True, False, False], [False, False, False], 0)
    step(gd, [True, False, False], [False, False, False], [False, False, False], 500)
    assert gd.long_press[0]

    # Release after long press
    step(gd, [False, False, False], [False, False, False], [True, False, False], 600)
    assert not gd.tap[0]
    assert gd.released[0]


# --- Double-tap ---


def test_double_tap():
    gd = make(double_tap_ms=300)
    gd.set_double_tap(0, True)

    # First press + release
    step(gd, [True, False, False], [True, False, False], [False, False, False], 0)
    step(gd, [False, False, False], [False, False, False], [True, False, False], 80)
    assert not gd.tap[0]  # waiting for possible second tap

    # Second press + release within window
    step(gd, [True, False, False], [True, False, False], [False, False, False], 150)
    step(gd, [False, False, False], [False, False, False], [True, False, False], 220)
    assert gd.double_tap[0]
    assert not gd.tap[0]


def test_double_tap_window_expiry_falls_back_to_tap():
    gd = make(double_tap_ms=200)
    gd.set_double_tap(0, True)

    # Press + release
    step(gd, [True, False, False], [True, False, False], [False, False, False], 0)
    step(gd, [False, False, False], [False, False, False], [True, False, False], 80)
    assert not gd.tap[0]

    # No second press — window expires
    step(gd, [False, False, False], [False, False, False], [False, False, False], 300)
    assert gd.tap[0]
    assert not gd.double_tap[0]


def test_double_tap_disabled_gives_immediate_tap():
    """Default: double-tap disabled, tap fires on release without delay."""
    gd = make(double_tap_ms=300)
    # Channel 0 double-tap is disabled by default
    step(gd, [True, False, False], [True, False, False], [False, False, False], 0)
    step(gd, [False, False, False], [False, False, False], [True, False, False], 80)
    assert gd.tap[0]  # immediate


# --- Long press ---


def test_long_press_fires_at_threshold():
    gd = make(long_press_ms=500)
    step(gd, [True, False, False], [True, False, False], [False, False, False], 0)
    # Not yet
    step(gd, [True, False, False], [False, False, False], [False, False, False], 400)
    assert not gd.long_press[0]
    assert 0.7 < gd.long_progress[0] < 0.9

    # At threshold
    step(gd, [True, False, False], [False, False, False], [False, False, False], 500)
    assert gd.long_press[0]
    assert gd.long_progress[0] == 1.0


def test_long_press_fires_once():
    gd = make(long_press_ms=500)
    step(gd, [True, False, False], [True, False, False], [False, False, False], 0)
    step(gd, [True, False, False], [False, False, False], [False, False, False], 500)
    assert gd.long_press[0]

    # Continued hold — should not re-fire
    step(gd, [True, False, False], [False, False, False], [False, False, False], 700)
    assert not gd.long_press[0]
    assert gd.holding[0]


def test_long_progress_ramps():
    gd = make(long_press_ms=1000)
    step(gd, [True, False, False], [True, False, False], [False, False, False], 0)

    step(gd, [True, False, False], [False, False, False], [False, False, False], 250)
    assert abs(gd.long_progress[0] - 0.25) < 0.01

    step(gd, [True, False, False], [False, False, False], [False, False, False], 500)
    assert abs(gd.long_progress[0] - 0.5) < 0.01

    step(gd, [True, False, False], [False, False, False], [False, False, False], 750)
    assert abs(gd.long_progress[0] - 0.75) < 0.01


def test_progress_resets_on_release():
    gd = make(long_press_ms=1000)
    step(gd, [True, False, False], [True, False, False], [False, False, False], 0)
    step(gd, [True, False, False], [False, False, False], [False, False, False], 500)
    assert gd.long_progress[0] > 0

    step(gd, [False, False, False], [False, False, False], [True, False, False], 600)
    # After tap fires and returns to idle, progress is 0
    assert gd.long_progress[0] == 0.0


def test_progress_clamped_at_1():
    gd = make(long_press_ms=500)
    step(gd, [True, False, False], [True, False, False], [False, False, False], 0)
    step(gd, [True, False, False], [False, False, False], [False, False, False], 5000)
    assert gd.long_progress[0] == 1.0


# --- Release ---


def test_released_tracks_just_released():
    gd = make()
    step(gd, [True, False, False], [True, False, False], [False, False, False], 0)
    assert not gd.released[0]

    step(gd, [False, False, False], [False, False, False], [True, False, False], 100)
    assert gd.released[0]

    step(gd, [False, False, False], [False, False, False], [False, False, False], 200)
    assert not gd.released[0]


# --- Channel independence ---


def test_channels_independent():
    gd = make(n=3, long_press_ms=500)
    # Press channel 0 only
    step(gd, [True, False, False], [True, False, False], [False, False, False], 0)
    assert gd.holding[0]
    assert not gd.holding[1]
    assert not gd.holding[2]

    # Long-press fires on channel 0 only
    step(gd, [True, False, False], [False, False, False], [False, False, False], 500)
    assert gd.long_press[0]
    assert not gd.long_press[1]

    # Tap on channel 1
    step(gd, [True, True, False], [False, True, False], [False, False, False], 600)
    step(gd, [True, False, False], [False, False, False], [False, True, False], 700)
    assert gd.tap[1]
    assert not gd.tap[0]


# --- Reset ---


def test_reset_clears_all():
    gd = make(long_press_ms=500)
    step(gd, [True, False, False], [True, False, False], [False, False, False], 0)
    step(gd, [True, False, False], [False, False, False], [False, False, False], 500)
    assert gd.long_press[0]

    gd.reset()
    for i in range(3):
        assert not gd.tap[i]
        assert not gd.double_tap[i]
        assert not gd.long_press[i]
        assert not gd.holding[i]
        assert gd.long_progress[i] == 0.0


def test_reset_channel():
    gd = make(long_press_ms=500)
    step(gd, [True, True, False], [True, True, False], [False, False, False], 0)
    step(gd, [True, True, False], [False, False, False], [False, False, False], 500)
    assert gd.long_press[0]
    assert gd.long_press[1]

    gd.reset_channel(0)
    assert not gd.long_press[0]
    assert gd.long_progress[0] == 0.0
    # Channel 1 unaffected (one-shot already consumed, but state remains PRESSED)
    assert gd.holding[1]


# --- Custom thresholds ---


def test_custom_long_press_threshold():
    gd = make(long_press_ms=200)
    step(gd, [True, False, False], [True, False, False], [False, False, False], 0)
    step(gd, [True, False, False], [False, False, False], [False, False, False], 200)
    assert gd.long_press[0]


def test_custom_double_tap_window():
    gd = make(double_tap_ms=100)
    gd.set_double_tap(0, True)

    step(gd, [True, False, False], [True, False, False], [False, False, False], 0)
    step(gd, [False, False, False], [False, False, False], [True, False, False], 50)

    # Second press within 100ms window
    step(gd, [True, False, False], [True, False, False], [False, False, False], 80)
    step(gd, [False, False, False], [False, False, False], [True, False, False], 120)
    assert gd.double_tap[0]


def test_double_tap_window_too_slow():
    gd = make(double_tap_ms=100)
    gd.set_double_tap(0, True)

    step(gd, [True, False, False], [True, False, False], [False, False, False], 0)
    step(gd, [False, False, False], [False, False, False], [True, False, False], 50)

    # Too slow — window expires before second press
    step(gd, [False, False, False], [False, False, False], [False, False, False], 200)
    assert gd.tap[0]  # falls back to single tap


# --- Second hold after release ---


def test_second_hold_after_release():
    gd = make(long_press_ms=500)
    # First hold — release early
    step(gd, [True, False, False], [True, False, False], [False, False, False], 0)
    step(gd, [False, False, False], [False, False, False], [True, False, False], 200)
    assert gd.tap[0]

    # Second hold — complete
    step(gd, [True, False, False], [True, False, False], [False, False, False], 500)
    step(gd, [True, False, False], [False, False, False], [False, False, False], 1000)
    assert gd.long_press[0]


# --- Holding flag ---


def test_holding_tracks_physical_state():
    gd = make()
    step(gd, [False, False, False], [False, False, False], [False, False, False], 0)
    assert not gd.holding[0]

    step(gd, [True, False, False], [True, False, False], [False, False, False], 100)
    assert gd.holding[0]

    step(gd, [True, False, False], [False, False, False], [False, False, False], 200)
    assert gd.holding[0]

    step(gd, [False, False, False], [False, False, False], [True, False, False], 300)
    assert not gd.holding[0]
