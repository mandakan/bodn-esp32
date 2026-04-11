"""Tests for the High-Five Friends game engine (pure logic)."""

import pytest

from bodn.highfive_rules import (
    HighFiveEngine,
    READY,
    SHOWING,
    HIT_FLASH,
    MISS_FLASH,
    GAME_OVER,
    NUM_BUTTONS,
)

# -- helpers --

DT = 33  # default tick in ms (~30 fps)


def _tick(eng, dt=DT, hit=False, miss=False):
    """Advance the engine by one tick."""
    return eng.advance(hit, miss, dt)


def _advance_ms(eng, ms, dt=DT):
    """Advance the engine by approximately *ms* milliseconds in dt-sized steps."""
    elapsed = 0
    while elapsed < ms:
        step = min(dt, ms - elapsed)
        eng.advance(False, False, step)
        elapsed += step


@pytest.fixture
def eng():
    e = HighFiveEngine()
    e.start()
    return e


class TestInitialState:
    def test_starts_in_ready(self, eng):
        assert eng.state == READY

    def test_initial_score(self, eng):
        assert eng.score == 0
        assert eng.streak == 0
        assert eng.misses == 0
        assert eng.round == 1

    def test_initial_window(self, eng):
        assert eng.window_ms == 2000


class TestReadyToShowing:
    def test_transitions_after_ready_ms(self, eng):
        # READY lasts 1500 ms
        _advance_ms(eng, 1400)
        assert eng.state == READY
        _advance_ms(eng, 200)  # total >= 1500
        assert eng.state == SHOWING
        assert 0 <= eng.target < NUM_BUTTONS


class TestHitDetection:
    def test_hit_advances_to_hit_flash(self, eng):
        # Get to SHOWING
        _advance_ms(eng, 1600)
        assert eng.state == SHOWING
        # Signal hit
        _tick(eng, hit=True)
        assert eng.state == HIT_FLASH
        assert eng.score == 1
        assert eng.streak == 1

    def test_hit_flash_returns_to_showing(self, eng):
        _advance_ms(eng, 1600)
        _tick(eng, hit=True)
        assert eng.state == HIT_FLASH
        # Wait out the flash duration (660 ms)
        _advance_ms(eng, 600)
        assert eng.state == HIT_FLASH
        _advance_ms(eng, 100)  # total >= 660
        assert eng.state == SHOWING


class TestMissDetection:
    def test_miss_advances_to_miss_flash(self, eng):
        _advance_ms(eng, 1600)
        assert eng.state == SHOWING
        _tick(eng, miss=True)
        assert eng.state == MISS_FLASH
        assert eng.misses == 1
        assert eng.streak == 0

    def test_three_misses_game_over(self, eng):
        for miss_num in range(3):
            # Get to SHOWING
            while eng.state != SHOWING:
                _tick(eng)
            # Miss
            _tick(eng, miss=True)
            assert eng.misses == miss_num + 1
            # Wait out MISS_FLASH (830 ms)
            _advance_ms(eng, 900)
        assert eng.state == GAME_OVER


class TestStreakTracking:
    def test_streak_increments_on_consecutive_hits(self, eng):
        for i in range(3):
            while eng.state != SHOWING:
                _tick(eng)
            _tick(eng, hit=True)
            assert eng.streak == i + 1

    def test_streak_resets_on_miss(self, eng):
        # Get 2 hits
        for _ in range(2):
            while eng.state != SHOWING:
                _tick(eng)
            _tick(eng, hit=True)
        assert eng.streak == 2
        # Wait for next SHOWING
        while eng.state != SHOWING:
            _tick(eng)
        # Miss
        _tick(eng, miss=True)
        assert eng.streak == 0

    def test_best_streak_tracked(self, eng):
        # Get 3 hits
        for _ in range(3):
            while eng.state != SHOWING:
                _tick(eng)
            _tick(eng, hit=True)
        assert eng.best_streak == 3
        # Miss resets streak but not best
        while eng.state != SHOWING:
            _tick(eng)
        _tick(eng, miss=True)
        assert eng.best_streak == 3


class TestDifficultyCurve:
    def test_window_shrinks_after_round(self, eng):
        initial = eng.window_ms
        # Complete 5 hits (one round) -- level-up happens when HIT_FLASH expires
        for _ in range(5):
            while eng.state != SHOWING:
                _tick(eng)
            _tick(eng, hit=True)
        # Wait through HIT_FLASH to trigger level-up
        _advance_ms(eng, 800)
        assert eng.round == 2
        assert eng.window_ms < initial

    def test_window_has_minimum(self, eng):
        # Force many rounds
        eng._window_ms = 600
        eng.round_hits = 4
        eng._level_up()
        assert eng.window_ms == 500  # minimum
        eng._level_up()
        assert eng.window_ms == 500  # can't go below

    def test_pulse_speed_increases_with_difficulty(self, eng):
        slow = eng.pulse_speed
        eng._window_ms = 600
        fast = eng.pulse_speed
        assert fast > slow


class TestTargetPicking:
    def test_target_in_valid_range(self, eng):
        _advance_ms(eng, 1600)
        assert 0 <= eng.target < NUM_BUTTONS

    def test_avoids_repeat(self, eng):
        """Target should usually differ from previous (not guaranteed but likely)."""
        _advance_ms(eng, 1600)
        targets = set()
        for _ in range(20):
            _tick(eng, hit=True)
            while eng.state != SHOWING:
                _tick(eng)
            targets.add(eng.target)
        # Should have seen more than 1 unique target
        assert len(targets) > 1


class TestGameOver:
    def test_game_over_auto_restarts(self, eng):
        eng.state = GAME_OVER
        eng._state_ms = 0
        # Wait for auto-restart (3000 ms)
        _advance_ms(eng, 3100)
        assert eng.state == READY
        assert eng.score == 0

    def test_high_score_saved(self, eng):
        eng.score = 10
        eng.misses = 2
        eng.state = SHOWING
        eng._state_ms = 0
        # Third miss triggers game over
        _tick(eng, miss=True)
        # Wait through MISS_FLASH (830 ms)
        _advance_ms(eng, 900)
        assert eng.state == GAME_OVER
        assert eng.high_score == 10
