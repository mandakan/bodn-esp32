# bodn/ui/mystery.py — Mystery Box game screen (Color Alchemy)

from micropython import const
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.input import BrightnessControl, EncoderAccumulator
from bodn.ui.widgets import draw_centered, draw_button_grid
from bodn.ui.pause import PauseMenu
from bodn.mystery_rules import MysteryEngine, OUT_IDLE, OUT_MIX, OUT_MAGIC
from bodn.i18n import t
from bodn.patterns import N_LEDS, zone_pulse, zone_chase, ZONE_LID_RING
from bodn.ui.catface import NEUTRAL, CURIOUS, HAPPY

NAV = const(0)  # config.ENC_NAV


class MysteryScreen(Screen):
    """Mystery Box — discover hidden rules through experimentation.

    No instructions. No tutorial. The box just reacts.
    Every input produces something interesting.

    Hold nav encoder button to open the pause menu (resume / back to menu).
    """

    def __init__(self, np, overlay, settings=None, secondary_screen=None, on_exit=None):
        self._np = np
        self._overlay = overlay
        self._secondary = secondary_screen
        self._on_exit = on_exit
        self._engine = MysteryEngine()
        self._brightness = BrightnessControl(settings=settings)
        self._hue_acc = EncoderAccumulator(
            settings=settings, fast_threshold=400, fast_multiplier=4
        )
        self._hue = 0
        self._manager = None
        self._pause = PauseMenu(settings=settings)
        self._prev_out_type = OUT_IDLE
        self._dirty = True
        self._leds_dirty = True

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._brightness.reset()
        self._hue_acc.reset()
        self._hue = 0
        self._dirty = True

    def exit(self):
        if self._on_exit:
            self._on_exit()

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

        # Update modifier state from switches and encoder B
        eng = self._engine
        prev_mods = (
            eng.sw_invert,
            eng.sw_mirror,
            eng.hue_shift,
        )
        eng.sw_invert = inp.sw[0] if len(inp.sw) > 0 else False
        eng.sw_mirror = inp.sw[1] if len(inp.sw) > 1 else False
        hue_units = self._hue_acc.update(
            inp.enc_delta[config.ENC_B], inp.enc_velocity[config.ENC_B]
        )
        if hue_units:
            self._hue = (self._hue + hue_units * 13) % 256
        eng.hue_shift = self._hue
        new_mods = (
            eng.sw_invert,
            eng.sw_mirror,
            eng.hue_shift,
        )
        if new_mods != prev_mods:
            self._dirty = True
            self._leds_dirty = True

        # Find first just-pressed button
        btn = inp.first_btn_pressed()
        self._engine.update(btn, frame)

        # Detect state changes that require a redraw
        out_type = self._engine.output_type
        if out_type != self._prev_out_type:
            self._prev_out_type = out_type
            self._dirty = True
            self._leds_dirty = True
            # Update secondary display cat face
            if self._secondary:
                emotion = {OUT_IDLE: NEUTRAL, OUT_MIX: CURIOUS, OUT_MAGIC: HAPPY}.get(
                    out_type, NEUTRAL
                )
                self._secondary.set_emotion(emotion)
        if btn >= 0:
            self._dirty = True
            self._leds_dirty = True

        # Update brightness from encoder A (velocity-aware)
        prev_bri = self._brightness.value
        self._brightness.update(
            inp.enc_delta[config.ENC_A], inp.enc_velocity[config.ENC_A]
        )
        if self._brightness.value != prev_bri:
            self._leds_dirty = True

        # Write LEDs only when state changes (static patterns, no animation)
        if self._leds_dirty:
            self._leds_dirty = False
            brightness = self._brightness.value
            lid_bright = min(brightness, config.NEOPIXEL_LID_BRIGHTNESS)

            # Sticks: game feedback (engine writes indices 0–15)
            leds = self._engine.make_static_leds(brightness)

            # Lid ring: ambient glow matching output color
            out_type = self._engine.output_type
            out_color = self._engine.display_color
            if out_type == OUT_MAGIC:
                zone_chase(ZONE_LID_RING, frame, 3, out_color, lid_bright)
            elif out_type != OUT_IDLE:
                zone_pulse(ZONE_LID_RING, frame, 1, out_color, lid_bright)
            else:
                zone_pulse(ZONE_LID_RING, frame, 1, (60, 20, 80), lid_bright // 2)

            ses_state = self._overlay.session_mgr.state
            leds = self._overlay.static_led_override(ses_state, leds, brightness)

            np = self._np
            n = N_LEDS
            for i in range(n):
                np[i] = leds[i]
            np.write()

    def render(self, tft, theme, frame):
        if self._pause.is_open:
            if self._dirty:
                # Redraw game underneath first time, then overlay pause
                self._dirty = False
                tft.fill(theme.BLACK)
                landscape = theme.width > theme.height
                if landscape:
                    self._render_landscape(tft, theme, frame)
                else:
                    self._render_portrait(tft, theme, frame)
            self._pause.render(tft, theme, frame)
            return

        if self._dirty:
            self._dirty = False
            tft.fill(theme.BLACK)
            landscape = theme.width > theme.height
            if landscape:
                self._render_landscape(tft, theme, frame)
            else:
                self._render_portrait(tft, theme, frame)

        # Hold-to-pause progress bar (always called so PauseMenu can clear its dirty flag)
        self._pause.render(tft, theme, frame)

    def _render_landscape(self, tft, theme, frame):
        out_type = self._engine.output_type
        out_color = self._engine.display_color
        held = self._manager.inp.btn_held if self._manager else [False] * 8
        w = theme.width
        h = theme.height

        # Big color swatch — top area, full width
        swatch_y = 4
        swatch_h = h // 2 - 8
        if out_type != OUT_IDLE:
            r, g, b = out_color
            c565 = tft.rgb(r, g, b)
            tft.fill_rect(8, swatch_y, w - 16, swatch_h, c565)

            if out_type == OUT_MAGIC:
                for i in range(8):
                    px = ((frame * 7 + i * 37) * 53) % (w - 32) + 16
                    py = ((frame * 11 + i * 23) * 41) % (swatch_h - 8) + swatch_y + 4
                    tft.fill_rect(px, py, 5, 5, theme.WHITE)
                draw_centered(
                    tft,
                    t("mystery_magic"),
                    swatch_y + swatch_h + 4,
                    theme.YELLOW,
                    w,
                    scale=2,
                )
            elif out_type == OUT_MIX:
                draw_centered(
                    tft,
                    t("mystery_mix"),
                    swatch_y + swatch_h + 4,
                    theme.WHITE,
                    w,
                    scale=2,
                )
        else:
            draw_centered(tft, "?", swatch_y + swatch_h // 4, theme.MUTED, w, scale=4)

        # Button grid — bottom half, centered
        btn_y = h // 2 + 20
        cell_w = w // 4 - 8
        cell_h = (h - btn_y - 20) // 2
        btn_x0 = (w - 4 * cell_w) // 2
        draw_button_grid(
            tft,
            theme,
            theme.BTN_NAMES,
            held,
            cols=4,
            x0=btn_x0,
            y0=btn_y,
            cell_w=cell_w,
            cell_h=cell_h,
        )

        # Bottom bar: discovery counter + modifier dots
        found = self._engine.discovery_count
        total = self._engine.total_discoverable
        tft.text("{}/{}".format(found, total), 8, h - 14, theme.MUTED)
        self._draw_mod_dots(tft, theme, w - 60, h - 12)

    def _render_portrait(self, tft, theme, frame):
        out_type = self._engine.output_type
        out_color = self._engine.display_color
        held = self._manager.inp.btn_held if self._manager else [False] * 8
        w = theme.width
        h = theme.height

        # Large color swatch — top half of screen
        swatch_y = 8
        swatch_h = h * 2 // 5
        if out_type != OUT_IDLE:
            r, g, b = out_color
            c565 = tft.rgb(r, g, b)
            tft.fill_rect(8, swatch_y, w - 16, swatch_h, c565)

            if out_type == OUT_MAGIC:
                for i in range(8):
                    px = ((frame * 7 + i * 37) * 53) % (w - 32) + 16
                    py = ((frame * 11 + i * 23) * 41) % (swatch_h - 16) + swatch_y + 8
                    tft.fill_rect(px, py, 5, 5, theme.WHITE)
                draw_centered(
                    tft,
                    t("mystery_magic"),
                    swatch_y + swatch_h + 8,
                    theme.YELLOW,
                    w,
                    scale=2,
                )
            elif out_type == OUT_MIX:
                draw_centered(
                    tft,
                    t("mystery_mix"),
                    swatch_y + swatch_h + 8,
                    theme.WHITE,
                    w,
                    scale=2,
                )
        else:
            draw_centered(tft, "?", swatch_y + swatch_h // 3, theme.MUTED, w, scale=4)

        # Button grid — centered, below swatch area
        btn_y = h * 3 // 5
        cell_w = w // 4 - 4
        cell_h = (h - btn_y - 24) // 2
        btn_x0 = (w - 4 * cell_w) // 2
        draw_button_grid(
            tft,
            theme,
            theme.BTN_NAMES,
            held,
            cols=4,
            x0=btn_x0,
            y0=btn_y,
            cell_w=cell_w,
            cell_h=cell_h,
        )

        # Bottom bar: discovery counter + modifier dots
        found = self._engine.discovery_count
        total = self._engine.total_discoverable
        tft.text("{}/{}".format(found, total), 8, h - 14, theme.MUTED)
        self._draw_mod_dots(tft, theme, w - 50, h - 12)

    def _draw_mod_dots(self, tft, theme, x, y):
        """Draw small colored dots for active modifiers."""
        eng = self._engine
        mods = [
            (eng.sw_invert, theme.CYAN),
            (eng.sw_mirror, theme.GREEN),
        ]
        dx = x
        for active, color in mods:
            if active:
                tft.fill_rect(dx, y, 6, 6, color)
            else:
                tft.rect(dx, y, 6, 6, theme.MUTED)
            dx += 10
        # Hue shift indicator: small bar
        if eng.hue_shift > 0:
            bar_w = eng.hue_shift * 20 // 255
            tft.fill_rect(dx + 4, y, max(2, bar_w), 6, theme.MAGENTA)
