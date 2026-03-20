"""Tests for InputState — debouncing, edge detection, encoder tracking."""

from bodn.ui.input import InputState


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
