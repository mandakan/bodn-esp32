"""Tests for ScreenManager — push/pop/replace, overlay, tick ordering."""

from bodn.ui.screen import Screen, ScreenManager


class FakeTft:
    """Minimal TFT stub tracking calls."""

    def __init__(self):
        self.calls = []

    def fill(self, color):
        self.calls.append(("fill", color))

    def show(self):
        self.calls.append(("show",))

    def text(self, *a, **kw):
        pass

    def rect(self, *a, **kw):
        pass

    def fill_rect(self, *a, **kw):
        pass

    def pixel(self, *a, **kw):
        return 0


class FakeTheme:
    BLACK = 0
    WHITE = 0xFFFF
    width = 128
    height = 160


class FakeInput:
    def __init__(self):
        self.scanned = 0

    def scan(self):
        self.scanned += 1


class SpyScreen(Screen):
    def __init__(self, name="spy"):
        self.name = name
        self.entered = False
        self.exited = False
        self.updates = 0
        self.renders = 0

    def enter(self, manager):
        self.entered = True

    def exit(self):
        self.exited = True

    def update(self, inp, frame):
        self.updates += 1

    def render(self, tft, theme, frame):
        self.renders += 1


def make_manager():
    return ScreenManager(FakeTft(), FakeTheme(), FakeInput())


def test_push_calls_enter():
    mgr = make_manager()
    s = SpyScreen()
    mgr.push(s)
    assert s.entered
    assert mgr.active is s


def test_pop_calls_exit():
    mgr = make_manager()
    s = SpyScreen()
    mgr.push(s)
    result = mgr.pop()
    assert result is s
    assert s.exited
    assert mgr.active is None


def test_replace_calls_exit_and_enter():
    mgr = make_manager()
    a = SpyScreen("a")
    b = SpyScreen("b")
    mgr.push(a)
    mgr.replace(b)
    assert a.exited
    assert b.entered
    assert mgr.active is b


def test_pop_empty_returns_none():
    mgr = make_manager()
    assert mgr.pop() is None


def test_tick_calls_scan_update_render():
    mgr = make_manager()
    s = SpyScreen()
    mgr.push(s)
    mgr.tick()
    assert mgr.inp.scanned == 1
    assert s.updates == 1
    assert s.renders == 1


def test_overlay_renders_after_screen():
    mgr = make_manager()
    order = []
    s = SpyScreen()
    s.render = lambda tft, theme, frame: order.append("screen")
    o = SpyScreen()
    o.render = lambda tft, theme, frame: order.append("overlay")
    mgr.push(s)
    mgr.set_overlay(o)
    mgr.tick()
    assert order == ["screen", "overlay"]


def test_overlay_takes_over_skips_screen_render():
    mgr = make_manager()
    s = SpyScreen()
    o = SpyScreen()
    o.takes_over = True
    mgr.push(s)
    mgr.set_overlay(o)
    mgr.tick()
    assert s.renders == 0
    assert o.renders == 1


def test_tick_with_empty_stack_does_not_crash():
    mgr = make_manager()
    mgr.tick()  # should not raise


def test_stack_depth():
    mgr = make_manager()
    a = SpyScreen("a")
    b = SpyScreen("b")
    mgr.push(a)
    mgr.push(b)
    assert mgr.active is b
    mgr.pop()
    assert mgr.active is a
