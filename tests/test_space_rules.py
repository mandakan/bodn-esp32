"""Tests for bodn/space_rules.py — Spaceship Cockpit engine.

All tests run on the host; no hardware required.
"""

import sys
import os

import pytest

# Ensure firmware/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "firmware"))

from bodn.space_rules import (
    SpaceEngine,
    CRUISING,
    ANNOUNCE,
    ACTIVE,
    SUCCESS,
    HINT,
    SC_ASTEROID,
    SC_COURSE,
    SC_SHIELD,
    SC_ENGINE,
    SC_LANDING,
    ANNOUNCE_FRAMES,
    SUCCESS_FRAMES,
    HINT_FRAMES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _no_input():
    """Default: no buttons, no encoder movement."""
    return dict(btn=-1, arc=-1, enc_a=0, enc_b=0, sw0=False, sw1=False)


def _tick(eng, frame, **kwargs):
    """Single engine tick. kwargs override _no_input defaults."""
    inp = _no_input()
    inp.update(kwargs)
    return eng.update(
        inp["btn"],
        inp["arc"],
        inp["enc_a"],
        inp["enc_b"],
        inp["sw0"],
        inp["sw1"],
        frame,
    )


def _advance_to_announce(eng):
    """Run the engine until it picks a scenario. Returns the announce frame."""
    for f in range(500):
        ev = _tick(eng, f)
        if ev == "announce":
            return f
    raise AssertionError("Engine never announced a scenario within 500 frames")


def _advance_through_announce(eng, start_frame):
    """Advance through ANNOUNCE phase until ACTIVE."""
    f = start_frame
    for _ in range(ANNOUNCE_FRAMES + 5):
        f += 1
        _tick(eng, f)
        if eng.state == ACTIVE:
            return f
    raise AssertionError("Engine did not transition to ACTIVE after announce")


# ---------------------------------------------------------------------------
# Basic state machine
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_starts_cruising(self):
        eng = SpaceEngine()
        assert eng.state == CRUISING

    def test_reset_restores_defaults(self):
        eng = SpaceEngine()
        eng.difficulty = 3
        eng.throttle = 200
        eng.reset()
        assert eng.state == CRUISING
        assert eng.difficulty == 1
        assert eng.throttle == 128

    def test_no_event_while_cruising(self):
        eng = SpaceEngine()
        # Just a few ticks — too early for scenario
        for f in range(50):
            ev = _tick(eng, f)
            assert ev is None


class TestCockpitTracking:
    """Cockpit state is always updated, regardless of game state."""

    def test_throttle_increases_with_encoder_a(self):
        eng = SpaceEngine()
        _tick(eng, 0, enc_a=2)
        assert eng.throttle > 128

    def test_throttle_decreases_with_negative_encoder_a(self):
        eng = SpaceEngine()
        _tick(eng, 0, enc_a=-5)
        assert eng.throttle < 128

    def test_throttle_clamps_to_0_255(self):
        eng = SpaceEngine()
        eng.throttle = 250
        _tick(eng, 0, enc_a=100)
        assert eng.throttle == 255
        eng.throttle = 5
        _tick(eng, 1, enc_a=-100)
        assert eng.throttle == 0

    def test_steering_updates_with_encoder_b(self):
        eng = SpaceEngine()
        _tick(eng, 0, enc_b=3)
        assert eng.steering > 0
        _tick(eng, 1, enc_b=-6)
        assert eng.steering < 0

    def test_steering_clamps(self):
        eng = SpaceEngine()
        for f in range(20):
            _tick(eng, f, enc_b=10)
        assert eng.steering == 127
        for f in range(20, 40):
            _tick(eng, f, enc_b=-10)
        assert eng.steering == -128

    def test_shields_follow_sw0(self):
        eng = SpaceEngine()
        _tick(eng, 0, sw0=True)
        assert eng.shields_on is True
        _tick(eng, 1, sw0=False)
        assert eng.shields_on is False

    def test_stealth_follows_sw1(self):
        eng = SpaceEngine()
        _tick(eng, 0, sw1=True)
        assert eng.stealth is True


# ---------------------------------------------------------------------------
# Scenario lifecycle
# ---------------------------------------------------------------------------


class TestScenarioAnnounce:
    def test_announces_within_cruise_countdown(self):
        eng = SpaceEngine()
        # Force short countdown
        eng._cruise_countdown = 10
        f = _advance_to_announce(eng)
        assert eng.state == ANNOUNCE
        assert eng.scenario_type in (
            SC_ASTEROID,
            SC_COURSE,
            SC_SHIELD,
            SC_ENGINE,
            SC_LANDING,
        )

    def test_announce_transitions_to_active(self):
        eng = SpaceEngine()
        eng._cruise_countdown = 10
        f = _advance_to_announce(eng)
        f = _advance_through_announce(eng, f)
        assert eng.state == ACTIVE

    def test_returns_announce_event_exactly_once(self):
        eng = SpaceEngine()
        eng._cruise_countdown = 10
        events = []
        for f in range(200):
            ev = _tick(eng, f)
            if ev is not None:
                events.append(ev)
        announce_count = events.count("announce")
        assert announce_count == 1


# ---------------------------------------------------------------------------
# Scenario: SC_ASTEROID
# ---------------------------------------------------------------------------


def _force_scenario(eng, sc_type, frame=0):
    """Force a specific scenario type into ACTIVE state."""
    eng._cruise_countdown = 1
    # Tick until announce
    for f in range(frame, frame + 10):
        ev = _tick(eng, f)
        if ev == "announce":
            eng.scenario_type = sc_type
            # Set up scenario details for the forced type
            if sc_type == SC_ASTEROID:
                eng._steer_dir = 1
            elif sc_type == SC_COURSE:
                eng._target_btn = 2
            elif sc_type == SC_LANDING:
                eng._target_arc = 1
            elif sc_type == SC_ENGINE:
                eng._throttle_clicks = 0
                eng._throttle_needed = 3
            f = _advance_through_announce(eng, f)
            return eng, f
    raise AssertionError("Could not force scenario to ANNOUNCE")


class TestAsteroidScenario:
    def _setup(self):
        eng = SpaceEngine()
        return _force_scenario(eng, SC_ASTEROID)

    def test_correct_steer_dir_resolves(self):
        eng, f = self._setup()
        d = eng.steer_dir
        ev = _tick(eng, f + 1, enc_b=d * 2)
        assert ev == "success"
        assert eng.state == SUCCESS

    def test_wrong_steer_dir_does_not_resolve(self):
        eng, f = self._setup()
        d = eng.steer_dir
        ev = _tick(eng, f + 1, enc_b=-d * 2)
        assert ev is None
        assert eng.state == ACTIVE

    def test_no_steering_does_not_resolve(self):
        eng, f = self._setup()
        ev = _tick(eng, f + 1)
        assert ev is None


# ---------------------------------------------------------------------------
# Scenario: SC_COURSE
# ---------------------------------------------------------------------------


class TestCourseScenario:
    def _setup(self):
        eng = SpaceEngine()
        return _force_scenario(eng, SC_COURSE)

    def test_correct_button_resolves(self):
        eng, f = self._setup()
        tgt = eng.target_btn_idx
        ev = _tick(eng, f + 1, btn=tgt)
        assert ev == "success"

    def test_wrong_button_does_not_resolve(self):
        eng, f = self._setup()
        tgt = eng.target_btn_idx
        wrong = (tgt + 1) % 6
        ev = _tick(eng, f + 1, btn=wrong)
        assert ev is None
        assert eng.state == ACTIVE


# ---------------------------------------------------------------------------
# Scenario: SC_SHIELD
# ---------------------------------------------------------------------------


class TestShieldScenario:
    def _setup(self, sw0_initial=False):
        eng = SpaceEngine()
        eng, f = _force_scenario(eng, SC_SHIELD)
        eng._sw0_was_on = sw0_initial
        return eng, f

    def test_shield_on_when_was_off_resolves(self):
        eng, f = self._setup(sw0_initial=False)
        ev = _tick(eng, f + 1, sw0=True)
        assert ev == "success"

    def test_shield_already_on_at_start_does_not_immediately_resolve(self):
        # SC_SHIELD should not be picked when sw0 is already True
        eng = SpaceEngine()
        events = []
        sw_on = True
        for f in range(2000):
            ev = _tick(eng, f, sw0=sw_on)
            if ev == "announce":
                # Shield scenario should never be announced when sw0 was True
                assert eng.scenario_type != SC_SHIELD, (
                    "SC_SHIELD was picked even though shields were already on"
                )
                break


# ---------------------------------------------------------------------------
# Scenario: SC_ENGINE
# ---------------------------------------------------------------------------


class TestEngineScenario:
    def _setup(self):
        eng = SpaceEngine()
        return _force_scenario(eng, SC_ENGINE)

    def test_enough_throttle_clicks_resolves(self):
        eng, f = self._setup()
        needed = eng._throttle_needed
        # Give enough positive encoder clicks
        for i in range(needed):
            ev = _tick(eng, f + i + 1, enc_a=1)
            if ev == "success":
                assert eng.state == SUCCESS
                return
        pytest.fail("SC_ENGINE not resolved after required clicks")

    def test_negative_clicks_do_not_count(self):
        eng, f = self._setup()
        # Turning throttle down should not help
        ev = _tick(eng, f + 1, enc_a=-5)
        assert ev is None
        assert eng._throttle_clicks == 0

    def test_progress_property(self):
        eng, f = self._setup()
        needed = eng._throttle_needed
        assert eng.engine_progress == 0.0
        _tick(eng, f + 1, enc_a=needed // 2)
        assert 0.0 < eng.engine_progress < 1.0


# ---------------------------------------------------------------------------
# Scenario: SC_LANDING
# ---------------------------------------------------------------------------


class TestLandingScenario:
    def _setup(self):
        eng = SpaceEngine()
        return _force_scenario(eng, SC_LANDING)

    def test_correct_arcade_button_resolves(self):
        eng, f = self._setup()
        tgt = eng.target_arc_idx
        ev = _tick(eng, f + 1, arc=tgt)
        assert ev == "success"

    def test_wrong_arcade_button_does_not_resolve(self):
        eng, f = self._setup()
        tgt = eng.target_arc_idx
        wrong = (tgt + 1) % 5
        ev = _tick(eng, f + 1, arc=wrong)
        assert ev is None


# ---------------------------------------------------------------------------
# Timeout / Hint / Resolve flow
# ---------------------------------------------------------------------------


class TestTimeoutFlow:
    def _setup_active(self):
        eng = SpaceEngine()
        eng._cruise_countdown = 5
        f = _advance_to_announce(eng)
        f = _advance_through_announce(eng, f)
        return eng, f

    def test_hint_after_first_timeout(self):
        eng, f = self._setup_active()
        timeout = [240, 180, 150][eng.difficulty - 1]
        # Advance past timeout without solving
        ev = None
        for i in range(timeout + 5):
            ev = _tick(eng, f + i + 1)
            if ev == "hint":
                break
        assert ev == "hint"
        assert eng.state == HINT

    def test_returns_to_active_after_hint(self):
        eng, f = self._setup_active()
        timeout = [240, 180, 150][eng.difficulty - 1]
        # Advance past first timeout
        for i in range(timeout + 5):
            ev = _tick(eng, f + i + 1)
            if ev == "hint":
                hint_frame = f + i + 1
                break
        # Advance through HINT phase
        for i in range(HINT_FRAMES + 5):
            _tick(eng, hint_frame + i + 1)
            if eng.state == ACTIVE:
                return
        pytest.fail("Engine did not return to ACTIVE after HINT")

    def test_resolve_after_second_timeout(self):
        eng, f = self._setup_active()
        timeout = [240, 180, 150][eng.difficulty - 1]
        events = []
        frame = f
        for _ in range(timeout * 2 + HINT_FRAMES + 100):
            frame += 1
            ev = _tick(eng, frame)
            if ev is not None:
                events.append(ev)
            if ev == "resolve":
                break
        assert "hint" in events
        assert "resolve" in events
        assert eng.state == CRUISING

    def test_success_returns_to_cruising_after_celebration(self):
        eng, f = self._setup_active()
        # Force the easiest scenario solvable with any input
        eng.scenario_type = SC_ASTEROID
        eng._steer_dir = 1
        ev = _tick(eng, f + 1, enc_b=2)
        assert ev == "success"
        assert eng.state == SUCCESS
        # Advance through SUCCESS celebration
        for i in range(SUCCESS_FRAMES + 5):
            _tick(eng, f + 2 + i)
            if eng.state == CRUISING:
                return
        pytest.fail("Engine did not return to CRUISING after SUCCESS")


# ---------------------------------------------------------------------------
# Difficulty adaptation
# ---------------------------------------------------------------------------


class TestDifficultyAdaptation:
    def test_difficulty_increases_after_three_successes(self):
        eng = SpaceEngine()
        eng._cruise_countdown = 5
        assert eng.difficulty == 1

        for _ in range(3):
            f = _advance_to_announce(eng)
            f = _advance_through_announce(eng, f)
            eng.scenario_type = SC_ASTEROID
            eng._steer_dir = 1
            ev = _tick(eng, f + 1, enc_b=2)
            assert ev == "success"
            # Advance through SUCCESS
            for i in range(SUCCESS_FRAMES + 5):
                _tick(eng, f + 2 + i)
                if eng.state == CRUISING:
                    break

        assert eng.difficulty == 2

    def test_difficulty_does_not_exceed_3(self):
        eng = SpaceEngine()
        eng.difficulty = 3
        eng._successes = 3
        eng._adjust_difficulty()
        assert eng.difficulty == 3

    def test_difficulty_decreases_after_two_timeouts(self):
        eng = SpaceEngine()
        eng.difficulty = 2
        eng._timeouts = 2
        eng._adjust_difficulty()
        assert eng.difficulty == 1

    def test_difficulty_does_not_go_below_1(self):
        eng = SpaceEngine()
        eng.difficulty = 1
        eng._timeouts = 2
        eng._adjust_difficulty()
        assert eng.difficulty == 1


# ---------------------------------------------------------------------------
# LED generation (smoke tests)
# ---------------------------------------------------------------------------


class TestLEDGeneration:
    def test_make_static_leds_returns_buffer(self):
        eng = SpaceEngine()
        buf = eng.make_static_leds(128)
        assert buf is not None
        assert len(buf) >= 16

    def test_success_leds_are_greenish(self):
        eng = SpaceEngine()
        eng.state = SUCCESS
        buf = eng.make_static_leds(200)
        for i in range(16):
            r, g, b = buf[i]
            assert g > r and g > b  # dominated by green

    def test_make_leds_animated_returns_buffer(self):
        eng = SpaceEngine()
        buf1 = eng.make_leds(0, 128)
        buf2 = eng.make_leds(64, 128)
        assert buf1 is not None
        assert buf2 is not None
