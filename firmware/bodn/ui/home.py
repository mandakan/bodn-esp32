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
_DPU = const(2)  # raw detents per unit (KY-040 dual-edge ≈ 2 per click)
_FAST_THRESH = const(400)  # velocity threshold for fast multiplier
_FAST_MULT = const(2)  # multiplier at high velocity


class HomeScreen(Screen):
    """Displays available modes and lets the user select one.

    Nav encoder (index 0) rotation cycles through modes with velocity scaling.
    Nav encoder button or any play button enters the selected mode.

    Mode changes play a short slide animation (~150ms at 20Hz).
    Only redraws on input events or during active animation.
    """

    def __init__(self, mode_screens, session_mgr, order=None):
        self._mode_screens = mode_screens
        self._session_mgr = session_mgr
        self._names = order if order else list(mode_screens.keys())
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
        # Chord: hold btn 0 + press btn 7 → jump to settings
        self._chords = (
            ChordDetector({(0, 7): "settings"})
            if "settings" in self._mode_screens
            else None
        )

    def enter(self, manager):
        self._manager = manager
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
        if delta != 0:
            # Re-center encoder on every raw delta to prevent hitting clamp limits
            mid = self._manager.inp._encoders[NAV]._max // 2
            self._manager.inp._encoders[NAV].value = mid
            self._manager.inp._prev_enc_pos[NAV] = mid

        velocity = inp.enc_velocity[NAV]
        units = self._accumulate(delta, velocity)
        if units != 0:
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

    def _render_landscape(self, tft, theme, frame, name):
        """Landscape layout: centered, icon above mode name."""
        w = theme.width
        h = theme.height
        ox = self._anim_x(w)

        # Title — centered at top (static, no slide)
        draw_centered(tft, t("home_title"), 8, theme.WHITE, w, scale=2)

        # Icon — centered, offset by animation
        icon_data = MODE_ICONS.get(name)
        icon_scale = 4
        icon_size = 16 * icon_scale
        if icon_data:
            ix = (w - icon_size) // 2 + ox
            iy = 40
            draw_icon(tft, icon_data, ix, iy, 16, 16, theme.CYAN, scale=icon_scale)

        # Mode name — centered below icon, offset by animation
        name_y = 40 + icon_size + 12
        draw_centered(
            tft, t("mode_" + name).upper(), name_y, theme.CYAN, w + ox * 2, scale=2
        )

        # Arrow hints
        n = len(self._names)
        if n > 1:
            draw_centered(tft, t("home_browse"), name_y + 24, theme.MUTED, w)

        # Sessions remaining — bottom center (static)
        remaining = self._session_mgr.sessions_remaining
        color = theme.GREEN if remaining > 0 else theme.RED
        draw_centered(tft, t("home_plays_left", remaining), h - 20, color, w)

    def _render_portrait(self, tft, theme, frame, name):
        """Portrait layout: icon centered, stacked vertically."""
        w = theme.width
        ox = self._anim_x(w)

        draw_centered(tft, t("home_title"), theme.HEADER_Y, theme.WHITE, w)

        icon_data = MODE_ICONS.get(name)
        if icon_data:
            icon_scale = 3
            icon_size = 16 * icon_scale
            ix = (w - icon_size) // 2 + ox
            iy = theme.CENTER_Y - icon_size // 2 - 8
            draw_icon(tft, icon_data, ix, iy, 16, 16, theme.CYAN, scale=icon_scale)

        draw_centered(
            tft,
            t("mode_" + name).upper(),
            theme.CENTER_Y + 24,
            theme.WHITE,
            w + ox * 2,
        )

        n = len(self._names)
        if n > 1:
            tft.text("<", 2, theme.CENTER_Y - 4, theme.MUTED)
            tft.text(">", w - 10, theme.CENTER_Y - 4, theme.MUTED)

        remaining = self._session_mgr.sessions_remaining
        color = theme.GREEN if remaining > 0 else theme.RED
        tft.text(t("home_plays_left", remaining), 16, theme.height - 16, color)
