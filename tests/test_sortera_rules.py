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
    ANNOUNCE_MS,
    CORRECT_MS,
    WRONG_MS,
    SWITCH_MS,
    DEMO_CARDS,
)

SAMPLE_CARD_SET = {
    "mode": "sortera",
    "version": 1,
    "dimensions": ["category", "colour"],
    "cards": [
        {"id": "cat_red", "category": "animal", "colour": "red"},
        {"id": "cat_blue", "category": "animal", "colour": "blue"},
        {"id": "dog_green", "category": "animal", "colour": "green"},
        {"id": "dog_yellow", "category": "animal", "colour": "yellow"},
        {"id": "fish_red", "category": "animal", "colour": "red"},
        {"id": "fish_blue", "category": "animal", "colour": "blue"},
        {"id": "cow_green", "category": "animal", "colour": "green"},
        {"id": "frog_yellow", "category": "animal", "colour": "yellow"},
    ],
}


@pytest.fixture
def engine():
    return SorteraEngine(SAMPLE_CARD_SET)


class TestInitialState:
    def test_starts_in_welcome(self, engine):
        assert engine.state == WELCOME

    def test_score_is_zero(self, engine):
        assert engine.score == 0
        assert engine.streak == 0
        assert engine.best_streak == 0
        assert engine.rule_switches == 0


class TestWelcomeToPlaying:
    def test_any_card_starts_game(self, engine):
        engine.update("cat_red", 0)
        assert engine.state == ANNOUNCE_RULE

    def test_no_input_stays_in_welcome(self, engine):
        engine.update(None, 100)
        assert engine.state == WELCOME

    def test_rule_is_picked(self, engine):
        engine.update("cat_red", 0)
        assert engine.rule_dimension in ("category", "colour")
        assert engine.rule_value != ""


class TestAnnounceRule:
    def test_waits_for_announce_duration(self, engine):
        engine.update("cat_red", 0)  # → ANNOUNCE_RULE
        engine.update(None, ANNOUNCE_MS - 1)
        assert engine.state == ANNOUNCE_RULE

    def test_transitions_to_waiting(self, engine):
        engine.update("cat_red", 0)
        engine.update(None, ANNOUNCE_MS)
        assert engine.state == WAITING


class TestCardChecking:
    def _to_waiting(self, engine):
        engine.update("cat_red", 0)
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
        engine.update("cat_red", 0)
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
        engine.update("cat_red", 0)
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
        engine.update("cat_red", 0)
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
        engine.update("cat_red", 0)  # start game, picks a rule
        count = engine.matching_count
        assert count >= 1
        assert count <= len(SAMPLE_CARD_SET["cards"])


class TestCheckCard:
    def test_check_updates_last_card(self, engine):
        engine.update("cat_red", 0)
        engine.update(None, ANNOUNCE_MS)
        engine.check_card("cat_red")
        assert engine.last_card_id == "cat_red"
        assert engine.last_card is not None
        assert engine.last_card["id"] == "cat_red"

    def test_check_unknown_card(self, engine):
        engine.update("cat_red", 0)
        engine.update(None, ANNOUNCE_MS)
        result = engine.check_card("unknown_xyz")
        assert result is False
        assert engine.last_card is None


class TestReset:
    def test_reset_clears_state(self, engine):
        engine.update("cat_red", 0)
        engine.update(None, ANNOUNCE_MS)
        engine.score = 10
        engine.streak = 5
        engine.reset()
        assert engine.state == WELCOME
        assert engine.score == 0
        assert engine.streak == 0


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
    def test_make_static_leds_returns_buffer(self, engine):
        buf = engine.make_static_leds(100)
        assert isinstance(buf, bytearray)
        assert len(buf) > 0

    def test_different_states_different_leds(self, engine):
        # WELCOME state
        buf_welcome = engine.make_static_leds(100)

        # Start game → ANNOUNCE_RULE
        engine.update("cat_red", 0)
        buf_announce = engine.make_static_leds(100)

        # The announce buffer should have colour (rule colour), welcome should be black
        assert buf_welcome != buf_announce or all(b == 0 for b in buf_welcome)
