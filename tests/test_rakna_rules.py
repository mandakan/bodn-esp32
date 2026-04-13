"""Tests for bodn.rakna_rules — Rakna math game engine."""

import pytest
from bodn.rakna_rules import (
    RaknaEngine,
    WELCOME,
    ANNOUNCE,
    WAITING,
    CORRECT,
    WRONG,
    LEVEL_UP,
    WELCOME_MS,
    ANNOUNCE_MS,
    CORRECT_MS,
    WRONG_MS,
    LEVEL_UP_MS,
    DISCOVER_THRESHOLD,
    FIND_THRESHOLD,
    DEMO_CARDS,
    CHALLENGE_DISCOVER,
    CHALLENGE_FIND,
    CHALLENGE_MORE,
    CHALLENGE_LESS,
)

SAMPLE_CARD_SET = {
    "mode": "rakna",
    "version": 1,
    "cards": [
        {"id": "dots_1", "quantity": 1, "type": "number"},
        {"id": "dots_2", "quantity": 2, "type": "number"},
        {"id": "dots_3", "quantity": 3, "type": "number"},
        {"id": "dots_4", "quantity": 4, "type": "number"},
        {"id": "dots_5", "quantity": 5, "type": "number"},
        {"id": "dots_6", "quantity": 6, "type": "number"},
        {"id": "dots_7", "quantity": 7, "type": "number"},
        {"id": "dots_8", "quantity": 8, "type": "number"},
        {"id": "dots_9", "quantity": 9, "type": "number"},
        {"id": "dots_10", "quantity": 10, "type": "number"},
        {"id": "op_plus", "type": "operator", "operator": "+"},
        {"id": "op_minus", "type": "operator", "operator": "-"},
        {"id": "op_equals", "type": "operator", "operator": "="},
    ],
}


@pytest.fixture
def engine():
    return RaknaEngine(SAMPLE_CARD_SET)


@pytest.fixture
def engine_l2():
    """Engine starting at level 2."""
    return RaknaEngine(SAMPLE_CARD_SET, level=2)


@pytest.fixture
def engine_l3():
    """Engine starting at level 3."""
    return RaknaEngine(SAMPLE_CARD_SET, level=3)


def _to_waiting(engine):
    """Advance engine through WELCOME -> ANNOUNCE -> WAITING."""
    engine.update(None, WELCOME_MS)
    assert engine.state == ANNOUNCE
    engine.update(None, ANNOUNCE_MS)
    assert engine.state == WAITING


class TestInitialState:
    def test_starts_in_welcome(self, engine):
        assert engine.state == WELCOME

    def test_default_level_is_1(self, engine):
        assert engine.level == 1

    def test_score_is_zero(self, engine):
        assert engine.score == 0
        assert engine.streak == 0
        assert engine.best_streak == 0

    def test_custom_start_level(self, engine_l2):
        assert engine_l2.level == 2

    def test_level_clamped(self):
        eng = RaknaEngine(SAMPLE_CARD_SET, level=99)
        assert eng.level == 3
        eng = RaknaEngine(SAMPLE_CARD_SET, level=0)
        assert eng.level == 1


class TestWelcome:
    def test_auto_advances_to_announce(self, engine):
        engine.update(None, WELCOME_MS)
        assert engine.state == ANNOUNCE

    def test_stays_in_welcome_before_timeout(self, engine):
        engine.update(None, WELCOME_MS - 1)
        assert engine.state == WELCOME


class TestLevel1Discovery:
    def test_challenge_type_is_discover(self, engine):
        engine.update(None, WELCOME_MS)
        assert engine.challenge_type == CHALLENGE_DISCOVER

    def test_any_number_card_is_correct(self, engine):
        _to_waiting(engine)
        engine.update("dots_5", 0)
        assert engine.state == CORRECT
        assert engine.score == 1
        assert engine.last_card_quantity == 5

    def test_tracks_discovered_quantities(self, engine):
        _to_waiting(engine)
        engine.update("dots_3", 0)
        assert 3 in engine.discovered
        engine.update(None, CORRECT_MS)  # back to WAITING (level 1)
        engine.update("dots_7", 0)
        assert 7 in engine.discovered

    def test_operator_card_is_wrong(self, engine):
        _to_waiting(engine)
        engine.update("op_plus", 0)
        assert engine.state == WRONG
        assert engine.score == 0

    def test_unknown_card_is_wrong(self, engine):
        _to_waiting(engine)
        engine.update("nonexistent", 0)
        assert engine.state == WRONG

    def test_correct_returns_to_waiting_directly(self, engine):
        """Level 1: CORRECT -> WAITING (no new ANNOUNCE, it's free exploration)."""
        _to_waiting(engine)
        engine.update("dots_1", 0)
        assert engine.state == CORRECT
        engine.update(None, CORRECT_MS)
        assert engine.state == WAITING

    def test_level_up_after_enough_unique_scans(self, engine):
        _to_waiting(engine)
        for i in range(1, DISCOVER_THRESHOLD + 1):
            engine.update("dots_{}".format(i), 0)
            assert engine.state == CORRECT
            engine.update(None, CORRECT_MS)
            if i < DISCOVER_THRESHOLD:
                assert engine.state == WAITING

        # After threshold unique discoveries, should level up
        assert engine.state == LEVEL_UP

    def test_duplicate_scans_dont_count_as_new_discoveries(self, engine):
        _to_waiting(engine)
        for _ in range(10):
            engine.update("dots_1", 0)
            engine.update(None, CORRECT_MS)
        # Only 1 unique discovery — no level up
        assert len(engine.discovered) == 1
        assert engine.level == 1

    def test_no_input_stays_waiting(self, engine):
        _to_waiting(engine)
        engine.update(None, 5000)
        assert engine.state == WAITING


class TestLevel2FindTheNumber:
    def test_challenge_type_is_find(self, engine_l2):
        engine_l2.update(None, WELCOME_MS)
        assert engine_l2.challenge_type == CHALLENGE_FIND

    def test_target_in_valid_range(self, engine_l2):
        engine_l2.update(None, WELCOME_MS)
        assert 1 <= engine_l2.target <= 10

    def test_matching_card_is_correct(self, engine_l2):
        _to_waiting(engine_l2)
        target = engine_l2.target
        engine_l2.update("dots_{}".format(target), 0)
        assert engine_l2.state == CORRECT
        assert engine_l2.score == 1

    def test_non_matching_card_is_wrong(self, engine_l2):
        _to_waiting(engine_l2)
        target = engine_l2.target
        wrong = (target % 10) + 1  # different number
        engine_l2.update("dots_{}".format(wrong), 0)
        assert engine_l2.state == WRONG
        assert engine_l2.score == 0

    def test_correct_returns_to_announce_with_new_target(self, engine_l2):
        """Level 2: CORRECT -> ANNOUNCE (new challenge)."""
        _to_waiting(engine_l2)
        target = engine_l2.target
        engine_l2.update("dots_{}".format(target), 0)
        assert engine_l2.state == CORRECT
        engine_l2.update(None, CORRECT_MS)
        assert engine_l2.state == ANNOUNCE

    def test_level_up_after_threshold(self, engine_l2):
        for _ in range(FIND_THRESHOLD):
            _to_waiting(engine_l2)
            target = engine_l2.target
            engine_l2.update("dots_{}".format(target), 0)
            assert engine_l2.state == CORRECT
            engine_l2.update(None, CORRECT_MS)

        assert engine_l2.state == LEVEL_UP
        engine_l2.update(None, LEVEL_UP_MS)
        assert engine_l2.level == 3

    def test_operator_card_is_wrong(self, engine_l2):
        _to_waiting(engine_l2)
        engine_l2.update("op_plus", 0)
        assert engine_l2.state == WRONG


class TestLevel3MoreOrLess:
    def test_challenge_type_is_comparison(self, engine_l3):
        engine_l3.update(None, WELCOME_MS)
        assert engine_l3.challenge_type in (CHALLENGE_MORE, CHALLENGE_LESS)

    def test_target_valid_for_more(self, engine_l3):
        """'More than' reference must be < 10 so valid answers exist."""
        # Run many times to check range
        for _ in range(50):
            eng = RaknaEngine(SAMPLE_CARD_SET, level=3)
            eng.update(None, WELCOME_MS)
            if eng.challenge_type == CHALLENGE_MORE:
                assert eng.target <= 9

    def test_target_valid_for_less(self, engine_l3):
        """'Less than' reference must be > 1 so valid answers exist."""
        for _ in range(50):
            eng = RaknaEngine(SAMPLE_CARD_SET, level=3)
            eng.update(None, WELCOME_MS)
            if eng.challenge_type == CHALLENGE_LESS:
                assert eng.target >= 2

    def test_more_correct(self, engine_l3):
        _to_waiting(engine_l3)
        if engine_l3.challenge_type == CHALLENGE_MORE:
            ref = engine_l3.target
            answer = min(ref + 1, 10)
            engine_l3.update("dots_{}".format(answer), 0)
            assert engine_l3.state == CORRECT
        else:
            # It's a LESS challenge — scan a smaller number
            ref = engine_l3.target
            answer = max(ref - 1, 1)
            engine_l3.update("dots_{}".format(answer), 0)
            assert engine_l3.state == CORRECT

    def test_equal_is_wrong(self, engine_l3):
        _to_waiting(engine_l3)
        ref = engine_l3.target
        engine_l3.update("dots_{}".format(ref), 0)
        assert engine_l3.state == WRONG

    def test_level_3_is_endless(self, engine_l3):
        """Level 3 never triggers LEVEL_UP (levels 4-6 are future)."""
        for _ in range(20):
            _to_waiting(engine_l3)
            ct = engine_l3.challenge_type
            ref = engine_l3.target
            if ct == CHALLENGE_MORE:
                answer = min(ref + 1, 10)
            else:
                answer = max(ref - 1, 1)
            engine_l3.update("dots_{}".format(answer), 0)
            assert engine_l3.state == CORRECT
            engine_l3.update(None, CORRECT_MS)
        assert engine_l3.level == 3
        assert engine_l3.state != LEVEL_UP


class TestFeedbackTimers:
    def test_wrong_returns_to_waiting(self, engine):
        _to_waiting(engine)
        engine.update("op_plus", 0)
        assert engine.state == WRONG
        engine.update(None, WRONG_MS - 1)
        assert engine.state == WRONG
        engine.update(None, 1)
        assert engine.state == WAITING

    def test_correct_stays_for_duration(self, engine):
        _to_waiting(engine)
        engine.update("dots_1", 0)
        assert engine.state == CORRECT
        engine.update(None, CORRECT_MS - 1)
        assert engine.state == CORRECT


class TestLevelUp:
    def test_level_up_transitions_to_announce(self, engine_l2):
        """LEVEL_UP -> ANNOUNCE, level increments."""
        for _ in range(FIND_THRESHOLD):
            _to_waiting(engine_l2)
            t = engine_l2.target
            engine_l2.update("dots_{}".format(t), 0)
            engine_l2.update(None, CORRECT_MS)

        assert engine_l2.state == LEVEL_UP
        assert engine_l2.level == 2  # still 2 during LEVEL_UP
        engine_l2.update(None, LEVEL_UP_MS)
        assert engine_l2.level == 3
        assert engine_l2.state == ANNOUNCE


class TestScoring:
    def test_streak_resets_on_wrong(self, engine_l2):
        _to_waiting(engine_l2)
        target = engine_l2.target
        engine_l2.update("dots_{}".format(target), 0)
        engine_l2.update(None, CORRECT_MS)
        _to_waiting(engine_l2)

        assert engine_l2.streak == 1
        assert engine_l2.best_streak == 1

        wrong = (target % 10) + 1
        engine_l2.update("dots_{}".format(wrong), 0)
        engine_l2.update(None, WRONG_MS)

        assert engine_l2.streak == 0
        assert engine_l2.best_streak == 1
        assert engine_l2.score == 1


class TestCheckCard:
    def test_check_updates_last_card(self, engine):
        engine.check_card("dots_3")
        assert engine.last_card_id == "dots_3"
        assert engine.last_card is not None
        assert engine.last_card_quantity == 3

    def test_check_unknown_card(self, engine):
        result = engine.check_card("unknown_xyz")
        assert result is False
        assert engine.last_card is None
        assert engine.last_card_quantity == 0

    def test_check_operator_returns_false(self, engine):
        result = engine.check_card("op_plus")
        assert result is False
        assert engine.last_card_quantity == 0


class TestNumberKeys:
    def test_number_key(self, engine):
        engine.check_card("dots_7")
        assert engine.number_key == "rakna_number_7"

    def test_target_number_key(self, engine_l2):
        engine_l2.update(None, WELCOME_MS)
        assert engine_l2.target_number_key == "rakna_number_{}".format(engine_l2.target)

    def test_number_key_none_for_no_scan(self, engine):
        assert engine.number_key is None


class TestReset:
    def test_reset_clears_state(self, engine):
        _to_waiting(engine)
        engine.update("dots_1", 0)
        engine.score = 10
        engine.streak = 5
        engine.reset()
        assert engine.state == WELCOME
        assert engine.score == 0
        assert engine.streak == 0
        assert engine.level == 1
        assert len(engine.discovered) == 0

    def test_reset_to_specific_level(self, engine):
        engine.reset(level=3)
        assert engine.level == 3


class TestDemoCards:
    def test_demo_cards_are_number_cards(self, engine):
        """All demo card IDs should correspond to number cards."""
        for card_id in DEMO_CARDS:
            assert engine.check_card(card_id) is True
            assert engine.last_card_quantity > 0

    def test_demo_cards_sequential(self):
        """Demo cards map buttons 0-7 to dots_1 through dots_8."""
        for i, card_id in enumerate(DEMO_CARDS):
            assert card_id == "dots_{}".format(i + 1)


class TestLEDs:
    def test_make_static_leds_returns_list(self, engine):
        buf = engine.make_static_leds(100)
        assert isinstance(buf, list)
        assert len(buf) > 0
        assert isinstance(buf[0], tuple)

    def test_announce_has_coloured_leds(self, engine):
        engine.update(None, WELCOME_MS)
        buf = engine.make_static_leds(100)
        assert any(t != (0, 0, 0) for t in buf)

    def test_correct_has_green_leds(self, engine):
        _to_waiting(engine)
        engine.update("dots_1", 0)
        assert engine.state == CORRECT
        buf = engine.make_static_leds(100)
        # At least some LEDs should be green-ish
        assert any(t[1] > 0 and t[0] == 0 for t in buf)

    def test_wrong_has_amber_leds(self, engine):
        _to_waiting(engine)
        engine.update("op_plus", 0)
        assert engine.state == WRONG
        buf = engine.make_static_leds(100)
        # Amber: r > 0, g > 0, b == 0
        assert any(t[0] > 0 and t[1] > 0 for t in buf)


class TestTargetRangeExpansion:
    def test_level2_starts_with_range_5(self, engine_l2):
        engine_l2.update(None, WELCOME_MS)
        assert engine_l2._target_range == 5
        assert engine_l2.target <= 5

    def test_level2_expands_to_10_after_3_correct(self, engine_l2):
        for _ in range(3):
            _to_waiting(engine_l2)
            t = engine_l2.target
            engine_l2.update("dots_{}".format(t), 0)
            engine_l2.update(None, CORRECT_MS)
        assert engine_l2._target_range == 10
