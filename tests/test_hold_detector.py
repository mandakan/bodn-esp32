# tests/test_hold_detector.py — host-side tests for the HoldDetector

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "firmware"))

from bodn.hold_detector import HoldDetector


def test_initial_state():
    hd = HoldDetector()
    assert not hd.holding
    assert not hd.triggered
    assert hd.progress == 0.0


def test_not_triggered_before_threshold():
    hd = HoldDetector(threshold_ms=1000)
    hd.update(True, 0)
    hd.update(True, 500)
    assert hd.holding
    assert not hd.triggered
    assert 0.4 < hd.progress < 0.6


def test_triggered_at_threshold():
    hd = HoldDetector(threshold_ms=1000)
    hd.update(True, 0)
    result = hd.update(True, 1000)
    assert result is True
    assert hd.triggered
    assert hd.progress == 1.0


def test_triggered_fires_once():
    hd = HoldDetector(threshold_ms=1000)
    hd.update(True, 0)
    hd.update(True, 1000)
    assert hd.triggered

    # Next update with still held — triggered should be False
    hd.update(True, 1200)
    assert not hd.triggered
    assert hd.holding


def test_release_resets_progress():
    hd = HoldDetector(threshold_ms=1000)
    hd.update(True, 0)
    hd.update(True, 500)
    assert hd.progress > 0

    hd.update(False, 600)
    assert not hd.holding
    assert hd.progress == 0.0


def test_release_before_threshold_no_trigger():
    hd = HoldDetector(threshold_ms=1000)
    hd.update(True, 0)
    hd.update(True, 800)
    hd.update(False, 900)
    assert not hd.triggered


def test_second_hold_after_release():
    hd = HoldDetector(threshold_ms=1000)
    # First hold — release early
    hd.update(True, 0)
    hd.update(True, 500)
    hd.update(False, 600)

    # Second hold — complete
    hd.update(True, 1000)
    hd.update(True, 2000)
    assert hd.triggered


def test_reset_clears_state():
    hd = HoldDetector(threshold_ms=1000)
    hd.update(True, 0)
    hd.update(True, 1000)
    assert hd.triggered

    hd.reset()
    assert not hd.holding
    assert not hd.triggered
    assert hd.progress == 0.0


def test_progress_is_clamped():
    hd = HoldDetector(threshold_ms=1000)
    hd.update(True, 0)
    hd.update(True, 5000)  # Way past threshold
    assert hd.progress == 1.0


def test_custom_threshold():
    hd = HoldDetector(threshold_ms=500)
    hd.update(True, 0)
    assert not hd.triggered
    hd.update(True, 500)
    assert hd.triggered


def test_default_threshold():
    hd = HoldDetector()
    assert hd.threshold_ms == 1500
