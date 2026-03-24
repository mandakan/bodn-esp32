# bodn/ui/home.py — home screen with mode selection

from micropython import const
from bodn.ui.screen import Screen
from bodn.ui.icons import MODE_ICONS
from bodn.ui.widgets import draw_icon, draw_centered
from bodn.chord import ChordDetector
from bodn.i18n import t

NAV = const(0)  # config.ENC_NAV

# Animation: ease-out x-offsets as fraction of screen width (numerator / 4)
# Positions: [full off-screen, 2/3 off, 1/4 off, settled]
_ANIM_STEPS = const(4)
_ANIM_FRAC = (4, 3, 1, 0)  # multiplied by width//4

# Accumulator settings
_DPU = const(1)  # raw detents per unit (1 per physical click)
_FAST_THRESH = const(400)  # velocity threshold for fast multiplier
_FAST_MULT = const(2)  # multiplier at high velocity


class HomeScreen(Screen):
    """Displays available modes and lets the user select one.

    Nav encoder (index 0) rotation cycles through modes with velocity scaling.
    Nav encoder button or any play button enters the selected mode.

    Mode changes play a short slide animation (~150ms at 20Hz).
    Only redraws on input events or during active animation.
    """

    def __init__(self, mode_screens, session_mgr, order=None, settings=None):
        self._mode_screens = mode_screens
        self._session_mgr = session_mgr
        self._all_names = order if order else list(mode_screens.keys())
        self._settings = settings or {}
        self._names = []  # rebuilt on enter()
        self._index = 0
        self._manager = None
        self._error = None
        self._error_mode = None
        self._dirty = True
        # Inline accumulator state
        self._accum = 0
        # Animation state
        self._anim_step = _ANIM_STEPS  # >= _ANIM_STEPS means idle
        self._anim_dir = 1  # +1 = incoming from right, -1 = from left
        self._prev_name = None  # previous item for slide-out animation
        # Chord: hold btn 0 + press btn 7 → jump to settings
        self._chords = (
            ChordDetector({(0, 7): "settings"})
            if "settings" in self._mode_screens
            else None
        )

    def _rebuild_names(self):
        """Rebuild visible mode list from settings.

        hidden_modes: list of mode names to hide from the carousel.
        Modes hidden here are still accessible via chord combos (e.g. settings).
        """
        hidden = self._settings.get("hidden_modes", ["settings"])
        self._names = [n for n in self._all_names if n not in hidden]
        # Clamp index
        if self._names:
            self._index = self._index % len(self._names)
        else:
            self._index = 0

    def enter(self, manager):
        self._manager = manager
        self._rebuild_names()
        self._accum = 0
        self._anim_step = _ANIM_STEPS
        self._dirty = True

    def needs_redraw(self):
        return self._dirty

    def _accumulate(self, delta, velocity):
        """Accumulate raw detents into logical units with velocity scaling."""
        if delta == 0:
            return 0
        if velocity >= _FAST_THRESH:
            self._accum += delta * _FAST_MULT
        else:
            self._accum += delta
        a = self._accum
        if a >= _DPU:
            units = a // _DPU
            self._accum = a - units * _DPU
            return units
        if a <= -_DPU:
            units = -((-a) // _DPU)
            self._accum = a - units * _DPU
            return units
        return 0

    def update(self, inp, frame):
        if not self._names:
            return

        # Chord shortcut: hold btn 0 + press btn 7 → settings
        if self._chords:
            chord = self._chords.update(inp.btn_held, inp.btn_just_pressed)
            if chord:
                for idx in self._chords.suppressed:
                    inp.gestures.tap[idx] = False
                if chord in self._mode_screens:
                    try:
                        self._manager.push(self._mode_screens[chord]())
                    except Exception as e:
                        self._error = str(e)
                        self._error_mode = chord
                        self._dirty = True
                    return

        # Nav encoder button or any play button → enter mode
        if inp.any_btn_pressed() or inp.enc_btn_pressed[NAV]:
            name = self._names[self._index]
            factory = self._mode_screens[name]
            try:
                screen = factory()
                if name != "settings":
                    self._session_mgr.try_wake(name)
                self._manager.push(screen)
            except Exception as e:
                self._error = str(e)
                self._error_mode = name
                self._dirty = True
            return

        # Advance animation if active
        if self._anim_step < _ANIM_STEPS:
            self._anim_step += 1
            self._dirty = True

        # Nav encoder rotation cycles modes via accumulator
        delta = inp.enc_delta[NAV]
        velocity = inp.enc_velocity[NAV]
        units = self._accumulate(delta, velocity)
        if units != 0:
            self._prev_name = self._names[self._index]
            self._index = (self._index + units) % len(self._names)
            # Start slide animation: incoming from direction of turn
            self._anim_step = 0
            self._anim_dir = 1 if units > 0 else -1
            self._dirty = True

    def _anim_x(self, width):
        """Return the current x-offset for the slide animation."""
        if self._anim_step >= _ANIM_STEPS:
            return 0
        frac = _ANIM_FRAC[self._anim_step]
        return self._anim_dir * (frac * width // 4)

    def render(self, tft, theme, frame):
        self._dirty = False
        tft.fill(theme.BLACK)

        # Show error on screen if a mode failed to load
        if self._error:
            tft.text("ERR: " + str(self._error_mode), 4, 4, theme.RED)
            # Word-wrap error message
            msg = self._error
            y = 20
            while msg and y < theme.height - 16:
                tft.text(msg[: theme.width // 8], 4, y, theme.WHITE)
                msg = msg[theme.width // 8 :]
                y += 12
            tft.text(t("home_press_clear"), 4, theme.height - 12, theme.MUTED)
            if self._manager and self._manager.inp.any_btn_pressed():
                self._error = None
                self._dirty = True
            return

        if not self._names:
            draw_centered(
                tft, t("home_no_modes"), theme.CENTER_Y, theme.MUTED, theme.width
            )
            return

        name = self._names[self._index]
        landscape = theme.width > theme.height

        if landscape:
            self._render_landscape(tft, theme, frame, name)
        else:
            self._render_portrait(tft, theme, frame, name)

    def _draw_dots(self, tft, theme, y, w):
        """Draw carousel dot indicators centered at y."""
        n = len(self._names)
        if n <= 1:
            return
        dot_r = 3
        gap = 12
        total_w = n * gap - (gap - dot_r * 2)
        x0 = (w - total_w) // 2
        for i in range(n):
            cx = x0 + i * gap + dot_r
            if i == self._index:
                tft.fill_rect(cx - dot_r, y - dot_r, dot_r * 2, dot_r * 2, theme.CYAN)
            else:
                tft.rect(cx - dot_r, y - dot_r, dot_r * 2, dot_r * 2, theme.MUTED)

    def _render_landscape(self, tft, theme, frame, name):
        """Landscape layout: centered, icon above mode name."""
        w = theme.width
        h = theme.height
        ox = self._anim_x(w)

        # Title — centered at top (static, no slide)
        draw_centered(tft, t("home_title"), 8, theme.WHITE, w, scale=2)

        icon_scale = 4
        icon_size = 16 * icon_scale
        name_y = 40 + icon_size + 12

        # Outgoing item (slides out in opposite direction)
        if self._prev_name and ox != 0:
            # Outgoing offset: opposite side, moving away
            out_ox = ox - self._anim_dir * w
            prev_icon = MODE_ICONS.get(self._prev_name)
            if prev_icon:
                pix = (w - icon_size) // 2 + out_ox
                draw_icon(
                    tft, prev_icon, pix, 40, 16, 16, theme.MUTED, scale=icon_scale
                )
            draw_centered(
                tft,
                t("mode_" + self._prev_name).upper(),
                name_y,
                theme.MUTED,
                w + out_ox * 2,
                scale=2,
            )

        # Incoming item (slides in from the side)
        icon_data = MODE_ICONS.get(name)
        if icon_data:
            ix = (w - icon_size) // 2 + ox
            draw_icon(tft, icon_data, ix, 40, 16, 16, theme.CYAN, scale=icon_scale)

        draw_centered(
            tft, t("mode_" + name).upper(), name_y, theme.CYAN, w + ox * 2, scale=2
        )

        # Clear prev_name when animation completes
        if ox == 0:
            self._prev_name = None

        # Carousel dots
        self._draw_dots(tft, theme, name_y + 28, w)

        # Sessions remaining — bottom center (static)
        remaining = self._session_mgr.sessions_remaining
        color = theme.GREEN if remaining > 0 else theme.RED
        draw_centered(tft, t("home_plays_left", remaining), h - 20, color, w)

    def _render_portrait(self, tft, theme, frame, name):
        """Portrait layout: icon centered, stacked vertically."""
        w = theme.width
        ox = self._anim_x(w)

        draw_centered(tft, t("home_title"), theme.HEADER_Y, theme.WHITE, w)

        icon_scale = 3
        icon_size = 16 * icon_scale
        iy = theme.CENTER_Y - icon_size // 2 - 8

        # Outgoing item
        if self._prev_name and ox != 0:
            out_ox = ox - self._anim_dir * w
            prev_icon = MODE_ICONS.get(self._prev_name)
            if prev_icon:
                pix = (w - icon_size) // 2 + out_ox
                draw_icon(
                    tft, prev_icon, pix, iy, 16, 16, theme.MUTED, scale=icon_scale
                )
            draw_centered(
                tft,
                t("mode_" + self._prev_name).upper(),
                theme.CENTER_Y + 24,
                theme.MUTED,
                w + out_ox * 2,
            )

        # Incoming item
        icon_data = MODE_ICONS.get(name)
        if icon_data:
            ix = (w - icon_size) // 2 + ox
            draw_icon(tft, icon_data, ix, iy, 16, 16, theme.CYAN, scale=icon_scale)

        draw_centered(
            tft,
            t("mode_" + name).upper(),
            theme.CENTER_Y + 24,
            theme.WHITE,
            w + ox * 2,
        )

        if ox == 0:
            self._prev_name = None

        # Carousel dots
        self._draw_dots(tft, theme, theme.CENTER_Y + 44, w)

        remaining = self._session_mgr.sessions_remaining
        color = theme.GREEN if remaining > 0 else theme.RED
        tft.text(t("home_plays_left", remaining), 16, theme.height - 16, color)
