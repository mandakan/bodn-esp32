"""Tests for HomeScreen — velocity scrolling and slide animation."""

from bodn.ui.home import HomeScreen, _ANIM_STEPS


class FakePin:
    def __init__(self, val=1):
        self._val = val

    def value(self, v=None):
        if v is not None:
            self._val = v
        return self._val


class FakeEncoder:
    def __init__(self, val=0):
        self.value = val
        self.sw = FakePin(1)


class FakeTft:
    def fill(self, c):
        pass

    def fill_rect(self, x, y, w, h, c):
        pass

    def rect(self, x, y, w, h, c):
        pass

    def text(self, s, x, y, c=0xFFFF):
        pass

    def pixel(self, x, y, c):
        pass

    def show(self):
        pass


class FakeTheme:
    width = 320
    height = 240
    BLACK = 0
    WHITE = 0xFFFF
    CYAN = 0x07FF
    RED = 0xF800
    GREEN = 0x07E0
    MUTED = 0x7BEF
    DIM = 0x4208
    HEADER_Y = 3
    CENTER_X = 160
    CENTER_Y = 120
    font_scale = 2


class FakeSessionMgr:
    sessions_remaining = 5

    def try_wake(self, name):
        pass


class FakeInp:
    def __init__(self):
        self.enc_delta = [0, 0, 0]
        self.enc_velocity = [0, 0, 0]
        self.btn_just_pressed = [False] * 8
        self.enc_btn_pressed = [False, False, False]
        self._encoders = [FakeEncoder(val=10) for _ in range(3)]
        self._prev_enc_pos = [10, 10, 10]

    def any_btn_pressed(self):
        return any(self.btn_just_pressed)

    def first_btn_pressed(self):
        return -1


class FakeManager:
    def __init__(self):
        self.inp = FakeInp()
        self.pushed = []

    def push(self, screen):
        self.pushed.append(screen)


def make_home(n_modes=4):
    modes = {f"mode{i}": lambda: None for i in range(n_modes)}
    order = [f"mode{i}" for i in range(n_modes)]
    session_mgr = FakeSessionMgr()
    home = HomeScreen(modes, session_mgr, order=order, settings={"hidden_modes": []})
    mgr = FakeManager()
    home.enter(mgr)
    # Consume initial dirty flag
    home.render(FakeTft(), FakeTheme(), 0)
    return home, mgr


def test_single_detent_moves_one_step():
    """Single detent at low velocity moves one mode step (dpu=1)."""
    home, mgr = make_home()
    inp = mgr.inp
    assert home._index == 0

    inp.enc_delta[0] = 1
    inp.enc_velocity[0] = 50
    home.update(inp, 1)
    assert home._index == 1


def test_fast_spin_skips_modes():
    """Fast spin: velocity multiplier makes fewer detents go further."""
    home, mgr = make_home(n_modes=6)
    inp = mgr.inp

    # 2 detents at high velocity → 2*2=4 effective, 4//1=4 units
    inp.enc_delta[0] = 2
    inp.enc_velocity[0] = 500
    home.update(inp, 1)
    assert home._index == 4


def test_mode_change_starts_animation():
    """Mode change triggers slide animation."""
    home, mgr = make_home()
    inp = mgr.inp

    # Trigger a mode change (1 detent = 1 unit at dpu=1)
    inp.enc_delta[0] = 1
    inp.enc_velocity[0] = 50
    home.update(inp, 1)
    assert home._anim_step == 0
    assert home._anim_dir == 1  # forward


def test_animation_advances_each_frame():
    """Animation progresses one step per update call."""
    home, mgr = make_home()
    inp = mgr.inp

    # Trigger mode change
    inp.enc_delta[0] = 1
    inp.enc_velocity[0] = 50
    home.update(inp, 1)
    assert home._anim_step == 0

    # Advance frames with no encoder input
    inp.enc_delta[0] = 0
    inp.enc_velocity[0] = 0
    for i in range(1, _ANIM_STEPS + 1):
        home.update(inp, 1 + i)
        assert home._anim_step == i


def test_animation_stops_redraws_when_done():
    """After animation completes, no more redraws requested."""
    home, mgr = make_home()
    inp = mgr.inp

    # Trigger mode change
    inp.enc_delta[0] = 1
    inp.enc_velocity[0] = 50
    home.update(inp, 1)

    # Run through animation
    inp.enc_delta[0] = 0
    inp.enc_velocity[0] = 0
    for i in range(_ANIM_STEPS):
        assert home.needs_redraw()
        home.render(FakeTft(), FakeTheme(), i + 2)
        home.update(inp, i + 3)

    # Final render
    home.render(FakeTft(), FakeTheme(), _ANIM_STEPS + 2)

    # Now idle — no more redraws
    home.update(inp, _ANIM_STEPS + 3)
    assert not home.needs_redraw()


def test_mid_animation_encoder_restarts():
    """Encoder input during animation cancels and starts fresh."""
    home, mgr = make_home()
    inp = mgr.inp

    # Trigger first mode change (1 detent = 1 unit at dpu=1)
    inp.enc_delta[0] = 1
    inp.enc_velocity[0] = 50
    home.update(inp, 1)
    assert home._index == 1
    assert home._anim_step == 0

    # Advance 2 frames
    inp.enc_delta[0] = 0
    home.update(inp, 2)
    home.update(inp, 3)
    assert home._anim_step == 2

    # New encoder input mid-animation → restarts
    inp.enc_delta[0] = 1
    inp.enc_velocity[0] = 50
    home.update(inp, 4)
    assert home._index == 2
    assert home._anim_step == 0  # restarted


def test_backward_turn_animation_direction():
    """Backward turn sets animation direction to -1."""
    home, mgr = make_home()
    inp = mgr.inp

    inp.enc_delta[0] = -1
    inp.enc_velocity[0] = 50
    home.update(inp, 1)
    assert home._anim_dir == -1


def test_circular_wrapping():
    """Mode index wraps around circularly."""
    home, mgr = make_home(n_modes=3)
    inp = mgr.inp

    # Go backward from index 0 → should wrap to last
    inp.enc_delta[0] = -1
    inp.enc_velocity[0] = 50
    home.update(inp, 1)
    assert home._index == 2


def test_accumulator_reset_on_enter():
    """Accumulator resets when entering the screen."""
    home, mgr = make_home()
    inp = mgr.inp

    # Move one step
    inp.enc_delta[0] = 1
    inp.enc_velocity[0] = 50
    home.update(inp, 1)
    assert home._index == 1

    # Re-enter screen — index preserved but accumulator reset
    home.enter(mgr)
    assert home._accum == 0


def test_button_still_enters_mode():
    """Button press still enters the selected mode (no regression)."""
    home, mgr = make_home()
    inp = mgr.inp

    inp.btn_just_pressed[0] = True
    home.update(inp, 1)
    assert len(mgr.pushed) == 1


def test_enc_button_still_enters_mode():
    """Encoder button press still enters the selected mode."""
    home, mgr = make_home()
    inp = mgr.inp

    inp.enc_btn_pressed[0] = True
    home.update(inp, 1)
    assert len(mgr.pushed) == 1


def test_anim_offset_idle_is_zero():
    """When animation is idle, offset is 0."""
    home, _ = make_home()
    assert home._anim_x(320) == 0


def test_anim_offset_during_animation():
    """During animation, offset decreases toward 0."""
    home, mgr = make_home()
    inp = mgr.inp

    inp.enc_delta[0] = 2
    inp.enc_velocity[0] = 50
    home.update(inp, 1)

    offsets = []
    for step in range(_ANIM_STEPS):
        offsets.append(home._anim_x(320))
        inp.enc_delta[0] = 0
        home.update(inp, step + 2)

    # Offsets should decrease in magnitude
    abs_offsets = [abs(o) for o in offsets]
    assert abs_offsets[0] > abs_offsets[-1]
    # Final position after animation completes
    assert home._anim_x(320) == 0
