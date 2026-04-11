"""Tests for bodn/story_rules.py — Story Mode engine.

All tests run on the host; no hardware required.
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "firmware"))

from bodn.story_rules import (
    StoryEngine,
    IDLE,
    NARRATING,
    CHOOSING,
    TRANSITIONING,
    ENDING,
    TRANSITION_MS,
    ENDING_MS,
    validate_story,
    find_endings,
    reachable_nodes,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TICK_MS = 33  # ~30 fps


def _advance_ms(eng, ms):
    """Advance the engine by *ms* milliseconds in TICK_MS-sized steps."""
    elapsed = 0
    while elapsed < ms:
        step = min(TICK_MS, ms - elapsed)
        eng.update(step)
        elapsed += step


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_STORY = {
    "id": "test",
    "version": 1,
    "title": {"sv": "Test", "en": "Test"},
    "start": "a",
    "narrate_choices": True,
    "nodes": {
        "a": {
            "text": {"sv": "Hallå", "en": "Hello"},
            "mood": "warm",
            "choices": [
                {"label": {"sv": "Gå", "en": "Go"}, "next": "b"},
            ],
        },
        "b": {
            "text": {"sv": "Slut", "en": "End"},
            "mood": "happy",
            "ending": True,
            "ending_type": "happy",
        },
    },
}

BRANCHING_STORY = {
    "id": "branch",
    "version": 1,
    "title": {"sv": "Grenar", "en": "Branches"},
    "start": "start",
    "narrate_choices": True,
    "nodes": {
        "start": {
            "text": {"sv": "Start", "en": "Start"},
            "choices": [
                {"label": {"sv": "A", "en": "A"}, "next": "left"},
                {"label": {"sv": "B", "en": "B"}, "next": "right"},
                {"label": {"sv": "C", "en": "C"}, "next": "middle"},
            ],
        },
        "left": {
            "text": {"sv": "Vänster", "en": "Left"},
            "mood": "tense",
            "choices": [
                {"label": {"sv": "Gå", "en": "Go"}, "next": "merge"},
            ],
        },
        "right": {
            "text": {"sv": "Höger", "en": "Right"},
            "mood": "wonder",
            "choices": [
                {"label": {"sv": "Gå", "en": "Go"}, "next": "merge"},
            ],
        },
        "middle": {
            "text": {"sv": "Mitten", "en": "Middle"},
            "ending": True,
            "ending_type": "adventurous",
        },
        "merge": {
            "text": {"sv": "Samman", "en": "Merged"},
            "mood": "calm",
            "ending": True,
            "ending_type": "gentle",
        },
    },
}


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_minimal(self):
        assert validate_story(MINIMAL_STORY) == []

    def test_valid_branching(self):
        assert validate_story(BRANCHING_STORY) == []

    def test_missing_id(self):
        story = {"start": "a", "nodes": {"a": {"text": {"en": "Hi"}, "ending": True}}}
        errors = validate_story(story)
        assert any("missing 'id'" in e for e in errors)

    def test_missing_start(self):
        story = {"id": "t", "nodes": {"a": {"text": {"en": "Hi"}, "ending": True}}}
        errors = validate_story(story)
        assert any("missing 'start'" in e for e in errors)

    def test_start_not_in_nodes(self):
        story = {
            "id": "t",
            "start": "missing",
            "nodes": {"a": {"text": {"en": "Hi"}, "ending": True}},
        }
        errors = validate_story(story)
        assert any("start node" in e for e in errors)

    def test_missing_text(self):
        story = {
            "id": "t",
            "start": "a",
            "nodes": {"a": {"ending": True}},
        }
        errors = validate_story(story)
        assert any("missing 'text'" in e for e in errors)

    def test_choice_target_missing(self):
        story = {
            "id": "t",
            "start": "a",
            "nodes": {
                "a": {
                    "text": {"en": "Hi"},
                    "choices": [{"label": {"en": "Go"}, "next": "nowhere"}],
                },
            },
        }
        errors = validate_story(story)
        assert any("nowhere" in e for e in errors)

    def test_too_many_choices(self):
        choices = [{"label": {"en": str(i)}, "next": "end"} for i in range(6)]
        story = {
            "id": "t",
            "start": "a",
            "nodes": {
                "a": {"text": {"en": "Hi"}, "choices": choices},
                "end": {"text": {"en": "End"}, "ending": True},
            },
        }
        errors = validate_story(story)
        assert any("exceeds max" in e for e in errors)

    def test_no_choices_no_ending(self):
        story = {
            "id": "t",
            "start": "a",
            "nodes": {"a": {"text": {"en": "Hi"}}},
        }
        errors = validate_story(story)
        assert any("no choices and not an ending" in e for e in errors)


# ---------------------------------------------------------------------------
# Graph analysis tests
# ---------------------------------------------------------------------------


class TestGraphAnalysis:
    def test_find_endings_minimal(self):
        endings = find_endings(MINIMAL_STORY)
        assert endings == ["b"]

    def test_find_endings_branching(self):
        endings = find_endings(BRANCHING_STORY)
        assert set(endings) == {"middle", "merge"}

    def test_reachable_minimal(self):
        reached = reachable_nodes(MINIMAL_STORY)
        assert reached == {"a", "b"}

    def test_reachable_branching(self):
        reached = reachable_nodes(BRANCHING_STORY)
        assert reached == {"start", "left", "right", "middle", "merge"}

    def test_all_endings_reachable(self):
        reached = reachable_nodes(BRANCHING_STORY)
        endings = find_endings(BRANCHING_STORY)
        for e in endings:
            assert e in reached, f"ending '{e}' is not reachable"


# ---------------------------------------------------------------------------
# Engine state machine tests
# ---------------------------------------------------------------------------


class TestEngineBasic:
    def test_initial_state(self):
        eng = StoryEngine()
        assert eng.state == IDLE
        assert eng.story is None

    def test_load_starts_narrating(self):
        eng = StoryEngine()
        errors = eng.load(MINIMAL_STORY)
        assert errors == []
        assert eng.state == NARRATING
        assert eng.node_id == "a"

    def test_load_invalid_returns_errors(self):
        eng = StoryEngine()
        errors = eng.load({"id": "bad"})
        assert len(errors) > 0
        assert eng.state == IDLE

    def test_reset(self):
        eng = StoryEngine()
        eng.load(MINIMAL_STORY)
        eng.reset()
        assert eng.state == IDLE
        assert eng.story is None
        assert eng.visited == []


class TestEngineNarration:
    def test_narration_done_transitions_to_choosing(self):
        eng = StoryEngine()
        eng.load(MINIMAL_STORY)
        assert eng.state == NARRATING
        eng.narration_done()
        assert eng.state == CHOOSING

    def test_text_returns_correct_language(self):
        eng = StoryEngine()
        eng.load(MINIMAL_STORY)
        assert eng.text("sv") == "Hallå"
        assert eng.text("en") == "Hello"

    def test_text_falls_back_to_english(self):
        eng = StoryEngine()
        eng.load(MINIMAL_STORY)
        assert eng.text("de") == "Hello"

    def test_choice_count(self):
        eng = StoryEngine()
        eng.load(MINIMAL_STORY)
        assert eng.choice_count == 1

    def test_choice_label(self):
        eng = StoryEngine()
        eng.load(MINIMAL_STORY)
        assert eng.choice_label(0, "en") == "Go"
        assert eng.choice_label(0, "sv") == "Gå"
        assert eng.choice_label(1, "en") == ""  # out of range


class TestEngineChoosing:
    def test_choose_valid(self):
        eng = StoryEngine()
        eng.load(MINIMAL_STORY)
        eng.narration_done()
        assert eng.state == CHOOSING
        assert eng.choose(0) is True
        assert eng.state == TRANSITIONING

    def test_choose_invalid_index(self):
        eng = StoryEngine()
        eng.load(MINIMAL_STORY)
        eng.narration_done()
        assert eng.choose(5) is False
        assert eng.state == CHOOSING

    def test_choose_wrong_state(self):
        eng = StoryEngine()
        eng.load(MINIMAL_STORY)
        # Still NARRATING
        assert eng.choose(0) is False

    def test_transition_leads_to_next_node(self):
        eng = StoryEngine()
        eng.load(MINIMAL_STORY)
        eng.narration_done()
        eng.choose(0)
        assert eng.state == TRANSITIONING
        # Advance past transition
        _advance_ms(eng, TRANSITION_MS + TICK_MS)
        # Should now be at ending node "b"
        assert eng.node_id == "b"
        assert eng.state == ENDING


class TestEngineBranching:
    def test_three_choices(self):
        eng = StoryEngine()
        eng.load(BRANCHING_STORY)
        assert eng.choice_count == 3

    def test_left_branch(self):
        eng = StoryEngine()
        eng.load(BRANCHING_STORY)
        eng.narration_done()
        eng.choose(0)  # "left"
        _advance_ms(eng, TRANSITION_MS + TICK_MS)
        assert eng.node_id == "left"
        assert eng.state == NARRATING

    def test_right_branch(self):
        eng = StoryEngine()
        eng.load(BRANCHING_STORY)
        eng.narration_done()
        eng.choose(1)  # "right"
        _advance_ms(eng, TRANSITION_MS + TICK_MS)
        assert eng.node_id == "right"

    def test_middle_direct_ending(self):
        eng = StoryEngine()
        eng.load(BRANCHING_STORY)
        eng.narration_done()
        eng.choose(2)  # "middle" — direct ending
        _advance_ms(eng, TRANSITION_MS + TICK_MS)
        assert eng.node_id == "middle"
        assert eng.state == ENDING
        assert eng.ending_type == "adventurous"

    def test_diamond_convergence(self):
        """Both left and right branches converge at 'merge'."""
        for branch_idx in (0, 1):
            eng = StoryEngine()
            eng.load(BRANCHING_STORY)
            eng.narration_done()
            eng.choose(branch_idx)
            _advance_ms(eng, TRANSITION_MS + TICK_MS)
            # Now at left or right
            eng.narration_done()
            eng.choose(0)
            _advance_ms(eng, TRANSITION_MS + TICK_MS)
            assert eng.node_id == "merge"
            assert eng.state == ENDING


class TestEngineEnding:
    def test_ending_returns_to_idle(self):
        eng = StoryEngine()
        eng.load(MINIMAL_STORY)
        eng.narration_done()
        eng.choose(0)
        # Advance through transition
        _advance_ms(eng, TRANSITION_MS + TICK_MS)
        assert eng.state == ENDING
        # Advance through ending celebration
        _advance_ms(eng, ENDING_MS + TICK_MS)
        assert eng.state == IDLE

    def test_visited_tracks_path(self):
        eng = StoryEngine()
        eng.load(MINIMAL_STORY)
        assert eng.visited == ["a"]
        eng.narration_done()
        eng.choose(0)
        _advance_ms(eng, TRANSITION_MS + TICK_MS)
        assert eng.visited == ["a", "b"]

    def test_progress_counts_visited(self):
        eng = StoryEngine()
        eng.load(MINIMAL_STORY)
        assert eng.progress == 1
        eng.narration_done()
        eng.choose(0)
        _advance_ms(eng, TRANSITION_MS + TICK_MS)
        assert eng.progress == 2


class TestEngineMood:
    def test_default_mood(self):
        story = {
            "id": "t",
            "start": "a",
            "nodes": {"a": {"text": {"en": "Hi"}, "ending": True}},
        }
        eng = StoryEngine()
        eng.load(story)
        assert eng.mood == "calm"

    def test_mood_from_node(self):
        eng = StoryEngine()
        eng.load(MINIMAL_STORY)
        assert eng.mood == "warm"


class TestEngineLEDs:
    def test_leds_not_none(self):
        eng = StoryEngine()
        eng.load(MINIMAL_STORY)
        leds = eng.make_static_leds(128)
        assert leds is not None
        assert len(leds) >= 16

    def test_idle_leds(self):
        eng = StoryEngine()
        leds = eng.make_static_leds(128)
        # Should be dim warm glow
        assert leds[0][0] > 0  # non-zero red component


# ---------------------------------------------------------------------------
# Forest Walk story validation
# ---------------------------------------------------------------------------


class TestForestWalkStory:
    @pytest.fixture
    def story(self):
        story_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "assets",
            "stories",
            "forest_walk",
            "script.py",
        )
        ns = {}
        with open(story_path) as f:
            exec(f.read(), ns)
        return ns["STORY"]

    def test_valid(self, story):
        errors = validate_story(story)
        assert errors == [], f"Forest Walk has errors: {errors}"

    def test_all_endings_reachable(self, story):
        reached = reachable_nodes(story)
        endings = find_endings(story)
        assert len(endings) > 0
        for e in endings:
            assert e in reached, f"ending '{e}' not reachable"


# ---------------------------------------------------------------------------
# Peter Rabbit story validation
# ---------------------------------------------------------------------------


class TestPeterRabbitStory:
    @pytest.fixture
    def story(self):
        story_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "assets",
            "stories",
            "peter_rabbit",
            "script.py",
        )
        ns = {}
        with open(story_path) as f:
            exec(f.read(), ns)
        return ns["STORY"]

    def test_valid(self, story):
        errors = validate_story(story)
        assert errors == [], f"Peter Rabbit has errors: {errors}"

    def test_has_multiple_endings(self, story):
        endings = find_endings(story)
        assert len(endings) >= 4, f"Expected 4+ endings, got {len(endings)}: {endings}"

    def test_all_endings_reachable(self, story):
        reached = reachable_nodes(story)
        endings = find_endings(story)
        for e in endings:
            assert e in reached, f"ending '{e}' not reachable"

    def test_all_nodes_reachable(self, story):
        reached = reachable_nodes(story)
        all_nodes = set(story["nodes"].keys())
        unreachable = all_nodes - reached
        assert unreachable == set(), f"Unreachable nodes: {unreachable}"

    def test_bilingual_text(self, story):
        """Every node should have both sv and en text."""
        for nid, node in story["nodes"].items():
            text = node.get("text", {})
            assert "sv" in text, f"node '{nid}' missing Swedish text"
            assert "en" in text, f"node '{nid}' missing English text"

    def test_bilingual_labels(self, story):
        """Every choice label should have both sv and en."""
        for nid, node in story["nodes"].items():
            for i, ch in enumerate(node.get("choices", [])):
                label = ch.get("label", {})
                assert "sv" in label, f"node '{nid}' choice {i} missing Swedish label"
                assert "en" in label, f"node '{nid}' choice {i} missing English label"

    def test_max_choices_per_node(self, story):
        for nid, node in story["nodes"].items():
            choices = node.get("choices", [])
            assert len(choices) <= 5, f"node '{nid}' has {len(choices)} choices (max 5)"
