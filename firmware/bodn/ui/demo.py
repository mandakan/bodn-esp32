# bodn/ui/demo.py — LED playground (Demo mode screen)

from micropython import const
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.input import BrightnessControl
from bodn.ui.widgets import draw_progress_bar, draw_button_grid, draw_centered
from bodn.ui.pause import PauseMenu
from bodn.patterns import PATTERNS, PATTERN_NAMES, N_LEDS, ZONE_LID_RING, _BLACK
from bodn.i18n import t

NAV = const(0)  # config.ENC_NAV
ENC_A = const(1)  # config.ENC_A
ENC_B = const(2)  # config.ENC_B

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


class DemoScreen(Screen):
    """Interactive LED playground — the original Bodn experience.

    Buttons select patterns, nav encoder button goes back.
    Encoder A = brightness, Encoder B = speed.
    Toggles apply modifiers.

    Display redraws on any input change. LED computation only
    happens on NeoPixel-write frames (every 3rd frame).
    """

    def __init__(self, np, overlay, settings=None):
        self._np = np
        self._overlay = overlay
        self._brightness = BrightnessControl()
        self._active_pattern = 0
        self._manager = None
        self._pause = PauseMenu(settings=settings)
        self._dirty = True
        # Snapshot of input state for dirty detection
        self._prev_enc = [0, 0, 0]
        self._prev_btn = [False] * 8
        self._prev_sw = [False] * 4

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._brightness.reset()
        self._dirty = True

    def needs_redraw(self):
        return self._dirty or self._pause.needs_render

    def update(self, inp, frame):
        # Pause menu handles hold-to-open and menu navigation
        result = self._pause.update(inp, frame)
        if result == "quit" and self._manager:
            self._manager.pop()
            return
        elif result == "resume":
            self._dirty = True
        if self._pause.is_open or self._pause.is_holding:
            return

        # Button press → select pattern
        first = inp.first_btn_pressed()
        if first >= 0:
            self._active_pattern = first % len(PATTERNS)
            self._dirty = True

        # Encoder A or B button → cycle pattern
        if inp.enc_btn_pressed[ENC_A] or inp.enc_btn_pressed[ENC_B]:
            self._active_pattern = (self._active_pattern + 1) % len(PATTERNS)
            self._dirty = True

        # Update brightness from encoder A (velocity-aware)
        prev_bri = self._brightness.value
        self._brightness.update(inp.enc_delta[ENC_A], inp.enc_velocity[ENC_A])
        if self._brightness.value != prev_bri:
            self._dirty = True

        # Detect encoder changes for display redraw
        for i in (NAV, ENC_B):
            if inp.enc_pos[i] != self._prev_enc[i]:
                self._prev_enc[i] = inp.enc_pos[i]
                self._dirty = True
        for i in range(8):
            if inp.btn_held[i] != self._prev_btn[i]:
                self._prev_btn[i] = inp.btn_held[i]
                self._dirty = True
        for i in range(min(4, len(inp.sw))):
            if inp.sw[i] != self._prev_sw[i]:
                self._prev_sw[i] = inp.sw[i]
                self._dirty = True

        # Only compute and write LEDs on NeoPixel-write frames
        if frame % 3 == 0:
            brightness = self._brightness.value
            speed = max(1, inp.enc_pos[ENC_B])

            _name, pat_fn = PATTERNS[self._active_pattern]

            if self._active_pattern == 0:
                leds = pat_fn(frame, speed, 0, brightness)
            else:
                colour = _COLOUR_RGB[self._active_pattern]
                leds = pat_fn(frame, speed, colour, brightness)

            # Toggle switch modifiers (operate in-place on shared _led_buf)
            sw = inp.sw
            n = N_LEDS
            black = _BLACK
            if sw[0]:
                # Reverse: swap in-place
                half = n // 2
                for i in range(half):
                    j = n - 1 - i
                    leds[i], leds[j] = leds[j], leds[i]
            if sw[1]:
                half = n // 2
                for i in range(half):
                    leds[n - 1 - i] = leds[i]
            if sw[2] and (frame // 4) % 2 == 0:
                for i in range(n):
                    leds[i] = black
            if len(sw) > 3 and sw[3]:
                for i in range(n):
                    r, g, b = leds[i]
                    leds[i] = (255 - r, 255 - g, 255 - b)

            # Dim the lid ring relative to the sticks
            lid_ratio = config.NEOPIXEL_LID_BRIGHTNESS
            ring_start, ring_count = ZONE_LID_RING
            for i in range(ring_start, ring_start + ring_count):
                r, g, b = leds[i]
                leds[i] = (
                    (r * lid_ratio) >> 8,
                    (g * lid_ratio) >> 8,
                    (b * lid_ratio) >> 8,
                )

            # Session state LED override
            state = self._overlay.session_mgr.state
            leds = self._overlay.led_override(state, frame, leds, brightness)

            np = self._np
            for i in range(n):
                np[i] = leds[i]
            np.write()

    def render(self, tft, theme, frame):
        if self._pause.is_open:
            if self._dirty:
                self._dirty = False
                tft.fill(theme.BLACK)
                landscape = theme.width > theme.height
                if landscape:
                    self._render_landscape(tft, theme, frame)
                else:
                    self._render_portrait(tft, theme, frame)
            self._pause.render(tft, theme, frame)
            return

        self._dirty = False
        tft.fill(theme.BLACK)
        landscape = theme.width > theme.height
        if landscape:
            self._render_landscape(tft, theme, frame)
        else:
            self._render_portrait(tft, theme, frame)

        # Hold-to-pause progress bar (drawn on top by PauseMenu)
        self._pause.render(tft, theme, frame)

    def _render_landscape(self, tft, theme, frame):
        """Split layout: pattern name + buttons left, encoder bars + toggles right."""
        sw = [False] * 4
        held = [False] * 8
        enc_spd = 0
        if self._manager:
            sw = self._manager.inp.sw
            held = self._manager.inp.btn_held
            enc_spd = self._manager.inp.enc_pos[ENC_B]

        mid_x = theme.width // 2

        # --- Left half: pattern + buttons ---
        pat_colour = theme.BTN_565[self._active_pattern]
        tft.fill_rect(0, 0, mid_x - 8, 20, pat_colour)
        tft.text(PATTERN_NAMES[self._active_pattern], 4, 6, theme.BLACK)

        # Button grid (4x2)
        tft.text(t("demo_buttons"), 0, 28, theme.WHITE)
        draw_button_grid(
            tft,
            theme,
            theme.BTN_NAMES,
            held,
            cols=4,
            x0=0,
            y0=42,
            cell_w=36,
            cell_h=22,
        )

        # Toggle indicators
        tft.text(t("demo_toggles"), 0, 90, theme.WHITE)
        toggle_labels = [
            t("tog_reverse"),
            t("tog_mirror"),
            t("tog_strobe"),
            t("tog_invert"),
        ]
        for i in range(len(toggle_labels)):
            x = i * 36
            y = 104
            if i < len(sw) and sw[i]:
                tft.fill_rect(x, y, 32, 14, theme.GREEN)
                tft.text(toggle_labels[i], x + 4, y + 3, theme.BLACK)
            else:
                tft.rect(x, y, 32, 14, theme.WHITE)
                tft.text(toggle_labels[i], x + 4, y + 3, theme.WHITE)

        # --- Right half: encoder bars ---
        rx = mid_x + 8
        rw = theme.width - rx - 4

        draw_centered(tft, t("home_title"), 6, theme.WHITE, theme.width)

        bar_info = [
            (t("demo_bri"), theme.CYAN, self._brightness.value, 255),
            (t("demo_spd"), theme.ORANGE, enc_spd, 20),
        ]
        for i, (label, colour_565, val, max_val) in enumerate(bar_info):
            y = 40 + i * 28
            tft.text(label, rx, y, colour_565)
            bar_x = rx + 32
            bar_w = rw - 32
            tft.rect(bar_x, y, bar_w, 14, theme.WHITE)
            draw_progress_bar(
                tft, bar_x, y, bar_w, 14, val, max_val, colour_565, theme.BLACK
            )

        # Back hint
        tft.text(t("demo_back"), rx, theme.height - 16, theme.MUTED)

    def _render_portrait(self, tft, theme, frame):
        """Stacked layout for portrait displays."""
        sw = [False] * 4
        held = [False] * 8
        enc_spd = 0
        if self._manager:
            sw = self._manager.inp.sw
            held = self._manager.inp.btn_held
            enc_spd = self._manager.inp.enc_pos[ENC_B]

        tft.text(t("home_title"), 32, 3, theme.WHITE)

        pat_colour = theme.BTN_565[self._active_pattern]
        tft.fill_rect(0, 16, theme.width, 12, pat_colour)
        tft.text(PATTERN_NAMES[self._active_pattern], 4, 18, theme.BLACK)

        bar_info = [
            (t("demo_bri"), theme.CYAN, self._brightness.value, 255),
            (t("demo_spd"), theme.ORANGE, enc_spd, 20),
        ]
        for i, (label, colour_565, val, max_val) in enumerate(bar_info):
            y = 32 + i * 16
            tft.rect(24, y, 96, 10, theme.WHITE)
            draw_progress_bar(tft, 24, y, 96, 10, val, max_val, colour_565, theme.BLACK)
            tft.text(label, 0, y + 1, colour_565)

        tft.text(t("demo_toggles"), 0, 70, theme.WHITE)
        toggle_labels = [
            t("tog_reverse"),
            t("tog_mirror"),
            t("tog_strobe"),
            t("tog_invert"),
        ]
        for i in range(len(toggle_labels)):
            x = i * 32
            y = 82
            if i < len(sw) and sw[i]:
                tft.fill_rect(x, y, 28, 14, theme.GREEN)
                tft.text(toggle_labels[i], x + 2, y + 3, theme.BLACK)
            else:
                tft.rect(x, y, 28, 14, theme.WHITE)
                tft.text(toggle_labels[i], x + 2, y + 3, theme.WHITE)

        tft.text(t("demo_buttons"), 0, 102, theme.WHITE)
        draw_button_grid(
            tft,
            theme,
            theme.BTN_NAMES,
            held,
            cols=4,
            x0=0,
            y0=114,
            cell_w=32,
            cell_h=16,
        )
