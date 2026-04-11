# tests/test_rulefollow_rules.py — host-side tests for the Rule Follow engine

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "firmware"))

from bodn.rulefollow_rules import (
    RuleFollowEngine,
    READY,
    SHOW_RULE,
    STIMULUS,
    CORRECT,
    WRONG,
    RULE_SWITCH,
    GAME_OVER,
    RULE_MATCH,
    RULE_OPPOSITE,
    SHOW_RULE_MS,
    STIMULUS_TIMEOUT_MS,
    CORRECT_MS,
    WRONG_MS,
    RULE_SWITCH_MS,
    NUM_BUTTONS,
    RULE_COLORS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DT = 33  # default tick step in ms (~30 fps)


def _tick(eng, dt=DT, btn=-1):
    """Advance the engine by one tick."""
    return eng.update(btn, dt)


def _advance_ms(eng, ms, btn=-1):
    """Fast-forward the engine by *ms* milliseconds in DT-sized steps."""
    elapsed = 0
    while elapsed < ms:
        step = min(DT, ms - elapsed)
        eng.update(btn, step)
        elapsed += step
    return eng.state


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_initial_state_is_ready():
    eng = RuleFollowEngine()
    assert eng.state == READY
    assert eng.score == 0
    assert eng.total == 0
    assert eng.current_rule == RULE_MATCH


def test_any_button_starts_game():
    eng = RuleFollowEngine()
    _tick(eng, btn=0)
    assert eng.state == SHOW_RULE
    assert eng.current_rule == RULE_MATCH


def test_show_rule_transitions_to_stimulus():
    eng = RuleFollowEngine()
    _tick(eng, btn=0)
    assert eng.state == SHOW_RULE

    _advance_ms(eng, SHOW_RULE_MS + DT)
    assert eng.state == STIMULUS
    assert 0 <= eng.stimulus_button < NUM_BUTTONS
    assert 0 <= eng.correct_button < NUM_BUTTONS


def test_correct_match_rule():
    eng = RuleFollowEngine()
    _tick(eng, btn=0)
    _advance_ms(eng, SHOW_RULE_MS + DT)
    assert eng.state == STIMULUS
    assert eng.current_rule == RULE_MATCH

    # In match rule, correct = stimulus
    correct = eng.stimulus_button
    _tick(eng, btn=correct)
    assert eng.state == CORRECT
    assert eng.score == 1
    assert eng.total == 1
    assert eng.streak == 1


def test_wrong_match_rule():
    eng = RuleFollowEngine()
    _tick(eng, btn=0)
    _advance_ms(eng, SHOW_RULE_MS + DT)
    assert eng.state == STIMULUS

    # Press wrong button
    wrong = (eng.stimulus_button + 1) % NUM_BUTTONS
    _tick(eng, btn=wrong)
    assert eng.state == WRONG
    assert eng.score == 0
    assert eng.total == 1
    assert eng.streak == 0


def test_opposite_rule_mapping():
    # Static method test — no game state needed
    assert RuleFollowEngine.get_correct(0, RULE_MATCH) == 0
    assert RuleFollowEngine.get_correct(1, RULE_MATCH) == 1
    assert RuleFollowEngine.get_correct(0, RULE_OPPOSITE) == 2
    assert RuleFollowEngine.get_correct(1, RULE_OPPOSITE) == 3
    assert RuleFollowEngine.get_correct(2, RULE_OPPOSITE) == 0
    assert RuleFollowEngine.get_correct(3, RULE_OPPOSITE) == 1


def test_correct_opposite_rule():
    eng = RuleFollowEngine()
    _tick(eng, btn=0)
    _advance_ms(eng, SHOW_RULE_MS + DT)
    # Force opposite rule
    eng.current_rule = RULE_OPPOSITE
    eng.correct_button = eng.get_correct(eng.stimulus_button, RULE_OPPOSITE)

    correct = eng.correct_button
    _tick(eng, btn=correct)
    assert eng.state == CORRECT
    assert eng.score == 1


def test_stimulus_timeout():
    eng = RuleFollowEngine()
    _tick(eng, btn=0)
    _advance_ms(eng, SHOW_RULE_MS + DT)
    assert eng.state == STIMULUS

    # No button press, wait for timeout
    _advance_ms(eng, STIMULUS_TIMEOUT_MS + DT)
    assert eng.state == WRONG
    assert eng.score == 0
    assert eng.total == 1


def test_correct_advances_to_next_stimulus():
    eng = RuleFollowEngine(rounds=12)
    _tick(eng, btn=0)
    _advance_ms(eng, SHOW_RULE_MS + DT)
    assert eng.state == STIMULUS

    correct = eng.correct_button
    _tick(eng, btn=correct)
    assert eng.state == CORRECT

    # After CORRECT_MS, should advance (stimulus or rule_switch)
    _advance_ms(eng, CORRECT_MS + DT)
    assert eng.state in (STIMULUS, RULE_SWITCH, SHOW_RULE)


def test_wrong_advances_to_next_stimulus():
    eng = RuleFollowEngine(rounds=12)
    _tick(eng, btn=0)
    _advance_ms(eng, SHOW_RULE_MS + DT)

    wrong = (eng.correct_button + 1) % NUM_BUTTONS
    _tick(eng, btn=wrong)
    assert eng.state == WRONG

    _advance_ms(eng, WRONG_MS + DT)
    assert eng.state in (STIMULUS, RULE_SWITCH, SHOW_RULE)


def _play_round(eng, press_correct=True):
    """Helper: advance through one full stimulus->response cycle."""
    # Wait until we reach STIMULUS
    safety = 0
    while eng.state != STIMULUS:
        _tick(eng)
        safety += 1
        if safety > 500:
            raise RuntimeError("Stuck waiting for STIMULUS, state={}".format(eng.state))

    if press_correct:
        btn = eng.correct_button
    else:
        btn = (eng.correct_button + 1) % NUM_BUTTONS
    _tick(eng, btn=btn)

    # Wait for feedback to finish
    wait = CORRECT_MS if eng.state == CORRECT else WRONG_MS
    _advance_ms(eng, wait + DT)


def test_rule_switch_happens():
    # Use switch_min=switch_max=2 so rule switches after exactly 2 correct
    eng = RuleFollowEngine(rounds=12, switch_min=2, switch_max=2)
    _tick(eng, btn=0)
    assert eng.current_rule == RULE_MATCH

    # Play 2 correct rounds — should trigger rule switch
    for _ in range(2):
        _play_round(eng, press_correct=True)

    assert eng.state == RULE_SWITCH
    old_rule = RULE_MATCH

    # Wait for switch to complete
    _advance_ms(eng, RULE_SWITCH_MS + DT)
    assert eng.state == SHOW_RULE
    assert eng.current_rule != old_rule


def test_game_over_after_all_rounds():
    eng = RuleFollowEngine(rounds=3, switch_min=99, switch_max=99)
    _tick(eng, btn=0)

    for _ in range(3):
        _play_round(eng, press_correct=True)

    assert eng.state == GAME_OVER
    assert eng.score == 3
    assert eng.total == 3


def test_game_over_restart():
    eng = RuleFollowEngine(rounds=1, switch_min=99, switch_max=99)
    _tick(eng, btn=0)
    _play_round(eng, press_correct=True)
    assert eng.state == GAME_OVER

    _tick(eng, btn=0)
    assert eng.state == SHOW_RULE
    assert eng.score == 0


def test_streak_tracking():
    eng = RuleFollowEngine(rounds=6, switch_min=99, switch_max=99)
    _tick(eng, btn=0)

    # 2 correct
    _play_round(eng, press_correct=True)
    _play_round(eng, press_correct=True)
    assert eng.streak == 2
    assert eng.best_streak == 2

    # 1 wrong
    _play_round(eng, press_correct=False)
    assert eng.streak == 0
    assert eng.best_streak == 2

    # 1 correct
    _play_round(eng, press_correct=True)
    assert eng.streak == 1
    assert eng.best_streak == 2


def test_score_only_counts_correct():
    eng = RuleFollowEngine(rounds=4, switch_min=99, switch_max=99)
    _tick(eng, btn=0)

    _play_round(eng, press_correct=True)
    _play_round(eng, press_correct=False)
    _play_round(eng, press_correct=True)
    _play_round(eng, press_correct=False)

    assert eng.state == GAME_OVER
    assert eng.score == 2
    assert eng.total == 4


def test_make_static_leds_returns_correct_size():
    from bodn.patterns import N_LEDS

    eng = RuleFollowEngine()
    leds = eng.make_static_leds(brightness=128)
    assert len(leds) == N_LEDS


def test_make_static_leds_correct_is_green():
    from bodn.patterns import N_STICKS

    eng = RuleFollowEngine()
    eng.state = CORRECT
    eng._state_ms = 0
    leds = eng.make_static_leds(brightness=200)
    # All stick LEDs should be green-ish
    for i in range(N_STICKS):
        r, g, b = leds[i]
        assert g > r and g > b, f"LED {i} should be green: {leds[i]}"


def test_make_static_leds_stimulus_highlights_button():
    eng = RuleFollowEngine()
    eng.state = STIMULUS
    eng.stimulus_button = 1
    eng.current_rule = RULE_MATCH
    eng._state_ms = 0
    leds = eng.make_static_leds(brightness=200)
    # Stimulus button LED should be brighter than others
    stim_brightness = sum(leds[1])
    other_brightness = sum(leds[0])
    assert stim_brightness > other_brightness


def test_reset_clears_state():
    eng = RuleFollowEngine()
    _tick(eng, btn=0)
    eng.score = 5
    eng.total = 10
    eng.streak = 3

    eng.reset()
    assert eng.state == READY
    assert eng.score == 0
    assert eng.total == 0
    assert eng.streak == 0
    assert eng.current_rule == RULE_MATCH


def test_no_button_stays_in_ready():
    eng = RuleFollowEngine()
    _tick(eng)
    assert eng.state == READY


def test_rule_color_property():
    eng = RuleFollowEngine()
    eng.current_rule = RULE_MATCH
    assert eng.rule_color == RULE_COLORS[RULE_MATCH]
    eng.current_rule = RULE_OPPOSITE
    assert eng.rule_color == RULE_COLORS[RULE_OPPOSITE]


def test_buttons_beyond_num_ignored():
    eng = RuleFollowEngine()
    _tick(eng, btn=0)
    _advance_ms(eng, SHOW_RULE_MS + DT)
    assert eng.state == STIMULUS

    # Press button 5 (beyond NUM_BUTTONS=4) — should be ignored
    _tick(eng, btn=5)
    assert eng.state == STIMULUS  # still waiting
