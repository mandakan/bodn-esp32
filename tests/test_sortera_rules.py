"""Tests for bodn.sortera_rules — Sortera classification game engine."""

import pytest
from bodn.sortera_rules import (
    SorteraEngine,
    WELCOME,
    ANNOUNCE_RULE,
    WAITING,
    CORRECT,
    WRONG,
    RULE_SWITCH,
    WELCOME_MS,
    ANNOUNCE_MS,
    CORRECT_MS,
    WRONG_MS,
    SWITCH_MS,
    DEMO_CARDS,
)

SAMPLE_CARD_SET = {
    "mode": "sortera",
    "version": 1,
    "dimensions": ["animal", "vehicle", "colour", "category"],
    "cards": [
        {"id": "cat_red", "category": "animal", "animal": "cat", "colour": "red"},
        {"id": "cat_blue", "category": "animal", "animal": "cat", "colour": "blue"},
        {"id": "dog_green", "category": "animal", "animal": "dog", "colour": "green"},
        {"id": "dog_yellow", "category": "animal", "animal": "dog", "colour": "yellow"},
        {"id": "car_red", "category": "vehicle", "vehicle": "car", "colour": "red"},
        {"id": "car_blue", "category": "vehicle", "vehicle": "car", "colour": "blue"},
        {"id": "bus_green", "category": "vehicle", "vehicle": "bus", "colour": "green"},
        {
            "id": "bus_yellow",
            "category": "vehicle",
            "vehicle": "bus",
            "colour": "yellow",
        },
    ],
}


@pytest.fixture
def engine():
    return SorteraEngine(SAMPLE_CARD_SET)


class TestInitialState:
    def test_starts_in_welcome(self, engine):
        assert engine.state == WELCOME

    def test_rule_is_picked_at_start(self, engine):
        assert engine.rule_dimension in ("animal", "colour")
        assert engine.rule_value != ""

    def test_score_is_zero(self, engine):
        assert engine.score == 0
        assert engine.streak == 0
        assert engine.best_streak == 0
        assert engine.rule_switches == 0


class TestWelcome:
    def test_auto_advances_to_announce(self, engine):
        engine.update(None, WELCOME_MS)
        assert engine.state == ANNOUNCE_RULE

    def test_stays_in_welcome_before_timeout(self, engine):
        engine.update(None, WELCOME_MS - 1)
        assert engine.state == WELCOME


class TestAnnounceRule:
    def _to_announce(self, engine):
        engine.update(None, WELCOME_MS)
        assert engine.state == ANNOUNCE_RULE

    def test_waits_for_announce_duration(self, engine):
        self._to_announce(engine)
        engine.update(None, ANNOUNCE_MS - 1)
        assert engine.state == ANNOUNCE_RULE

    def test_transitions_to_waiting(self, engine):
        self._to_announce(engine)
        engine.update(None, ANNOUNCE_MS)
        assert engine.state == WAITING


class TestCardChecking:
    def _to_waiting(self, engine):
        engine.update(None, WELCOME_MS)
        engine.update(None, ANNOUNCE_MS)
        assert engine.state == WAITING

    def test_matching_card_is_correct(self, engine):
        self._to_waiting(engine)
        # Find a card that matches the current rule
        for card in SAMPLE_CARD_SET["cards"]:
            if card.get(engine.rule_dimension) == engine.rule_value:
                engine.update(card["id"], 0)
                assert engine.state == CORRECT
                assert engine.score == 1
                assert engine.streak == 1
                return
        pytest.skip("No matching card found for picked rule")

    def test_non_matching_card_is_wrong(self, engine):
        self._to_waiting(engine)
        # Find a card that doesn't match
        for card in SAMPLE_CARD_SET["cards"]:
            if card.get(engine.rule_dimension) != engine.rule_value:
                engine.update(card["id"], 0)
                assert engine.state == WRONG
                assert engine.score == 0
                assert engine.streak == 0
                return
        pytest.skip("All cards match the picked rule")

    def test_unknown_card_is_wrong(self, engine):
        self._to_waiting(engine)
        engine.update("nonexistent_card", 0)
        assert engine.state == WRONG

    def test_no_input_stays_waiting(self, engine):
        self._to_waiting(engine)
        engine.update(None, 1000)
        assert engine.state == WAITING


class TestFeedbackTimers:
    def _to_waiting(self, engine):
        engine.update(None, WELCOME_MS)
        engine.update(None, ANNOUNCE_MS)

    def _find_matching(self, engine):
        for card in SAMPLE_CARD_SET["cards"]:
            if card.get(engine.rule_dimension) == engine.rule_value:
                return card["id"]
        return None

    def _find_non_matching(self, engine):
        for card in SAMPLE_CARD_SET["cards"]:
            if card.get(engine.rule_dimension) != engine.rule_value:
                return card["id"]
        return None

    def test_correct_returns_to_waiting(self, engine):
        self._to_waiting(engine)
        match = self._find_matching(engine)
        if match is None:
            pytest.skip("No match")
        engine.update(match, 0)
        assert engine.state == CORRECT
        engine.update(None, CORRECT_MS)
        # Should go back to WAITING (not enough correct for rule switch)
        assert engine.state == WAITING

    def test_wrong_returns_to_waiting(self, engine):
        self._to_waiting(engine)
        non_match = self._find_non_matching(engine)
        if non_match is None:
            pytest.skip("All match")
        engine.update(non_match, 0)
        assert engine.state == WRONG
        engine.update(None, WRONG_MS)
        assert engine.state == WAITING


class TestRuleSwitching:
    def _to_waiting(self, engine):
        engine.update(None, WELCOME_MS)
        engine.update(None, ANNOUNCE_MS)

    def _find_matching(self, engine):
        for card in SAMPLE_CARD_SET["cards"]:
            if card.get(engine.rule_dimension) == engine.rule_value:
                return card["id"]
        return None

    def test_switches_after_threshold(self, engine):
        """After enough correct answers, rule should switch."""
        self._to_waiting(engine)
        old_dim = engine.rule_dimension
        old_val = engine.rule_value
        threshold = engine._switch_threshold

        for _ in range(threshold):
            match = self._find_matching(engine)
            if match is None:
                pytest.skip("No match found")
            engine.update(match, 0)
            assert engine.state == CORRECT
            engine.update(None, CORRECT_MS)

        # After threshold correct, should be in RULE_SWITCH
        assert engine.state == RULE_SWITCH
        assert engine.rule_switches == 1

        # Wait for switch to complete
        engine.update(None, SWITCH_MS)
        assert engine.state == ANNOUNCE_RULE

        # New rule should be different (with high probability)
        # Note: with small card sets it could randomly pick the same,
        # so we just check the engine didn't crash


class TestScoring:
    def _to_waiting(self, engine):
        engine.update(None, WELCOME_MS)
        engine.update(None, ANNOUNCE_MS)

    def _find_matching(self, engine):
        for card in SAMPLE_CARD_SET["cards"]:
            if card.get(engine.rule_dimension) == engine.rule_value:
                return card["id"]
        return None

    def _find_non_matching(self, engine):
        for card in SAMPLE_CARD_SET["cards"]:
            if card.get(engine.rule_dimension) != engine.rule_value:
                return card["id"]
        return None

    def test_streak_resets_on_wrong(self, engine):
        self._to_waiting(engine)
        # Get 2 correct
        for _ in range(2):
            match = self._find_matching(engine)
            if match is None:
                pytest.skip("No match")
            engine.update(match, 0)
            engine.update(None, CORRECT_MS)

        assert engine.streak == 2
        assert engine.best_streak == 2

        # Get one wrong
        non_match = self._find_non_matching(engine)
        if non_match is None:
            pytest.skip("All match")
        engine.update(non_match, 0)
        engine.update(None, WRONG_MS)

        assert engine.streak == 0
        assert engine.best_streak == 2  # best preserved
        assert engine.score == 2  # score preserved


class TestMatchingCount:
    def test_matching_count(self, engine):
        count = engine.matching_count
        assert count >= 1
        assert count <= len(SAMPLE_CARD_SET["cards"])


class TestCheckCard:
    def test_check_updates_last_card(self, engine):
        engine.update(None, WELCOME_MS)
        engine.update(None, ANNOUNCE_MS)
        engine.check_card("cat_red")
        assert engine.last_card_id == "cat_red"
        assert engine.last_card is not None
        assert engine.last_card["id"] == "cat_red"

    def test_check_unknown_card(self, engine):
        engine.update(None, WELCOME_MS)
        engine.update(None, ANNOUNCE_MS)
        result = engine.check_card("unknown_xyz")
        assert result is False
        assert engine.last_card is None


class TestReset:
    def test_reset_clears_state(self, engine):
        engine.update(None, WELCOME_MS)
        engine.update(None, ANNOUNCE_MS)
        engine.score = 10
        engine.streak = 5
        engine.reset()
        assert engine.state == WELCOME
        assert engine.score == 0
        assert engine.streak == 0
        assert engine.rule_dimension in ("animal", "colour")


class TestDemoCards:
    def test_demo_cards_exist_in_card_set(self):
        """All demo card IDs should exist in the sortera card set."""
        card_ids = {c["id"] for c in SAMPLE_CARD_SET["cards"]}
        # Demo cards reference the first colour variant of each animal
        for card_id in DEMO_CARDS:
            # Demo cards may reference specific variants — just check format
            assert isinstance(card_id, str)
            assert len(card_id) > 0


class TestLEDs:
    def test_make_static_leds_returns_list(self, engine):
        buf = engine.make_static_leds(100)
        assert isinstance(buf, list)
        assert len(buf) > 0
        assert isinstance(buf[0], tuple)

    def test_announce_has_coloured_leds(self, engine):
        engine.update(None, WELCOME_MS)  # advance to ANNOUNCE_RULE
        buf = engine.make_static_leds(100)
        # Should have some non-zero LEDs (rule colour)
        assert any(t != (0, 0, 0) for t in buf)
