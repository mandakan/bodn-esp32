# bodn/ui/mystery.py — Mystery Box game screen (Color Alchemy)

import time
from micropython import const
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.input import BrightnessControl, EncoderAccumulator
from bodn.ui.widgets import draw_centered, draw_button_grid
from bodn.ui.pause import PauseMenu
from bodn.mystery_rules import (
    MysteryEngine,
    OUT_IDLE,
    OUT_MIX,
    OUT_MAGIC,
    EV_NONE,
    EV_NEW_SINGLE,
    EV_NEW_MAGIC,
    EV_NEW_MOD,
    EV_COMPLETE,
    FINALE_MS,
)
from bodn.i18n import t
from bodn.neo import neo
from bodn.storage import save_settings

NAV = const(0)  # config.ENC_NAV
_SETTINGS_KEY = "mystery_unlocks"

# Discovery tones — whole-tone scale, mysterious and exploratory
_MYSTERY_TONES = (262, 294, 330, 370, 415, 466, 523, 587)  # C4-D5 whole-tone


class MysteryScreen(Screen):
    """Mystery Box -- discover hidden colour combinations through play.

    Pressing two caps within ~1s either averages their colours or, for
    hand-picked pairs, fires a magic combo. Singles and magic combos build
    a 16-tile recipe book (visible on the secondary display). Modifier
    toggles and the hue encoder unlock at 5 / 10 / all-singles.

    Hold the nav encoder button to open the pause menu.
    """

    def __init__(
        self,
        overlay,
        arcade=None,
        audio=None,
        settings=None,
        secondary_screen=None,
        on_exit=None,
    ):
        self._overlay = overlay
        self._arcade = arcade
        self._audio = audio
        self._settings = settings
        self._secondary = secondary_screen
        self._on_exit = on_exit
        self._engine = MysteryEngine()
        self._engine.load_state(settings.get(_SETTINGS_KEY) if settings else None)
        self._brightness = BrightnessControl(settings=settings)
        self._hue_acc = EncoderAccumulator(
            settings=settings, fast_threshold=400, fast_multiplier=4
        )
        self._hue = 0
        self._manager = None
        self._pause = PauseMenu(settings=settings)
        self._prev_out_type = OUT_IDLE
        self._dirty = True
        self._full_clear = True
        self._leds_dirty = True
        self._needs_save = False
        self._finale_ms = 0  # >0 while finale is active
        # HUD cache - avoids per-frame string formatting
        self._hud_counter = ""
        self._hud_found = -1
        self._hud_total = -1

    def _on_immediate_press(self, kind, index):
        """Scan-time callback - fires at 200 Hz, bypassing frame sync."""
        if kind != "btn" or index >= len(_MYSTERY_TONES):
            return
        if self._audio:
            self._audio.tone(_MYSTERY_TONES[index], 200)

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._brightness.reset()
        self._hue_acc.reset()
        self._hue = 0
        self._last_ms = time.ticks_ms()
        self._dirty = True
        self._full_clear = True
        self._leds_dirty = True
        arc = self._arcade
        if arc:
            arc.wave(0, speed=1)
            arc.flush()
        manager.inp.set_on_press(self._on_immediate_press)
        neo.clear_all_overrides()
        # Push current state to the recipe book so it's correct on enter.
        if self._secondary:
            self._secondary.set_state(
                self._engine.singles_discovered,
                self._engine.magic_discovered,
            )

    def exit(self):
        self._persist_state(force=True)
        if self._manager:
            self._manager.inp.set_on_press(None)
        arc = self._arcade
        if arc:
            arc.all_off()
            arc.flush()
        neo.all_off()
        neo.clear_all_overrides()
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
            self._full_clear = True
        if self._pause.is_open or self._pause.is_holding:
            return

        eng = self._engine
        prev_mods = (eng.sw_invert, eng.sw_mirror, eng.hue_shift)
        eng.sw_invert = inp.sw[0] if len(inp.sw) > 0 else False
        eng.sw_mirror = inp.sw[1] if len(inp.sw) > 1 else False
        hue_units = self._hue_acc.update(
            inp.enc_delta[config.ENC_B], inp.enc_velocity[config.ENC_B]
        )
        if hue_units:
            self._hue = (self._hue + hue_units * 13) % 256
        eng.hue_shift = self._hue
        new_mods = (eng.sw_invert, eng.sw_mirror, eng.hue_shift)
        if new_mods != prev_mods:
            self._dirty = True
            self._leds_dirty = True

        # Find first just-pressed button and tick the engine
        btn = inp.first_btn_pressed()
        now = time.ticks_ms()
        dt = time.ticks_diff(now, self._last_ms)
        self._last_ms = now
        eng.update(btn, dt)

        # Drain any discovery event the engine raised this tick.
        ev = eng.consume_event()
        if ev != EV_NONE:
            self._handle_event(ev)

        # Detect output-state changes that require a redraw
        out_type = eng.output_type
        if out_type != self._prev_out_type:
            self._prev_out_type = out_type
            self._dirty = True
            self._full_clear = True
            self._leds_dirty = True
        if btn >= 0:
            self._dirty = True
            self._leds_dirty = True

        # Brightness from encoder A (velocity-aware)
        prev_bri = self._brightness.value
        self._brightness.update(
            inp.enc_delta[config.ENC_A], inp.enc_velocity[config.ENC_A]
        )
        if self._brightness.value != prev_bri:
            self._leds_dirty = True

        # Tick the finale timer; when it ends, drop back to normal patterns.
        if self._finale_ms > 0:
            self._finale_ms = max(0, self._finale_ms - dt)
            if self._finale_ms == 0:
                self._leds_dirty = True
                self._dirty = True

        if self._leds_dirty:
            self._leds_dirty = False
            self._refresh_leds()

        # Arcade ambient effects matching game state
        arc = self._arcade
        if arc:
            if self._finale_ms > 0:
                still = arc.tick_flash()
                if not still:
                    for i in range(arc.count):
                        arc.flash(i, duration=20)
            elif out_type == OUT_MAGIC:
                still = arc.tick_flash()
                if not still:
                    for i in range(arc.count):
                        arc.flash(i, duration=15)
            elif out_type == OUT_MIX:
                arc.all_pulse(frame, speed=2)
            else:
                arc.wave(frame, speed=1)
            arc.flush()

        # Periodic persistence: only writes when something actually changed.
        self._persist_state()

    def _handle_event(self, ev):
        eng = self._engine
        # Push the latest state + highlight to the recipe book.
        if self._secondary:
            self._secondary.set_state(
                eng.singles_discovered,
                eng.magic_discovered,
                highlight=eng.last_unlock,
            )
        self._needs_save = True
        self._dirty = True
        self._leds_dirty = True

        audio = self._audio
        if not audio:
            return
        if ev == EV_NEW_SINGLE:
            audio.play_sound("boop", channel="ui")
        elif ev == EV_NEW_MAGIC:
            audio.play_sound("reward", channel="ui")
        elif ev == EV_NEW_MOD:
            audio.play_sound("rule_switch", channel="ui")
        elif ev == EV_COMPLETE:
            audio.play_sound("success", channel="ui")
            self._finale_ms = FINALE_MS

    def _refresh_leds(self):
        eng = self._engine
        brightness = self._brightness.value
        lid_bright = min(brightness, config.NEOPIXEL_LID_BRIGHTNESS)

        if self._finale_ms > 0:
            # 16/16 finale: rainbow takeover on every zone.
            neo.clear_all_overrides()
            neo.all_pattern(neo.PAT_RAINBOW, speed=4, brightness=brightness)
            return

        # Sticks: solid colour reflecting the current output (engine writes
        # indices 0..N_STICKS-1 into the shared LED buffer).
        leds = eng.make_static_leds(brightness)
        for i in range(16):
            r, g, b = leds[i]
            neo.set_pixel(i, r, g, b)

        # Lid ring: ambient glow keyed to the output type.
        out_type = eng.output_type
        out_color = eng.display_color
        if out_type == OUT_MAGIC:
            neo.zone_pattern(
                neo.ZONE_LID_RING,
                neo.PAT_CHASE,
                speed=3,
                colour=out_color,
                brightness=lid_bright,
            )
        elif out_type != OUT_IDLE:
            neo.zone_pattern(
                neo.ZONE_LID_RING,
                neo.PAT_PULSE,
                speed=1,
                colour=out_color,
                brightness=lid_bright,
            )
        else:
            neo.zone_pattern(
                neo.ZONE_LID_RING,
                neo.PAT_PULSE,
                speed=1,
                colour=(60, 20, 80),
                brightness=lid_bright // 2,
            )

    def _persist_state(self, force=False):
        if not (self._needs_save or force) or not self._settings:
            return
        if not self._needs_save and force is True:
            # Nothing changed since last write; skip flash wear.
            return
        self._settings[_SETTINGS_KEY] = self._engine.to_state()
        save_settings(self._settings)
        self._needs_save = False

    def render(self, tft, theme, frame):
        if self._pause.is_open:
            if self._dirty:
                self._dirty = False
                tft.fill(theme.BLACK)
                self._full_clear = False
                self._render_game(tft, theme, frame)
            self._pause.render(tft, theme, frame)
            return

        if self._dirty:
            self._dirty = False
            if self._full_clear:
                self._full_clear = False
                tft.fill(theme.BLACK)
            self._render_game(tft, theme, frame)

        # Hold-to-pause progress bar (always called so PauseMenu can clear)
        self._pause.render(tft, theme, frame)

    def _render_game(self, tft, theme, frame):
        eng = self._engine
        out_type = eng.output_type
        out_color = eng.display_color
        held = self._manager.inp.btn_held if self._manager else [False] * 8
        w = theme.width
        h = theme.height

        # Clear swatch + label zone (top half) for redraw
        swatch_y = 4
        swatch_h = h // 2 - 8
        tft.fill_rect(0, swatch_y, w, swatch_h + 24, theme.BLACK)

        # Big colour swatch -- top area, full width
        if self._finale_ms > 0:
            draw_centered(
                tft,
                t("mystery_complete"),
                swatch_y + swatch_h // 4,
                theme.YELLOW,
                w,
                scale=3,
            )
        elif out_type != OUT_IDLE:
            r, g, b = out_color
            c565 = tft.rgb(r, g, b)
            tft.fill_rect(8, swatch_y, w - 16, swatch_h, c565)
            if out_type == OUT_MAGIC:
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

        # Button row: single row of 8 matching the physical strip
        btn_y = h // 2 + 20
        cell_w = w // 8 - 2
        cell_h = h - btn_y - 20
        btn_x0 = (w - 8 * cell_w) // 2
        draw_button_grid(
            tft,
            theme,
            theme.BTN_NAMES,
            held,
            cols=8,
            x0=btn_x0,
            y0=btn_y,
            cell_w=cell_w,
            cell_h=cell_h,
        )

        # Bottom bar: discovery counter + modifier dots (only those unlocked)
        tft.fill_rect(0, h - 18, w, 18, theme.BLACK)
        found = eng.discovery_count
        total = eng.total_discoverable
        if found != self._hud_found or total != self._hud_total:
            self._hud_found = found
            self._hud_total = total
            self._hud_counter = "{}/{}".format(found, total)
        counter_color = theme.YELLOW if found == total else theme.MUTED
        tft.text(self._hud_counter, 8, h - 14, counter_color)
        self._draw_mod_dots(tft, theme, w - 60, h - 12)

    def _draw_mod_dots(self, tft, theme, x, y):
        """Draw small coloured dots for each modifier, dim until unlocked."""
        eng = self._engine
        # Each entry: (unlocked, active, active_color, locked_color)
        slots = (
            (eng.invert_unlocked, eng.sw_invert, theme.CYAN),
            (eng.mirror_unlocked, eng.sw_mirror, theme.GREEN),
        )
        dx = x
        for unlocked, active, color in slots:
            if not unlocked:
                # Tiny dim square hints at a locked slot.
                tft.rect(dx, y, 6, 6, theme.DIM)
            elif active:
                tft.fill_rect(dx, y, 6, 6, color)
            else:
                tft.rect(dx, y, 6, 6, color)
            dx += 10
        # Hue shift indicator (only meaningful once unlocked).
        if eng.hue_unlocked and eng.hue_shift > 0:
            bar_w = eng.hue_shift * 20 // 255
            tft.fill_rect(dx + 4, y, max(2, bar_w), 6, theme.MAGENTA)
        elif not eng.hue_unlocked:
            tft.rect(dx + 4, y, 20, 6, theme.DIM)
