# bodn/ui/demo.py — LED playground + hardware test (Demo mode screen)
#
# Every physical input is visible on-screen with its real color, making
# this both the original "leklåda" experience and a quick hardware check.

from micropython import const

from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.input import BrightnessControl
from bodn.ui.widgets import draw_progress_bar
from bodn.ui.pause import PauseMenu
from bodn.patterns import PATTERNS, PATTERN_NAMES
from bodn.i18n import t
from bodn.neo import neo

NAV = config.ENC_NAV
ENC_A = config.ENC_A
ENC_B = config.ENC_B

# Map Python PATTERNS index → C _neopixel pattern ID
_PAT_MAP = [
    neo.PAT_RAINBOW,  # 0: Rainbow
    neo.PAT_PULSE,  # 1: Pulse
    neo.PAT_CHASE,  # 2: Chase
    neo.PAT_SPARKLE,  # 3: Sparkle
    neo.PAT_BOUNCE,  # 4: Bounce
    neo.PAT_WAVE,  # 5: Wave
    neo.PAT_SPLIT,  # 6: Split
    neo.PAT_FILL,  # 7: Fill
]

# Dirty section flags (bitmask)
_D_HEADER = const(1)
_D_ENCODERS = const(2)
_D_TOGGLES = const(4)
_D_BUTTONS = const(8)
_D_ARCADE = const(16)
_D_ALL = const(31)  # 1|2|4|8|16

# Colour palette per pattern index — module-level to avoid per-frame allocation
_COLOUR_RGB = [
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 255, 0),
    (0, 255, 255),
    (255, 0, 255),
    (255, 128, 0),
    (128, 0, 255),
]

# Physical mini-button colors → RGB tuples (matches config.BUTTON_COLORS order)
_BTN_RGB = [
    (0, 200, 0),  # green
    (0, 100, 255),  # blue
    (255, 255, 255),  # white
    (255, 220, 0),  # yellow
    (255, 0, 0),  # red
    (80, 80, 80),  # black (shown as dark grey)
    (0, 200, 0),  # green
    (0, 100, 255),  # blue
]

# Physical arcade-button colors → RGB tuples (matches config.ARCADE_COLORS order)
_ARC_RGB = [
    (60, 220, 60),  # green (far left)
    (60, 100, 255),  # blue
    (255, 255, 255),  # white (centre)
    (255, 220, 60),  # yellow
    (255, 60, 60),  # red (far right)
]

# 565 versions are lazily initialised on first render (needs theme.rgb)
_btn_565 = None
_arc_565 = None


def _init_565(rgb_fn):
    global _btn_565, _arc_565
    if _btn_565 is None:
        _btn_565 = [rgb_fn(r, g, b) for r, g, b in _BTN_RGB]
        _arc_565 = [rgb_fn(r, g, b) for r, g, b in _ARC_RGB]


class DemoScreen(Screen):
    """Interactive LED playground — the original Bodn experience.

    All physical inputs are shown on-screen:
    - 8 mini buttons with their physical colors
    - 5 arcade buttons with their physical colors
    - 4 toggle switches (SW_L, SW0/reverse, SW1/mirror, SW_R)
    - 2 encoders (position bars + button indicators)

    Button tap → select LED pattern.  Arcade tap → color flash on LEDs.
    Encoder A = brightness, NAV/Encoder B = speed.
    Toggle modifiers: SW0=reverse, SW1=mirror, SW_L=color shift, SW_R=strobe.
    """

    def __init__(self, overlay, arcade=None, settings=None):
        self._overlay = overlay
        self._arcade = arcade
        self._brightness = BrightnessControl(settings=settings)
        self._active_pattern = 0
        self._speed = 3  # 1-10, controlled by NAV/ENC_B rotation
        self._manager = None
        self._pause = PauseMenu(settings=settings)
        self._dirty_sections = _D_ALL  # bitmask of sections needing redraw
        self._full_clear = True
        # Arcade flash: when an arcade button is tapped, flash its color
        self._arc_flash = -1  # arcade index, or -1
        self._arc_flash_ttl = 0  # frames remaining
        # Snapshot of input state for dirty detection
        self._prev_enc = [0, 0]
        self._prev_btn = []
        self._prev_arc = []
        self._prev_sw = []
        self._prev_enc_btn = [False, False, False]
        self._neo_dirty = True  # push pattern to C engine on enter

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._brightness.reset()
        self._dirty_sections = _D_ALL
        self._full_clear = True
        self._neo_dirty = True
        neo.clear_all_overrides()
        self._apply_neo_pattern()

    def on_reveal(self):
        self._dirty_sections = _D_ALL
        self._full_clear = True
        self._neo_dirty = True
        self._apply_neo_pattern()

    def exit(self):
        neo.all_off()
        if self._arcade:
            self._arcade.all_off()
            self._arcade.flush()

    def needs_redraw(self):
        return self._dirty_sections != 0 or self._pause.needs_render

    def update(self, inp, frame):
        # Pause menu handles hold-to-open and menu navigation
        result = self._pause.update(inp, frame)
        if result == "quit" and self._manager:
            self._manager.pop()
            return
        elif result == "resume":
            self._dirty_sections = _D_ALL
            self._full_clear = True
        if self._pause.is_open or self._pause.is_holding:
            return

        ds = self._dirty_sections

        # Button tap → select pattern (uses gesture layer)
        g = inp.gestures
        n_btn = len(inp.btn_held)
        for i in range(n_btn):
            if g.tap[i]:
                self._active_pattern = i % len(PATTERNS)
                ds |= _D_HEADER
                self._neo_dirty = True
                break

        # Arcade button tap → flash that button's color on all LEDs
        n_arc = len(inp.arc_held)
        for i in range(n_arc):
            if inp.arc_just_pressed[i]:
                self._arc_flash = i
                self._arc_flash_ttl = 9  # ~300 ms at 30 fps
                break

        # Decay arcade flash (LED-only, no screen section)
        if self._arc_flash_ttl > 0:
            self._arc_flash_ttl -= 1
            if self._arc_flash_ttl == 0:
                self._arc_flash = -1

        # Encoder A button → cycle pattern
        if inp.enc_btn_pressed[ENC_A]:
            self._active_pattern = (self._active_pattern + 1) % len(PATTERNS)
            ds |= _D_HEADER
            self._neo_dirty = True

        # Update brightness from encoder A (velocity-aware)
        prev_bri = self._brightness.value
        self._brightness.update(inp.enc_delta[ENC_A], inp.enc_velocity[ENC_A])
        if self._brightness.value != prev_bri:
            ds |= _D_HEADER | _D_ENCODERS
            self._neo_dirty = True

        # NAV/ENC_B rotation adjusts speed
        delta_b = inp.enc_delta[ENC_B]
        if delta_b != 0:
            self._speed = max(1, min(10, self._speed + delta_b))
            ds |= _D_HEADER | _D_ENCODERS
            self._neo_dirty = True

        # Dirty detection for display: encoders
        if inp.enc_pos[ENC_A] != self._prev_enc[ENC_A]:
            self._prev_enc[ENC_A] = inp.enc_pos[ENC_A]
            ds |= _D_ENCODERS
        if inp.enc_pos[ENC_B] != self._prev_enc[ENC_B]:
            self._prev_enc[ENC_B] = inp.enc_pos[ENC_B]
            ds |= _D_ENCODERS

        # Dirty detection: mini buttons
        if not self._prev_btn:
            self._prev_btn = [False] * n_btn
        for i in range(n_btn):
            if inp.btn_held[i] != self._prev_btn[i]:
                self._prev_btn[i] = inp.btn_held[i]
                ds |= _D_BUTTONS

        # Dirty detection: arcade buttons
        if not self._prev_arc:
            self._prev_arc = [False] * n_arc
        for i in range(n_arc):
            if inp.arc_held[i] != self._prev_arc[i]:
                self._prev_arc[i] = inp.arc_held[i]
                ds |= _D_ARCADE

        # Dirty detection: toggle switches (all 4)
        n_sw = len(inp.sw)
        if not self._prev_sw and n_sw:
            self._prev_sw = [False] * n_sw
        for i in range(min(n_sw, len(self._prev_sw))):
            if inp.sw[i] != self._prev_sw[i]:
                self._prev_sw[i] = inp.sw[i]
                ds |= _D_TOGGLES
        # Handle switch list growing (MCP2 came online)
        if n_sw > len(self._prev_sw):
            self._prev_sw = list(inp.sw)
            ds |= _D_TOGGLES

        # Dirty detection: encoder buttons
        for i in range(min(len(inp.enc_btn_held), len(self._prev_enc_btn))):
            if inp.enc_btn_held[i] != self._prev_enc_btn[i]:
                self._prev_enc_btn[i] = inp.enc_btn_held[i]
                ds |= _D_ENCODERS

        self._dirty_sections = ds

        # Arcade button LEDs update every frame (cheap I2C)
        self._update_arcade_leds(inp, frame)

        # NeoPixel strip: C engine handles rendering, only push on change
        if self._neo_dirty:
            self._neo_dirty = False
            self._apply_neo_pattern()
        # Arcade flash override via C engine
        if self._arc_flash >= 0 and self._arc_flash < len(_ARC_RGB):
            cr, cg, cb = _ARC_RGB[self._arc_flash]
            fade = self._arc_flash_ttl * self._brightness.value // 9
            neo.set_override(
                neo.OVERRIDE_SOLID,
                (cr * fade) >> 8,
                (cg * fade) >> 8,
                (cb * fade) >> 8,
            )

    def _apply_neo_pattern(self):
        """Push current pattern/speed/brightness to C engine (no per-frame cost)."""
        pat_idx = self._active_pattern
        pat_id = _PAT_MAP[pat_idx]
        speed = self._speed
        brightness = self._brightness.value
        colour = _COLOUR_RGB[pat_idx] if pat_idx > 0 else (255, 255, 255)
        neo.zone_pattern(
            neo.ZONE_STICK_A, pat_id, speed=speed, colour=colour, brightness=brightness
        )
        neo.zone_pattern(
            neo.ZONE_STICK_B, pat_id, speed=speed, colour=colour, brightness=brightness
        )
        neo.zone_pattern(
            neo.ZONE_LID_RING,
            pat_id,
            speed=speed,
            colour=colour,
            brightness=config.NEOPIXEL_LID_BRIGHTNESS,
        )

    def _update_arcade_leds(self, inp, frame):
        """Update arcade button LEDs every frame (cheap I2C, not gated by NeoPixel throttle)."""
        arc = self._arcade
        if not arc:
            return
        sw = inp.sw
        use_wave = len(sw) > 3 and sw[3]  # SW_R: wave mode
        if use_wave:
            arc.wave(frame, speed=self._speed)
        n_arc = len(inp.arc_held)
        for i in range(min(n_arc, arc.count)):
            if inp.arc_held[i]:
                arc.on(i)
            elif not use_wave:
                arc.glow(i)
        arc.flush()

    def render(self, tft, theme, frame):
        _init_565(theme.rgb)
        ds = self._dirty_sections

        if self._pause.is_open:
            if ds:
                self._dirty_sections = 0
                tft.fill(theme.BLACK)
                self._full_clear = False
                self._render_sections(tft, theme, _D_ALL)
            self._pause.render(tft, theme, frame)
            return

        if not ds:
            self._pause.render(tft, theme, frame)
            return
        self._dirty_sections = 0
        if self._full_clear:
            self._full_clear = False
            tft.fill(theme.BLACK)
            ds = _D_ALL  # full clear → redraw everything
        self._render_sections(tft, theme, ds)
        self._pause.render(tft, theme, frame)

    def _render_sections(self, tft, theme, ds):
        """Redraw only the dirty sections of the display."""
        sw = []
        held = [False] * 8
        arc_held = [False] * 5
        enc_pos = [0, 0, 0]
        enc_btn = [False, False, False]
        if self._manager:
            inp = self._manager.inp
            sw = inp.sw
            held = inp.btn_held
            arc_held = inp.arc_held
            enc_pos = inp.enc_pos
            enc_btn = inp.enc_btn_held

        w = theme.width  # 320
        h = theme.height  # 240

        # --- Row 1: Pattern name banner (y 0–16) ---
        if ds & _D_HEADER:
            pat_idx = self._active_pattern
            pat_c = _btn_565[pat_idx % len(_btn_565)]
            tft.fill_rect(0, 0, w, 16, pat_c)
            tft.text(PATTERN_NAMES[pat_idx], 4, 4, theme.BLACK)
            bri_txt = "{}:{}".format(t("demo_bri"), self._brightness.value)
            spd_txt = "{}:{}".format(t("demo_spd"), self._speed)
            tft.text(bri_txt, w - len(bri_txt) * 8 - 4, 4, theme.BLACK)
            tft.text(
                spd_txt, w - len(spd_txt) * 8 - len(bri_txt) * 8 - 12, 4, theme.BLACK
            )

        # --- Row 2: Encoders + brightness/speed bars (y 20–70) ---
        if ds & _D_ENCODERS:
            tft.text(t("demo_encoders"), 0, 20, theme.MUTED)
            _draw_encoder(tft, theme, 0, 32, "NAV", enc_pos[ENC_B], enc_btn[ENC_B])
            _draw_encoder(tft, theme, 100, 32, "ENC", enc_pos[ENC_A], enc_btn[ENC_A])
            bar_x = 200
            bar_w = w - bar_x - 4
            tft.text(t("demo_bri"), bar_x, 32, theme.CYAN)
            draw_progress_bar(
                tft,
                bar_x,
                42,
                bar_w,
                8,
                self._brightness.value,
                255,
                theme.CYAN,
                theme.BLACK,
            )
            tft.text(t("demo_spd"), bar_x, 52, theme.ORANGE)
            draw_progress_bar(
                tft,
                bar_x,
                62,
                bar_w,
                8,
                self._speed,
                10,
                theme.ORANGE,
                theme.BLACK,
            )

        # --- Row 3: Toggle switches (y 74–100) ---
        if ds & _D_TOGGLES:
            tft.text(t("demo_toggles"), 0, 74, theme.MUTED)
            toggle_info = [
                (t("tog_left"), 2),
                (t("tog_reverse"), 0),
                (t("tog_mirror"), 1),
                (t("tog_right"), 3),
            ]
            for ti, (label, sw_idx) in enumerate(toggle_info):
                x = ti * 40
                y = 86
                on = sw_idx < len(sw) and sw[sw_idx]
                tft.fill_rect(x, y, 36, 14, theme.GREEN if on else theme.BLACK)
                if not on:
                    tft.rect(x, y, 36, 14, theme.DIM)
                tft.text(label, x + 2, y + 3, theme.BLACK if on else theme.WHITE)

        # --- Row 4: Mini buttons (y 104–134) ---
        if ds & _D_BUTTONS:
            tft.text(t("demo_buttons"), 0, 104, theme.MUTED)
            _draw_btn_row(tft, theme, held, 0, 118, w)

        # --- Row 5: Arcade buttons (y 136–176) ---
        if ds & _D_ARCADE:
            tft.text(t("demo_arcade"), 0, 136, theme.MUTED)
            _draw_arc_row(tft, theme, arc_held, 0, 150, w)

        # --- Bottom: back hint (only on full redraw) ---
        if ds == _D_ALL:
            tft.text(t("demo_back"), 4, h - 12, theme.MUTED)


def _draw_encoder(tft, theme, x, y, label, pos, btn_held):
    """Draw a compact encoder indicator: label, position value, button dot."""
    tft.fill_rect(x, y, 96, 20, theme.BLACK)
    tft.text(label, x, y, theme.WHITE)
    # Position value
    pos_txt = str(pos)
    tft.text(pos_txt, x + 32, y, theme.CYAN)
    # Button indicator (filled circle approximation)
    bx = x + 76
    by = y + 2
    if btn_held:
        tft.fill_rect(bx, by, 10, 10, theme.YELLOW)
    else:
        tft.rect(bx, by, 10, 10, theme.DIM)
    tft.text("SW", x, y + 12, theme.DIM)
    tft.text(
        "ON" if btn_held else "--",
        x + 20,
        y + 12,
        theme.YELLOW if btn_held else theme.DIM,
    )


def _draw_btn_row(tft, theme, held, x0, y0, screen_w):
    """Draw 8 mini buttons in a single row with physical colors."""
    n = min(8, len(held))
    cell_w = screen_w // 8
    for i in range(n):
        x = x0 + i * cell_w
        bw = cell_w - 4
        bh = 16
        c = _btn_565[i]
        if held[i]:
            tft.fill_rect(x, y0, bw, bh, c)
            tft.text(str(i), x + bw // 2 - 4, y0 + 4, theme.BLACK)
        else:
            tft.fill_rect(x, y0, bw, bh, theme.BLACK)
            tft.rect(x, y0, bw, bh, c)
            tft.text(str(i), x + bw // 2 - 4, y0 + 4, c)


def _draw_arc_row(tft, theme, held, x0, y0, screen_w):
    """Draw 5 arcade buttons with physical colors."""
    n = min(5, len(held))
    cell_w = screen_w // 5
    bh = 24
    for i in range(n):
        x = x0 + i * cell_w
        bw = cell_w - 6
        c = _arc_565[i]
        label = config.ARCADE_COLORS[i][:3].upper()  # YEL, RED, BLU, GRE, WHI
        if held[i]:
            tft.fill_rect(x, y0, bw, bh, c)
            tft.text(label, x + 4, y0 + 8, theme.BLACK)
        else:
            tft.fill_rect(x, y0, bw, bh, theme.BLACK)
            tft.rect(x, y0, bw, bh, c)
            tft.text(label, x + 4, y0 + 8, c)
