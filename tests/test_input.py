"""Tests for InputState — debouncing, edge detection, encoder tracking."""

from bodn.ui.input import BrightnessControl, EncoderAccumulator, InputState


class FakePin:
    """Minimal pin stub with settable value."""

    def __init__(self, val=1):
        self._val = val

    def value(self, v=None):
        if v is not None:
            self._val = v
        return self._val


class FakeEncoder:
    """Minimal encoder stub with .value and .sw attributes."""

    def __init__(self, val=0):
        self.value = val
        self.sw = FakePin(1)  # not pressed


def make_input(n_btn=8, n_sw=4, n_enc=3):
    buttons = [FakePin() for _ in range(n_btn)]
    switches = [FakePin() for _ in range(n_sw)]
    encoders = [FakeEncoder() for _ in range(n_enc)]
    t = [0]

    def time_ms():
        return t[0]

    inp = InputState(buttons, switches, encoders, time_ms)
    return inp, buttons, switches, encoders, t


def test_btn_just_pressed_fires_on_transition():
    inp, btns, _, _, t = make_input()
    # Button 0 not pressed
    t[0] = 0
    inp.scan()
    assert not inp.btn_just_pressed[0]

    # Press button 0 — register the change
    btns[0]._val = 0
    t[0] = 10
    inp.scan()
    assert not inp.btn_held[0]  # not yet stable

    # Wait for debounce to settle (30ms after change)
    t[0] = 50
    inp.scan()
    assert inp.btn_just_pressed[0]
    assert inp.btn_held[0]

    # Still held — should NOT be just_pressed again
    t[0] = 100
    inp.scan()
    assert not inp.btn_just_pressed[0]
    assert inp.btn_held[0]


def test_btn_just_released():
    inp, btns, _, _, t = make_input()
    # Press (register + settle)
    btns[0]._val = 0
    t[0] = 10
    inp.scan()
    t[0] = 50
    inp.scan()
    assert inp.btn_held[0]

    # Release (register + settle)
    btns[0]._val = 1
    t[0] = 60
    inp.scan()
    t[0] = 100
    inp.scan()
    assert inp.btn_just_released[0]
    assert not inp.btn_held[0]


def test_debounce_rejects_noise():
    inp, btns, _, _, t = make_input()
    # Rapidly toggle within debounce window
    btns[0]._val = 0
    t[0] = 0
    inp.scan()
    assert not inp.btn_held[0]  # not stable yet

    btns[0]._val = 1
    t[0] = 10
    inp.scan()
    assert not inp.btn_held[0]

    btns[0]._val = 0
    t[0] = 20
    inp.scan()
    assert not inp.btn_held[0]  # still bouncing

    # Settle
    t[0] = 55
    inp.scan()
    assert inp.btn_held[0]


def test_enc_delta():
    inp, _, _, encs, t = make_input()
    t[0] = 0
    inp.scan()
    assert inp.enc_delta[0] == 0

    encs[0].value = 5
    t[0] = 30
    inp.scan()
    assert inp.enc_delta[0] == 5
    assert inp.enc_pos[0] == 5

    # No change
    t[0] = 60
    inp.scan()
    assert inp.enc_delta[0] == 0


def test_enc_btn_pressed_edge_only():
    inp, _, _, encs, t = make_input()
    t[0] = 0
    inp.scan()
    assert not inp.enc_btn_pressed[1]

    # Press encoder 1 button (register + settle past 50ms debounce)
    encs[1].sw._val = 0
    t[0] = 10
    inp.scan()
    t[0] = 70
    inp.scan()
    assert inp.enc_btn_pressed[1]

    # Still held — no edge
    t[0] = 120
    inp.scan()
    assert not inp.enc_btn_pressed[1]


def test_any_btn_pressed():
    inp, btns, _, _, t = make_input()
    t[0] = 0
    inp.scan()
    assert not inp.any_btn_pressed()

    # Press button 3 (register + settle)
    btns[3]._val = 0
    t[0] = 10
    inp.scan()
    t[0] = 50
    inp.scan()
    assert inp.any_btn_pressed()
    assert inp.first_btn_pressed() == 3


def test_enc_btn_held():
    inp, _, _, encs, t = make_input()
    t[0] = 0
    inp.scan()
    assert not inp.enc_btn_held[0]

    # Press encoder 0 button (register + settle)
    encs[0].sw._val = 0
    t[0] = 10
    inp.scan()
    t[0] = 70
    inp.scan()
    assert inp.enc_btn_held[0]

    # Still held
    t[0] = 200
    inp.scan()
    assert inp.enc_btn_held[0]
    assert not inp.enc_btn_pressed[0]  # no edge

    # Release
    encs[0].sw._val = 1
    t[0] = 250
    inp.scan()
    t[0] = 300
    inp.scan()
    assert not inp.enc_btn_held[0]


def test_switch_states():
    inp, _, sws, _, t = make_input()
    t[0] = 0
    inp.scan()
    assert not inp.sw[0]

    sws[0]._val = 0
    inp.scan()
    assert inp.sw[0]

    sws[0]._val = 1
    inp.scan()
    assert not inp.sw[0]


# --- Encoder velocity tracking ---


def test_enc_velocity_computed_on_step():
    inp, _, _, encs, t = make_input()
    t[0] = 0
    inp.scan()

    # Move 1 step after 50ms → 1000/50 = 20 steps/s
    encs[0].value = 1
    t[0] = 50
    inp.scan()
    assert inp.enc_velocity[0] == 20


def test_enc_velocity_fast_spin():
    inp, _, _, encs, t = make_input()
    t[0] = 0
    inp.scan()

    # Move 3 steps in 10ms → 3000/10 = 300 steps/s
    encs[0].value = 3
    t[0] = 10
    inp.scan()
    assert inp.enc_velocity[0] == 300


def test_enc_velocity_decays_after_timeout():
    inp, _, _, encs, t = make_input()
    t[0] = 0
    inp.scan()

    encs[0].value = 1
    t[0] = 50
    inp.scan()
    assert inp.enc_velocity[0] > 0

    # No movement for 201ms → velocity should decay to 0
    t[0] = 251
    inp.scan()
    assert inp.enc_velocity[0] == 0


def test_enc_velocity_persists_within_timeout():
    inp, _, _, encs, t = make_input()
    t[0] = 0
    inp.scan()

    encs[0].value = 1
    t[0] = 50
    inp.scan()
    vel = inp.enc_velocity[0]
    assert vel > 0

    # No movement but within 200ms timeout → velocity stays
    t[0] = 200
    inp.scan()
    assert inp.enc_velocity[0] == vel


def test_enc_velocity_independent_per_encoder():
    inp, _, _, encs, t = make_input()
    t[0] = 0
    inp.scan()

    encs[0].value = 1
    t[0] = 100
    inp.scan()
    assert inp.enc_velocity[0] == 10
    assert inp.enc_velocity[1] == 0

    encs[1].value = 2
    t[0] = 110
    inp.scan()
    assert inp.enc_velocity[1] == 2 * 1000 // 110  # 2 steps since t=0 (init)


# --- EncoderAccumulator ---


def test_accumulator_basic_accumulation():
    acc = EncoderAccumulator(detents_per_unit=3)
    # 1 detent → not enough
    assert acc.update(1, 0) == 0
    # 2nd detent → not enough
    assert acc.update(1, 0) == 0
    # 3rd detent → triggers 1 unit
    assert acc.update(1, 0) == 1


def test_accumulator_negative_direction():
    acc = EncoderAccumulator(detents_per_unit=3)
    assert acc.update(-1, 0) == 0
    assert acc.update(-1, 0) == 0
    assert acc.update(-1, 0) == -1


def test_accumulator_fast_velocity_multiplier():
    acc = EncoderAccumulator(detents_per_unit=3, fast_threshold=400, fast_multiplier=3)
    # 1 detent at high velocity → 1*3 = 3 effective → 1 unit immediately
    assert acc.update(1, 500) == 1


def test_accumulator_slow_velocity_no_multiplier():
    acc = EncoderAccumulator(detents_per_unit=3, fast_threshold=400, fast_multiplier=3)
    # 1 detent at slow velocity → 1 effective → not enough
    assert acc.update(1, 100) == 0
    assert acc.update(1, 100) == 0
    assert acc.update(1, 100) == 1


def test_accumulator_remainder_carries():
    acc = EncoderAccumulator(detents_per_unit=3)
    # 5 detents at once → 1 unit with 2 remainder
    assert acc.update(5, 0) == 1
    # 1 more → remainder 2 + 1 = 3 → another unit
    assert acc.update(1, 0) == 1


def test_accumulator_zero_delta_returns_zero():
    acc = EncoderAccumulator(detents_per_unit=3)
    assert acc.update(0, 0) == 0
    assert acc.update(0, 500) == 0


def test_accumulator_reset():
    acc = EncoderAccumulator(detents_per_unit=3)
    acc.update(2, 0)  # accumulate 2
    acc.reset()
    # After reset, need full 3 detents again
    assert acc.update(1, 0) == 0
    assert acc.update(1, 0) == 0
    assert acc.update(1, 0) == 1


def test_accumulator_direction_change():
    acc = EncoderAccumulator(detents_per_unit=3)
    acc.update(2, 0)  # accumulate +2
    # Reverse direction: +2 + (-2) = 0
    acc.update(-2, 0)
    # Now 3 forward should trigger
    assert acc.update(1, 0) == 0
    assert acc.update(1, 0) == 0
    assert acc.update(1, 0) == 1


# --- BrightnessControl ---


def test_brightness_initial_value():
    bc = BrightnessControl(initial=128)
    assert bc.value == 128


def test_brightness_slow_turn_fine_adjustment():
    bc = BrightnessControl(initial=128, step=20)
    # 1 slow detent (dpu=1 default) → 1 unit → +20 brightness
    bc.update(1, 100)
    assert bc.value == 148  # +20


def test_brightness_fast_spin_big_jump():
    bc = BrightnessControl(initial=128, step=20)
    # 1 detent at high velocity → multiplied by 3 → 3 units → +60
    bc.update(1, 500)
    assert bc.value == 188


def test_brightness_clamps_to_max():
    bc = BrightnessControl(initial=240, step=20)
    bc.update(1, 500)  # +20 → 260, clamped to 255
    assert bc.value == 255


def test_brightness_clamps_to_min():
    bc = BrightnessControl(initial=20, step=20)
    bc.update(-1, 500)  # -20 → 0, clamped to 10
    assert bc.value == 10


def test_brightness_reset_clears_accumulator():
    bc = BrightnessControl(initial=128, step=20)
    bc.update(1, 100)  # 1 detent → +20 → 148
    bc.reset(value=200)
    assert bc.value == 200
    # After reset, 1 detent → +20
    bc.update(1, 100)
    assert bc.value == 220


def test_brightness_decrease_direction():
    bc = BrightnessControl(initial=128, step=20)
    # 1 detent down at dpu=1 → -20 per detent
    bc.update(-1, 100)
    assert bc.value == 108


def test_brightness_consistent_across_instances():
    """All instances with same params produce identical behavior."""
    controls = [BrightnessControl() for _ in range(4)]
    deltas = [(1, 100), (1, 100), (1, 100), (-1, 500), (1, 500)]
    for d, v in deltas:
        for bc in controls:
            bc.update(d, v)
    values = [bc.value for bc in controls]
    assert len(set(values)) == 1  # all identical
