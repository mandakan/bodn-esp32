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


@pytest.fixture
def eng():
    e = HighFiveEngine()
    e.start(0)
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
    def test_transitions_after_ready_frames(self, eng):
        # READY lasts ~45 frames
        for f in range(1, 45):
            eng.advance(False, False, f)
        assert eng.state == READY
        eng.advance(False, False, 45)
        assert eng.state == SHOWING
        assert 0 <= eng.target < NUM_BUTTONS


class TestHitDetection:
    def test_hit_advances_to_hit_flash(self, eng):
        # Get to SHOWING
        eng.advance(False, False, 50)
        assert eng.state == SHOWING
        # Signal hit
        eng.advance(True, False, 51)
        assert eng.state == HIT_FLASH
        assert eng.score == 1
        assert eng.streak == 1

    def test_hit_flash_returns_to_showing(self, eng):
        eng.advance(False, False, 50)
        eng.advance(True, False, 51)
        assert eng.state == HIT_FLASH
        # Wait out the flash duration (20 frames)
        for f in range(52, 72):
            eng.advance(False, False, f)
        assert eng.state == HIT_FLASH or eng.state == SHOWING
        # Should definitely be SHOWING after enough frames
        eng.advance(False, False, 72)
        assert eng.state == SHOWING


class TestMissDetection:
    def test_miss_advances_to_miss_flash(self, eng):
        eng.advance(False, False, 50)
        assert eng.state == SHOWING
        eng.advance(False, True, 51)
        assert eng.state == MISS_FLASH
        assert eng.misses == 1
        assert eng.streak == 0

    def test_three_misses_game_over(self, eng):
        frame = 50
        for miss_num in range(3):
            # Get to SHOWING
            while eng.state != SHOWING:
                eng.advance(False, False, frame)
                frame += 1
            # Miss
            eng.advance(False, True, frame)
            frame += 1
            assert eng.misses == miss_num + 1
            # Wait out MISS_FLASH
            for _ in range(30):
                eng.advance(False, False, frame)
                frame += 1
        assert eng.state == GAME_OVER


class TestStreakTracking:
    def test_streak_increments_on_consecutive_hits(self, eng):
        frame = 50
        for i in range(3):
            while eng.state != SHOWING:
                eng.advance(False, False, frame)
                frame += 1
            eng.advance(True, False, frame)
            frame += 1
            assert eng.streak == i + 1

    def test_streak_resets_on_miss(self, eng):
        frame = 50
        # Get 2 hits
        for _ in range(2):
            while eng.state != SHOWING:
                eng.advance(False, False, frame)
                frame += 1
            eng.advance(True, False, frame)
            frame += 1
        assert eng.streak == 2
        # Wait for next SHOWING
        while eng.state != SHOWING:
            eng.advance(False, False, frame)
            frame += 1
        # Miss
        eng.advance(False, True, frame)
        assert eng.streak == 0

    def test_best_streak_tracked(self, eng):
        frame = 50
        # Get 3 hits
        for _ in range(3):
            while eng.state != SHOWING:
                eng.advance(False, False, frame)
                frame += 1
            eng.advance(True, False, frame)
            frame += 1
        assert eng.best_streak == 3
        # Miss resets streak but not best
        while eng.state != SHOWING:
            eng.advance(False, False, frame)
            frame += 1
        eng.advance(False, True, frame)
        assert eng.best_streak == 3


class TestDifficultyCurve:
    def test_window_shrinks_after_round(self, eng):
        initial = eng.window_ms
        frame = 50
        # Complete 5 hits (one round) — level-up happens when HIT_FLASH expires
        for _ in range(5):
            while eng.state != SHOWING:
                eng.advance(False, False, frame)
                frame += 1
            eng.advance(True, False, frame)
            frame += 1
        # Wait through HIT_FLASH to trigger level-up
        for _ in range(25):
            eng.advance(False, False, frame)
            frame += 1
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
        eng.advance(False, False, 50)
        assert 0 <= eng.target < NUM_BUTTONS

    def test_avoids_repeat(self, eng):
        """Target should usually differ from previous (not guaranteed but likely)."""
        eng.advance(False, False, 50)
        targets = set()
        frame = 51
        for _ in range(20):
            eng.advance(True, False, frame)
            frame += 1
            while eng.state != SHOWING:
                eng.advance(False, False, frame)
                frame += 1
            targets.add(eng.target)
        # Should have seen more than 1 unique target
        assert len(targets) > 1


class TestGameOver:
    def test_game_over_auto_restarts(self, eng):
        eng.state = GAME_OVER
        eng._state_frame = 0
        # Wait for auto-restart (90 frames)
        eng.advance(False, False, 91)
        assert eng.state == READY
        assert eng.score == 0

    def test_high_score_saved(self, eng):
        eng.score = 10
        eng.misses = 2
        eng.state = SHOWING
        eng._state_frame = 0
        # Third miss triggers game over
        eng.advance(False, True, 1)
        # Wait through MISS_FLASH
        for f in range(2, 30):
            eng.advance(False, False, f)
        assert eng.state == GAME_OVER
        assert eng.high_score == 10
