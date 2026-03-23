"""Tests for SecondaryDisplay two-zone layout and StatusStrip."""

from bodn.ui.screen import Screen
from bodn.ui.secondary import SecondaryDisplay, CONTENT_SIZE, STATUS_THICK
from bodn.ui.catface import CatFaceScreen, NEUTRAL, CURIOUS, HAPPY, SLEEPY


class FakeTft:
    def __init__(self):
        self.calls = []

    def fill(self, color):
        self.calls.append(("fill", color))

    def fill_rect(self, x, y, w, h, color):
        self.calls.append(("fill_rect", x, y, w, h, color))

    def show(self):
        self.calls.append(("show",))

    def show_rect(self, x, y, w, h):
        self.calls.append(("show_rect", x, y, w, h))

    def text(self, *a, **kw):
        pass

    def rect(self, *a, **kw):
        pass

    def hline(self, *a, **kw):
        self.calls.append(("hline", *a))

    def pixel(self, *a, **kw):
        return 0


class FakeTheme:
    BLACK = 0
    WHITE = 0xFFFF
    CYAN = 0x07FF
    GREEN = 0x07E0
    RED = 0xF800
    AMBER = 0xFDE0
    ORANGE = 0xFC00
    MAGENTA = 0xF81F
    MUTED = 0x5145
    width = 128
    height = 160


class SpyScreen(Screen):
    def __init__(self):
        self.entered = False
        self.exited = False
        self.renders = 0
        self._dirty = True

    def enter(self, display):
        self.entered = True

    def exit(self):
        self.exited = True

    def needs_redraw(self):
        return self._dirty

    def render(self, tft, theme, frame):
        self.renders += 1
        self._dirty = False


class AlwaysCleanScreen(Screen):
    def __init__(self):
        self.renders = 0

    def enter(self, display):
        pass

    def needs_redraw(self):
        return False

    def render(self, tft, theme, frame):
        self.renders += 1


def make_display(landscape=False):
    return SecondaryDisplay(FakeTft(), FakeTheme(), landscape=landscape)


# --- Zone geometry ---


def test_zone_constants():
    assert CONTENT_SIZE == 128
    assert STATUS_THICK == 32


def test_portrait_geometry():
    d = make_display(landscape=False)
    # Content at top-left, status below
    assert d._content_rect == (0, 0, 128, 128)
    assert d._status_rect == (0, 128, 128, 32)


def test_landscape_geometry():
    d = make_display(landscape=True)
    # Status on the left, content on the right
    assert d._status_rect == (0, 0, 32, 128)
    assert d._content_rect == (32, 0, 128, 128)


# --- set_content / set_status ---


def test_set_content_calls_enter():
    d = make_display()
    s = SpyScreen()
    d.set_content(s)
    assert s.entered


def test_set_status_calls_enter():
    d = make_display()
    s = SpyScreen()
    d.set_status(s)
    assert s.entered


def test_replace_content_calls_exit():
    d = make_display()
    a = SpyScreen()
    b = SpyScreen()
    d.set_content(a)
    d.set_content(b)
    assert a.exited
    assert b.entered


def test_replace_status_calls_exit():
    d = make_display()
    a = SpyScreen()
    b = SpyScreen()
    d.set_status(a)
    d.set_status(b)
    assert a.exited
    assert b.entered


# --- Independent dirty tracking ---


def test_tick_renders_both_zones_when_dirty():
    d = make_display()
    content = SpyScreen()
    status = SpyScreen()
    d.set_content(content)
    d.set_status(status)
    d.tick()
    assert content.renders == 1
    assert status.renders == 1


def test_clean_content_not_rerendered():
    d = make_display()
    content = SpyScreen()
    status = SpyScreen()
    d.set_content(content)
    d.set_status(status)
    d.tick()  # both render
    # Now content is clean, status is clean
    d.tick()
    assert content.renders == 1
    assert status.renders == 1


def test_only_dirty_zone_redrawn():
    d = make_display()
    content = SpyScreen()
    status = AlwaysCleanScreen()
    d.set_content(content)
    d.set_status(status)
    d.tick()  # content dirty → renders, status clean but initial dirty → renders
    assert content.renders == 1
    assert status.renders == 1
    # Invalidate only content
    d.invalidate("content")
    d.tick()
    assert content.renders == 2
    assert status.renders == 1


def test_invalidate_status_only():
    d = make_display()
    content = AlwaysCleanScreen()
    status = SpyScreen()
    d.set_content(content)
    d.set_status(status)
    d.tick()  # initial dirty
    d.invalidate("status")
    d.tick()
    assert content.renders == 1
    assert status.renders == 2


def test_no_show_when_nothing_dirty():
    d = make_display()
    content = SpyScreen()
    d.set_content(content)
    d.tick()  # renders and shows
    d.tft.calls.clear()
    d.tick()  # nothing dirty
    show_calls = [c for c in d.tft.calls if c[0] == "show"]
    assert len(show_calls) == 0


def test_show_called_once_per_tick():
    d = make_display()
    content = SpyScreen()
    status = SpyScreen()
    d.set_content(content)
    d.set_status(status)
    d.tft.calls.clear()
    d.tick()
    show_calls = [c for c in d.tft.calls if c[0] == "show"]
    assert len(show_calls) == 1


def test_content_zone_cleared_at_correct_region():
    d = make_display()
    d.set_content(SpyScreen())
    d.tft.calls.clear()
    d.tick()
    fill_rects = [c for c in d.tft.calls if c[0] == "fill_rect"]
    # Content zone clear: (0, 0, 128, 128, BLACK)
    assert ("fill_rect", 0, 0, 128, 128, 0) in fill_rects


def test_status_zone_cleared_at_correct_region():
    d = make_display()
    d.set_status(SpyScreen())
    d.tft.calls.clear()
    d.tick()
    fill_rects = [c for c in d.tft.calls if c[0] == "fill_rect"]
    # Status zone clear: (0, 128, 128, 32, BLACK)
    assert ("fill_rect", 0, 128, 128, 32, 0) in fill_rects


def test_landscape_content_zone_cleared_at_correct_region():
    d = make_display(landscape=True)
    d.set_content(SpyScreen())
    d.tft.calls.clear()
    d.tick()
    fill_rects = [c for c in d.tft.calls if c[0] == "fill_rect"]
    # Content zone clear: (32, 0, 128, 128, BLACK)
    assert ("fill_rect", 32, 0, 128, 128, 0) in fill_rects


def test_landscape_status_zone_cleared_at_correct_region():
    d = make_display(landscape=True)
    d.set_status(SpyScreen())
    d.tft.calls.clear()
    d.tick()
    fill_rects = [c for c in d.tft.calls if c[0] == "fill_rect"]
    # Status zone clear: (0, 0, 32, 128, BLACK)
    assert ("fill_rect", 0, 0, 32, 128, 0) in fill_rects


def test_transition_clears_zone_but_normal_redraw_does_not():
    """set_content() should clear the zone once; subsequent redraws should not.

    This is critical for performance — screens handle their own partial
    clearing on normal redraws, so SecondaryDisplay must not fill_rect
    the entire zone every time.
    """
    d = make_display()
    content = SpyScreen()
    d.set_content(content)

    # First tick — transition, should have fill_rect from SecondaryDisplay
    d.tft.calls.clear()
    d.tick()
    fill_rects = [c for c in d.tft.calls if c[0] == "fill_rect"]
    assert ("fill_rect", 0, 0, 128, 128, 0) in fill_rects

    # Mark screen dirty again (simulating a normal redraw, not a transition)
    content._dirty = True
    d.tft.calls.clear()
    d.tick()
    fill_rects = [c for c in d.tft.calls if c[0] == "fill_rect"]
    # SecondaryDisplay should NOT have issued a zone clear
    assert ("fill_rect", 0, 0, 128, 128, 0) not in fill_rects
    # But the screen's render() should still have been called
    assert content.renders == 2


# --- Legacy alias ---


def test_set_screen_aliases_set_content():
    d = make_display()
    s = SpyScreen()
    d.set_screen(s)
    assert s.entered
    d.tick()
    assert s.renders == 1


# --- CatFaceScreen ---


def test_catface_initial_emotion():
    cat = CatFaceScreen()
    assert cat._emotion == NEUTRAL


def test_catface_set_emotion_marks_dirty():
    cat = CatFaceScreen()
    cat.enter(None)
    # Consume initial dirty
    assert cat.needs_redraw()
    cat.render(FakeTft(), FakeTheme(), 1)
    assert not cat.needs_redraw()
    cat.set_emotion(HAPPY)
    assert cat.needs_redraw()


def test_catface_same_emotion_not_dirty():
    cat = CatFaceScreen()
    cat.enter(None)
    cat.needs_redraw()
    cat.render(FakeTft(), FakeTheme(), 1)
    cat.set_emotion(NEUTRAL)  # same as current
    assert not cat.needs_redraw()


def test_catface_all_emotions_render():
    """All four emotions should render without errors."""
    tft = FakeTft()
    theme = FakeTheme()
    cat = CatFaceScreen()
    cat.enter(None)
    for emotion in (NEUTRAL, CURIOUS, HAPPY, SLEEPY):
        cat.set_emotion(emotion)
        cat._dirty = True
        cat.render(tft, theme, 1)


# --- Zone-aware partial push tests ---


def test_status_only_update_uses_show_rect():
    """When only the status strip changes, show_rect is used for just that zone."""
    d = make_display()
    content = SpyScreen()
    status = SpyScreen()
    d.set_content(content)
    d.set_status(status)
    d.tick()  # consume transitions
    d.tft.calls.clear()

    # Only status dirty
    status._dirty = True
    d.tick()

    show_rects = [c for c in d.tft.calls if c[0] == "show_rect"]
    full_shows = [c for c in d.tft.calls if c[0] == "show"]
    assert ("show_rect", 0, 128, 128, 32) in show_rects
    assert len(full_shows) == 0


def test_content_only_update_uses_show_rect():
    """When only the content zone changes, show_rect is used for just that zone."""
    d = make_display()
    content = SpyScreen()
    status = SpyScreen()
    d.set_content(content)
    d.set_status(status)
    d.tick()  # consume transitions
    d.tft.calls.clear()

    # Only content dirty
    content._dirty = True
    d.tick()

    show_rects = [c for c in d.tft.calls if c[0] == "show_rect"]
    full_shows = [c for c in d.tft.calls if c[0] == "show"]
    assert ("show_rect", 0, 0, 128, 128) in show_rects
    assert len(full_shows) == 0


def test_both_zones_dirty_uses_full_show():
    """When both zones need redraw, a single full show() is used."""
    d = make_display()
    content = SpyScreen()
    status = SpyScreen()
    d.set_content(content)
    d.set_status(status)
    d.tick()  # consume transitions
    d.tft.calls.clear()

    content._dirty = True
    status._dirty = True
    d.tick()

    show_rects = [c for c in d.tft.calls if c[0] == "show_rect"]
    full_shows = [c for c in d.tft.calls if c[0] == "show"]
    assert len(show_rects) == 0
    assert len(full_shows) == 1


# --- Viewport offset tests ---


def test_viewport_offsets_drawing_calls():
    """Content viewport should offset all drawing operations."""
    from bodn.ui.secondary import _Viewport

    tft = FakeTft()
    vp = _Viewport(tft, 32, 0, 128, 128)
    vp.fill_rect(0, 0, 10, 10, 0xFFFF)
    assert ("fill_rect", 32, 0, 10, 10, 0xFFFF) in tft.calls

    tft.calls.clear()
    vp.hline(5, 10, 20, 0x1234)
    assert tft.calls[0] == ("hline", 37, 10, 20, 0x1234)


def test_viewport_dimensions():
    """Viewport exposes zone dimensions, not full display dimensions."""
    from bodn.ui.secondary import _Viewport

    tft = FakeTft()
    vp = _Viewport(tft, 32, 0, 128, 128)
    assert vp.width == 128
    assert vp.height == 128


def test_landscape_content_renders_through_viewport():
    """In landscape mode, content screen draws are offset by the status strip width."""
    d = make_display(landscape=True)
    tft = d.tft

    class OffsetChecker(Screen):
        def __init__(self):
            self._dirty = True
            self.fill_call = None

        def enter(self, display):
            pass

        def needs_redraw(self):
            return self._dirty

        def render(self, vp, theme, frame):
            self._dirty = False
            vp.fill_rect(0, 0, 128, 128, 0x1234)

    checker = OffsetChecker()
    d.set_content(checker)
    d.tft.calls.clear()
    d.tick()

    # The fill_rect(0, 0, ...) from the screen should land at (32, 0, ...) on the tft
    fill_rects = [c for c in tft.calls if c[0] == "fill_rect"]
    # Two fill_rects: zone clear + screen's own fill
    screen_fills = [c for c in fill_rects if c[5] == 0x1234]
    assert len(screen_fills) == 1
    assert screen_fills[0] == ("fill_rect", 32, 0, 128, 128, 0x1234)
