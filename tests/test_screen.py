"""Tests for ScreenManager — push/pop/replace, overlay, tick ordering."""

from bodn.ui.screen import Screen, ScreenManager


class FakeTft:
    """Minimal TFT stub tracking calls with dirty rect support."""

    def __init__(self):
        self.calls = []
        self._drect = None
        self.width = 128
        self.height = 160

    def mark_dirty(self, x, y, w, h):
        x1 = x + w
        y1 = y + h
        if self._drect is None:
            self._drect = [x, y, x1, y1]
        else:
            d = self._drect
            if x < d[0]:
                d[0] = x
            if y < d[1]:
                d[1] = y
            if x1 > d[2]:
                d[2] = x1
            if y1 > d[3]:
                d[3] = y1

    def reset_dirty(self):
        self._drect = None

    def show_dirty(self):
        if self._drect is None:
            return
        d = self._drect
        self._drect = None
        w, h = d[2] - d[0], d[3] - d[1]
        if w >= self.width and h >= self.height:
            self.calls.append(("show",))
        else:
            self.calls.append(("show_rect", d[0], d[1], w, h))

    def fill(self, color):
        self.calls.append(("fill", color))
        self._drect = [0, 0, self.width, self.height]

    def show(self):
        self.calls.append(("show",))

    def show_rect(self, x, y, w, h):
        self.calls.append(("show_rect", x, y, w, h))

    def text(self, *a, **kw):
        self.mark_dirty(a[1] if len(a) > 1 else 0, a[2] if len(a) > 2 else 0, 8, 8)

    def rect(self, *a, **kw):
        if len(a) >= 4:
            self.mark_dirty(a[0], a[1], a[2], a[3])

    def fill_rect(self, *a, **kw):
        if len(a) >= 4:
            self.mark_dirty(a[0], a[1], a[2], a[3])

    def pixel(self, *a, **kw):
        if len(a) >= 2:
            self.mark_dirty(a[0], a[1], 1, 1)
        return 0


class FakeTheme:
    BLACK = 0
    WHITE = 0xFFFF
    width = 128
    height = 160


class _FakeGestures:
    def reset(self):
        pass


class FakeInput:
    def __init__(self):
        self.scanned = 0
        self.gestures = _FakeGestures()

    def scan(self):
        self.scanned += 1

    def consume(self):
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


def test_pop_marks_revealed_screen_dirty():
    """When a screen is popped, the screen underneath must be redrawn."""

    class DirtyScreen(Screen):
        def __init__(self):
            self._dirty = False
            self.renders = 0

        def enter(self, manager):
            self._dirty = True

        def needs_redraw(self):
            return self._dirty

        def render(self, tft, theme, frame):
            self._dirty = False
            self.renders += 1

    mgr = make_manager()
    bottom = DirtyScreen()
    top = SpyScreen()
    mgr.push(bottom)
    mgr.tick()  # renders bottom, clears its dirty flag
    assert bottom.renders == 1
    assert not bottom._dirty

    mgr.push(top)
    mgr.tick()  # renders top
    mgr.pop()  # should mark bottom as dirty again

    assert bottom._dirty
    mgr.tick()  # should render bottom
    assert bottom.renders == 2


# --- invalidate_rect / request_show partial-push tests ---


def test_request_show_no_args_calls_full_show():
    """request_show() without args triggers tft.show() on next tick."""
    mgr = make_manager()
    s = SpyScreen()
    s.needs_redraw = lambda: False
    mgr.push(s)
    mgr.tick()  # consume initial dirty render
    mgr.tft.calls.clear()

    mgr.request_show()
    mgr.tick()

    assert ("show",) in mgr.tft.calls
    assert not any(c[0] == "show_rect" for c in mgr.tft.calls)


def test_request_show_with_rect_calls_show_rect():
    """request_show(x, y, w, h) triggers tft.show_rect() on next tick."""
    mgr = make_manager()
    s = SpyScreen()
    s.needs_redraw = lambda: False
    mgr.push(s)
    mgr.tick()
    mgr.tft.calls.clear()

    mgr.request_show(0, 0, 32, 4)
    mgr.tick()

    assert ("show_rect", 0, 0, 32, 4) in mgr.tft.calls
    assert ("show",) not in mgr.tft.calls


def test_invalidate_rect_merges_bounding_box():
    """Multiple invalidate_rect calls are merged into their bounding box."""
    mgr = make_manager()
    mgr.invalidate_rect(10, 20, 30, 5)
    mgr.invalidate_rect(5, 18, 10, 10)
    # Union: x=5, y=18, x2=max(40,15)=40, y2=max(25,28)=28 → w=35, h=10
    assert mgr._dirty_rect == (5, 18, 35, 10)


def test_dirty_rect_cleared_after_partial_push():
    """_dirty_rect is reset to None after the push tick."""
    mgr = make_manager()
    s = SpyScreen()
    s.needs_redraw = lambda: False
    mgr.push(s)
    mgr.tick()

    mgr.request_show(0, 0, 10, 10)
    assert mgr._dirty_rect == (0, 0, 10, 10)
    mgr.tick()
    assert mgr._dirty_rect is None


def test_dirty_rect_cleared_on_full_render():
    """_dirty_rect is also cleared when a full render happens."""
    mgr = make_manager()
    mgr.invalidate_rect(5, 5, 20, 20)
    s = SpyScreen()
    mgr.push(s)
    mgr.tick()
    assert mgr._dirty_rect is None
