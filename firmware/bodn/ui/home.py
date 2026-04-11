# bodn/ui/home.py — home screen with mode selection

import time

from micropython import const
from bodn.ui.screen import Screen
from bodn.ui.icons import MODE_ICONS
from bodn.ui.widgets import (
    draw_centered,
    make_icon_sprite,
    make_label_sprite,
    blit_sprite,
    make_emoji_sprite,
)
from bodn.chord import ChordDetector
from bodn.i18n import t

NAV = const(0)  # config.ENC_NAV

# Animation: ease-out x-offsets as fraction of screen width (numerator / 16)
# 16 steps for smooth sliding with larger emoji icons (~800ms at 20 Hz)
_ANIM_STEPS = const(16)
_ANIM_FRAC = (16, 15, 14, 13, 12, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0)

# Loading bar: lives in the free zone between the carousel dots (y≈147) and
# the "plays left" footer (y≈220).  Values tuned for 320×240 landscape.
_LOAD_Y = const(154)  # top of loading zone
_LOAD_H = const(34)  # height of loading zone
_LOAD_BAR_Y = const(172)  # top of the progress bar inside the zone
_LOAD_BAR_H = const(8)  # bar height
_LOAD_BAR_MX = const(40)  # horizontal margin on each side

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

    def __init__(
        self, mode_screens, session_mgr, order=None, settings=None, audio=None
    ):
        self._mode_screens = mode_screens
        self._session_mgr = session_mgr
        self._all_names = order if order else list(mode_screens.keys())
        self._settings = settings or {}
        self._audio = audio
        self._names = []  # rebuilt on enter()
        self._index = 0
        self._manager = None
        self._error = None
        self._error_mode = None
        self._dirty = True
        self._full_clear = True
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
        hidden = self._settings.get("hidden_modes", [])
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
        from bodn.config import encoder_dpu

        self._dpu = encoder_dpu(self._settings)
        self._anim_step = _ANIM_STEPS
        self._dirty = True
        self._full_clear = True
        # Pre-render scaled icon/label sprites — one blit per frame
        # instead of hundreds of fill_rect calls.
        self._icon_sprites = {}
        self._label_sprites = {}
        self._icon_display_size = 64  # default, updated in _build_sprites
        self._sprite_color = None  # rebuilt on first render when theme available

    def _build_sprites(self, theme):
        """Pre-render icon and label sprites for all carousel modes."""
        color = theme.CYAN
        icon_scale = 4 if theme.width > theme.height else 3
        label_scale = 2
        self._icon_scale = icon_scale
        # Emoji: 96px on landscape primary, 48px on smaller/portrait displays
        emoji_size = 96 if theme.width > theme.height else 48
        has_emoji = False
        for name in self._names:
            # Try pre-rendered emoji sprite (with background pad)
            if name not in self._icon_sprites:
                spr = make_emoji_sprite(name, emoji_size)
                if spr is None and emoji_size != 48:
                    spr = make_emoji_sprite(name, 48)
                if spr is not None:
                    self._icon_sprites[name] = spr
                    has_emoji = True
                else:
                    # Fall back to 1-bit icon sprite
                    icon_data = MODE_ICONS.get(name)
                    if icon_data:
                        self._icon_sprites[name] = make_icon_sprite(
                            icon_data, 16, 16, color, scale=icon_scale
                        )
            elif self._icon_sprites.get(name) is not None:
                # Already cached — check if it's emoji-sized
                _, pw, _ = self._icon_sprites[name]
                if pw > 16 * icon_scale:
                    has_emoji = True
            label_text = t("mode_" + name).upper()
            if name not in self._label_sprites:
                self._label_sprites[name] = make_label_sprite(
                    label_text, color, scale=label_scale
                )
        # Compute icon_size once — used for layout in render
        if has_emoji:
            self._icon_display_size = emoji_size + 8  # include pad
        else:
            self._icon_display_size = 16 * icon_scale
        self._sprite_color = color

    def _blit_mode_icon(self, tft, name, screen_w, icon_size, ox, y):
        """Render a mode icon (pre-rendered sprite — emoji or 1-bit)."""
        spr = self._icon_sprites.get(name)
        if spr:
            _, pw, ph = spr
            blit_sprite(tft, spr, (screen_w - pw) // 2 + ox, y + (icon_size - ph) // 2)

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
        dpu = self._dpu
        if a >= dpu:
            units = a // dpu
            self._accum = a - units * dpu
            return units
        if a <= -dpu:
            units = -((-a) // dpu)
            self._accum = a - units * dpu
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
                # Show loading indicator immediately so the child sees feedback.
                # Draw into the free zone and push it to the display before the
                # (potentially slow) factory call begins.
                self._draw_loading_bar(0, 1)
                try:
                    screen = factory(on_progress=self._draw_loading_bar)
                except TypeError:
                    screen = factory()
                if name != "settings":
                    self._session_mgr.try_wake(name)
                if self._audio:
                    self._audio.play_sound("select")
                self._manager.push(screen)
            except Exception as e:
                self._error = str(e)
                self._error_mode = name
                self._dirty = True
            return

        # Advance animation if active — only the content band is cleared
        if self._anim_step < _ANIM_STEPS:
            self._anim_step += 1
            self._dirty = True

        # Nav encoder rotation cycles modes via accumulator
        delta = inp.enc_delta[NAV]
        velocity = inp.enc_velocity[NAV]
        units = self._accumulate(delta, velocity)
        if units != 0:
            # Clamp to ±1 so each frame steps once with its own animation + click.
            # Put excess back into the accumulator for subsequent frames.
            sign = 1 if units > 0 else -1
            excess = (abs(units) - 1) * self._dpu
            self._accum += excess * sign
            units = sign
            self._prev_name = self._names[self._index]
            self._index = (self._index + units) % len(self._names)
            # Start slide animation: incoming from direction of turn
            self._anim_step = 0
            self._anim_dir = 1 if units > 0 else -1
            self._dirty = True
            if self._audio:
                self._audio.play_sound("nav_click")

    def _draw_loading_bar(self, loaded, total):
        """Draw a progress bar in the free zone below the carousel dots.

        Called once before the factory (loaded=0, total=1) to show "Loading..."
        immediately, then called again by the factory's on_progress callback
        after each asset is preloaded.  Pushes only the loading zone to the
        display via show_rect so the surrounding home screen content stays intact.
        """
        tft = self._manager.tft
        theme = self._manager.theme
        w = theme.width

        bar_x = _LOAD_BAR_MX
        bar_w = w - _LOAD_BAR_MX * 2

        # Clear the loading zone
        tft.fill_rect(0, _LOAD_Y, w, _LOAD_H, theme.BLACK)

        # "Loading..." label (centred)
        label = t("home_loading")
        lx = (w - len(label) * 8) // 2
        tft.text(label, lx, _LOAD_Y + 4, theme.MUTED)

        # Bar outline
        tft.rect(bar_x, _LOAD_BAR_Y, bar_w, _LOAD_BAR_H, theme.DIM)

        # Bar fill — avoid division by zero; show a minimal sliver at 0
        if total > 0:
            fill_w = bar_w * loaded // total
            if fill_w > 0:
                tft.fill_rect(bar_x, _LOAD_BAR_Y, fill_w, _LOAD_BAR_H, theme.CYAN)

        # Push just this zone immediately (no full-screen redraw needed)
        tft.show_rect(0, _LOAD_Y, w, _LOAD_H)

    def _anim_x(self, width):
        """Return the current x-offset for the slide animation."""
        if self._anim_step >= _ANIM_STEPS:
            return 0
        frac = _ANIM_FRAC[self._anim_step]
        return self._anim_dir * (frac * width // 16)

    def render(self, tft, theme, frame):
        self._dirty = False
        full_clear = self._full_clear
        self._full_clear = False

        if full_clear:
            tft.fill(theme.BLACK)

        # Show error on screen if a mode failed to load
        if self._error:
            if not full_clear:
                tft.fill(theme.BLACK)
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
            self._render_landscape(tft, theme, frame, name, full_clear)
        else:
            self._render_portrait(tft, theme, frame, name, full_clear)

    def _draw_dots(self, tft, theme, y, w):
        """Draw carousel dot indicators centered at y."""
        n = len(self._names)
        if n <= 1:
            return
        dot_r = 3
        gap = 12
        total_w = n * gap - (gap - dot_r * 2)
        x0 = (w - total_w) // 2
        # Clear the dots row to avoid stale dot remnants
        tft.fill_rect(x0 - 1, y - dot_r - 1, total_w + 2, dot_r * 2 + 2, theme.BLACK)
        for i in range(n):
            cx = x0 + i * gap + dot_r
            if i == self._index:
                tft.fill_rect(cx - dot_r, y - dot_r, dot_r * 2, dot_r * 2, theme.CYAN)
            else:
                tft.rect(cx - dot_r, y - dot_r, dot_r * 2, dot_r * 2, theme.DIM)

    def _render_landscape(self, tft, theme, frame, name, full_clear):
        """Landscape layout: centered, icon above mode name."""
        # Lazy-build sprites on first render (need theme for colour)
        if self._sprite_color != theme.CYAN:
            self._build_sprites(theme)

        w = theme.width
        h = theme.height
        ox = self._anim_x(w)

        # Debug timing during animation (remove once tuned)
        _t0 = time.ticks_ms() if ox != 0 else 0

        icon_size = self._icon_display_size
        name_y = 40 + icon_size + 12
        dots_y = name_y + 28

        # Content band: icon + label rows (dots sit below)
        band_top = 40
        band_bot = name_y + 20

        if full_clear:
            draw_centered(tft, t("home_title"), 8, theme.WHITE, w, scale=2)
            remaining = self._session_mgr.sessions_remaining
            color = theme.GREEN if remaining > 0 else theme.RED
            draw_centered(tft, t("home_plays_left", remaining), h - 20, color, w)

        # Reset dirty tracking so show_dirty() only pushes what we draw,
        # not the entire screen from the full_clear fill.
        tft.reset_dirty()

        # Clear the content band
        tft.fill_rect(0, band_top, w, band_bot - band_top, theme.BLACK)

        # Draw only the incoming item (no outgoing slide — it was already
        # cleared by the fill_rect above). This keeps the dirty rect to
        # ~one sprite width instead of spanning both sprite positions.
        self._blit_mode_icon(tft, name, w, icon_size, ox, 40)

        label_spr = self._label_sprites.get(name)
        if label_spr:
            blit_sprite(tft, label_spr, (w - label_spr[1]) // 2 + ox, name_y)

        # Clear prev_name when animation completes
        if ox == 0:
            self._prev_name = None

        # Carousel dots
        self._draw_dots(tft, theme, dots_y, w)

        # Debug: print render time during animation
        if _t0:
            dr = tft.dirty_rect
            _ms = time.ticks_diff(time.ticks_ms(), _t0)
            print("ANIM f={} render={}ms ox={} dirty={}".format(frame, _ms, ox, dr))

    def _render_portrait(self, tft, theme, frame, name, full_clear):
        """Portrait layout: icon centered, stacked vertically."""
        w = theme.width
        ox = self._anim_x(w)

        icon_size = self._icon_display_size
        iy = theme.CENTER_Y - icon_size // 2 - 8
        dots_y = theme.CENTER_Y + 44

        # Content band: from icon top to below dots
        band_top = iy
        band_bot = dots_y + 8

        # Clear only the content band during animation, not the whole screen
        if not full_clear:
            tft.fill_rect(0, band_top, w, band_bot - band_top, theme.BLACK)

        # Static elements — only drawn on full clear
        if full_clear:
            draw_centered(tft, t("home_title"), theme.HEADER_Y, theme.WHITE, w)
            remaining = self._session_mgr.sessions_remaining
            color = theme.GREEN if remaining > 0 else theme.RED
            tft.text(t("home_plays_left", remaining), 16, theme.height - 16, color)

        # Outgoing item
        if self._prev_name and ox != 0:
            out_ox = ox - self._anim_dir * w
            self._blit_mode_icon(tft, self._prev_name, w, icon_size, out_ox, iy)
            prev_text = t("mode_" + self._prev_name).upper()
            ptx = (w - len(prev_text) * 8) // 2 + out_ox
            tft.text(prev_text, ptx, theme.CENTER_Y + 24, theme.CYAN)

        # Incoming item
        self._blit_mode_icon(tft, name, w, icon_size, ox, iy)

        mode_text = t("mode_" + name).upper()
        mtx = (w - len(mode_text) * 8) // 2 + ox
        tft.text(mode_text, mtx, theme.CENTER_Y + 24, theme.WHITE)

        if ox == 0:
            self._prev_name = None

        # Carousel dots
        self._draw_dots(tft, theme, dots_y, w)
