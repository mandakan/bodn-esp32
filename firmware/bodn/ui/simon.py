# bodn/ui/simon.py — Pattern Copy (Simon) game screen

import time
from micropython import const
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.input import BrightnessControl
from bodn.ui.widgets import draw_centered, draw_button_grid
from bodn.ui.pause import PauseMenu
from bodn.i18n import t
from bodn.simon_rules import (
    SimonEngine,
    READY,
    SHOWING,
    WAITING,
    WIN,
    FAIL,
    GAME_OVER,
    NUM_BUTTONS,
)
from bodn.neo import neo
from bodn.ui.catface import NEUTRAL, CURIOUS, HAPPY

NAV = const(0)  # config.ENC_NAV

# Pentatonic tones per button (6 buttons, ascending pitch)
_SIMON_TONES = (262, 330, 392, 523, 659, 784)  # C4 E4 G4 C5 E5 G5

# Map game states to cat emotions
_STATE_EMOTIONS = {
    READY: NEUTRAL,
    SHOWING: CURIOUS,
    WAITING: CURIOUS,
    WIN: HAPPY,
    FAIL: NEUTRAL,
    GAME_OVER: NEUTRAL,
}


class SimonScreen(Screen):
    """Pattern Copy — watch the sequence, then repeat it!

    Buttons 0–5 are the play buttons (6 colors).  They render as a single
    row on screen matching the physical strip below the display.
    Hold nav encoder button to open the pause menu.
    """

    # Tight flash/playback cadence — throttle the background NFC scanner.
    nfc_low_priority = True

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
        self._secondary = secondary_screen
        self._on_exit = on_exit
        self._engine = SimonEngine()
        self._brightness = BrightnessControl(settings=settings)
        self._manager = None
        self._pause = PauseMenu(settings=settings)
        self._prev_state = None
        self._prev_active_btn = -1
        self._dirty = True
        self._full_clear = True
        self._leds_dirty = True

    def _on_immediate_press(self, kind, index):
        """Scan-time callback — fires at 200 Hz, bypassing frame sync."""
        if kind != "btn" or index >= NUM_BUTTONS:
            return
        state = self._engine.state
        if state == WAITING and self._audio:
            self._audio.tone(_SIMON_TONES[index], 150)
        elif state == READY and self._audio:
            self._audio.tone(_SIMON_TONES[0], 100)

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._engine.reset()
        self._brightness.reset()
        self._last_ms = time.ticks_ms()
        self._dirty = True
        self._full_clear = True
        neo.clear_all_overrides()
        manager.inp.set_on_press(self._on_immediate_press)

    def exit(self):
        if self._manager:
            self._manager.inp.set_on_press(None)
        neo.all_off()
        neo.clear_all_overrides()
        if self._arcade:
            self._arcade.all_off()
            self._arcade.flush()
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

        # Find first just-pressed button
        btn = inp.first_btn_pressed()
        now = time.ticks_ms()
        dt = time.ticks_diff(now, self._last_ms)
        self._last_ms = now
        self._engine.update(btn, dt)

        # Detect state changes
        state = self._engine.state
        if state != self._prev_state:
            self._prev_state = state
            self._dirty = True
            self._full_clear = True
            self._leds_dirty = True
            # Audio feedback for state transitions
            if self._audio:
                if state == WIN:
                    self._audio.play_sound("correct", channel="sfx")
                elif state == FAIL:
                    self._audio.play_sound("wrong", channel="sfx")
            # Update cat face
            if self._secondary:
                emotion = _STATE_EMOTIONS.get(state, NEUTRAL)
                self._secondary.set_emotion(emotion)

        # Active button advances during SHOWING — only the dot row changes,
        # so use a partial push instead of a full redraw.
        active_btn = self._engine.active_button
        if active_btn != self._prev_active_btn:
            self._prev_active_btn = active_btn
            self._leds_dirty = True
            # Play tone when sequence shows a new button
            if state == SHOWING and active_btn >= 0 and self._audio:
                self._audio.tone(_SIMON_TONES[active_btn], 150)
            if state == SHOWING and not self._dirty and self._manager:
                self._push_dot_row()
            else:
                self._dirty = True
        # Button press feedback
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

            # Sticks: game feedback as pixel overrides
            leds = self._engine.make_static_leds(brightness)
            for i in range(16):
                r, g, b = leds[i]
                neo.set_pixel(i, r, g, b)

            # Lid ring: ambient effect matching game state
            state = self._engine.state
            if state == WIN:
                neo.zone_pattern(
                    neo.ZONE_LID_RING,
                    neo.PAT_RAINBOW,
                    speed=2,
                    brightness=lid_bright,
                )
            elif state == FAIL:
                neo.zone_pattern(
                    neo.ZONE_LID_RING,
                    neo.PAT_PULSE,
                    speed=3,
                    colour=(255, 0, 0),
                    brightness=lid_bright,
                )
            elif state == SHOWING and self._engine.active_button >= 0:
                from bodn.simon_rules import BTN_COLORS

                c = BTN_COLORS[self._engine.active_button]
                neo.zone_pattern(
                    neo.ZONE_LID_RING,
                    neo.PAT_PULSE,
                    speed=1,
                    colour=c,
                    brightness=lid_bright,
                )
            else:
                neo.zone_off(neo.ZONE_LID_RING)

        # Arcade LEDs: animated per-state (runs every frame)
        arc = self._arcade
        if arc:
            state = self._engine.state
            if state == WIN:
                if not any(arc._flash_ttl):
                    for i in range(5):
                        arc.flash(i, duration=15)
                arc.tick_flash()
            elif state == SHOWING:
                arc.all_pulse(frame, speed=2)
            elif state in (READY, GAME_OVER):
                arc.wave(frame, speed=1)
            elif state == WAITING:
                arc.wave(frame, speed=2)
            elif state == FAIL:
                arc.all_glow()
            else:
                arc.all_off()
            arc.flush()

    def _push_dot_row(self):
        """Partial push of just the sequence dot row during SHOWING.

        Called from update() when active_button advances and the rest of
        the screen hasn't changed. Pushes only the dot row rectangle
        (~12 KB for landscape) instead of the full framebuffer (~150 KB).
        """
        tft = self._manager.tft
        theme = self._manager.theme
        eng = self._engine
        round_num = eng.sequence_length

        dot_y = 40
        dot_size = min(20, (theme.width - 40) // max(1, round_num) - 4)
        step = dot_size + 4
        total_w = round_num * step - 4

        dot_x0 = (theme.width - total_w) // 2
        row_h = dot_size + 4
        tft.fill_rect(0, dot_y, theme.width, row_h, theme.BLACK)

        for i in range(round_num):
            x = dot_x0 + i * step
            color = theme.BTN_565[eng.sequence[i]]
            if i < eng._show_pos or (i == eng._show_pos and eng.active_button >= 0):
                tft.fill_rect(x, dot_y, dot_size, dot_size, color)
            else:
                tft.rect(x, dot_y, dot_size, dot_size, theme.MUTED)

        self._manager.request_show(0, dot_y, theme.width, row_h)

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

        # Hold-to-pause progress bar (always called so PauseMenu can clear its dirty flag)
        self._pause.render(tft, theme, frame)

    def _render_game(self, tft, theme, frame):
        eng = self._engine
        w = theme.width
        h = theme.height
        held = self._manager.inp.btn_held if self._manager else [False] * 8

        if eng.state == READY:
            draw_centered(tft, t("simon_title"), 20, theme.CYAN, w, scale=2)
            draw_centered(tft, t("simon_watch_repeat"), h // 2 - 8, theme.WHITE, w)
            draw_centered(tft, t("simon_press_start"), h // 2 + 16, theme.MUTED, w)
            if eng.high_score > 0:
                draw_centered(
                    tft,
                    t("simon_best", eng.high_score),
                    h - 30,
                    theme.YELLOW,
                    w,
                )
            return

        if eng.state == GAME_OVER:
            draw_centered(tft, t("simon_great"), 30, theme.YELLOW, w, scale=2)
            draw_centered(
                tft,
                t("simon_score", eng.score),
                h // 2 - 8,
                theme.WHITE,
                w,
                scale=2,
            )
            if eng.high_score > 0:
                draw_centered(
                    tft, t("simon_best", eng.high_score), h // 2 + 24, theme.CYAN, w
                )
            draw_centered(tft, t("simon_press_again"), h - 30, theme.MUTED, w)
            return

        # --- Active game states ---

        # Top: state label + round info
        round_num = eng.sequence_length
        if eng.state == SHOWING:
            draw_centered(tft, t("simon_watch"), 8, theme.YELLOW, w, scale=2)
        elif eng.state == WAITING:
            draw_centered(tft, t("simon_your_turn"), 8, theme.GREEN, w, scale=2)
        elif eng.state == WIN:
            draw_centered(tft, t("simon_yes"), 8, theme.YELLOW, w, scale=2)
        elif eng.state == FAIL:
            draw_centered(tft, t("simon_try_again"), 8, theme.RED, w, scale=2)

        # Sequence display: colored dots showing the pattern
        dot_y = 40
        dot_size = min(20, (w - 40) // max(1, round_num) - 4)
        total_w = round_num * (dot_size + 4) - 4
        dot_x0 = (w - total_w) // 2

        for i in range(round_num):
            x = dot_x0 + i * (dot_size + 4)
            btn_idx = eng.sequence[i]
            color = theme.BTN_565[btn_idx]

            if eng.state == SHOWING:
                if i < eng._show_pos or (i == eng._show_pos and eng.active_button >= 0):
                    tft.fill_rect(x, dot_y, dot_size, dot_size, color)
                else:
                    tft.rect(x, dot_y, dot_size, dot_size, theme.MUTED)
            elif eng.state == WAITING:
                if i < eng._input_pos:
                    tft.fill_rect(x, dot_y, dot_size, dot_size, color)
                elif i == eng._input_pos:
                    tft.rect(x, dot_y, dot_size, dot_size, theme.WHITE)
                else:
                    tft.rect(x, dot_y, dot_size, dot_size, theme.MUTED)
            elif eng.state == WIN:
                tft.fill_rect(x, dot_y, dot_size, dot_size, color)
            elif eng.state == FAIL:
                if i < eng._input_pos:
                    tft.fill_rect(x, dot_y, dot_size, dot_size, color)
                else:
                    tft.rect(x, dot_y, dot_size, dot_size, theme.MUTED)

        # Button row — single row of 6 matching physical buttons 0-5 left-to-right
        btn_y = h // 2 + 20
        btn_names = theme.BTN_NAMES[:NUM_BUTTONS]
        btn_held = held[:NUM_BUTTONS]
        cell_w = w // NUM_BUTTONS - 2
        cell_h = h - btn_y - 24
        btn_x0 = (w - NUM_BUTTONS * cell_w) // 2
        draw_button_grid(
            tft,
            theme,
            btn_names,
            btn_held,
            cols=NUM_BUTTONS,
            x0=btn_x0,
            y0=btn_y,
            cell_w=cell_w,
            cell_h=cell_h,
        )

        # Bottom bar: score
        tft.fill_rect(0, h - 18, w, 18, theme.BLACK)
        tft.text(t("simon_round", round_num), 8, h - 14, theme.MUTED)
        if eng.high_score > 0:
            hs_text = t("simon_best_short", eng.high_score)
            tft.text(hs_text, w - len(hs_text) * 8 - 8, h - 14, theme.YELLOW)
