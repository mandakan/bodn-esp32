# bodn/ui/rulefollow.py — Rule Follow game screen

import time
from micropython import const
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.input import BrightnessControl
from bodn.ui.widgets import draw_centered, fill_circle, draw_circle
from bodn.ui.pause import PauseMenu
from bodn.i18n import t
from bodn.rulefollow_rules import (
    RuleFollowEngine,
    READY,
    SHOW_RULE,
    STIMULUS,
    CORRECT,
    WRONG,
    RULE_SWITCH,
    GAME_OVER,
    RULE_MATCH,
    NUM_BUTTONS,
    BTN_COLORS,
    RULE_COLORS,
)
from bodn.neo import neo
from bodn.ui.catface import NEUTRAL, CURIOUS, HAPPY

NAV = const(0)  # config.ENC_NAV

# Full colour names for buttons 0–3 (matches BTN_COLORS order).
# BTN_NAMES in theme.py is a 3-char abbreviation sized for Mystery's
# narrow 8-cell row; here we want the readable word.
_COLOR_KEYS = ("color_green", "color_blue", "color_white", "color_yellow")

# Map game states to cat emotions
_STATE_EMOTIONS = {
    READY: NEUTRAL,
    SHOW_RULE: CURIOUS,
    STIMULUS: CURIOUS,
    CORRECT: HAPPY,
    WRONG: NEUTRAL,
    RULE_SWITCH: CURIOUS,
    GAME_OVER: HAPPY,
}

# Tone frequencies for stimulus feedback (one per button)
_STIM_TONES = (330, 440, 523, 659)  # E4, A4, C5, E5
_CORRECT_TONE = 880  # A5
_WRONG_TONE = 220  # A3
_SWITCH_TONE = 587  # D5


class RuleFollowScreen(Screen):
    """Rule Follow — watch the rule, respond to the stimulus!

    Buttons 0–3 are the play buttons (4 colors).
    Hold nav encoder button to open the pause menu.
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
        self._secondary = secondary_screen
        self._on_exit = on_exit
        self._engine = RuleFollowEngine()
        self._brightness = BrightnessControl(settings=settings)
        self._manager = None
        self._pause = PauseMenu(settings=settings)
        self._prev_state = None
        self._dirty = True
        self._full_clear = True
        self._leds_dirty = True
        # Cached RGB565 values — populated in enter()
        self._rule_565 = None
        self._btn_565 = None

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._engine.reset()
        self._brightness.reset()
        self._last_ms = time.ticks_ms()
        self._dirty = True
        self._full_clear = True
        neo.clear_all_overrides()
        # Pre-cache RGB565 conversions (avoids theme.rgb() calls per render)
        rgb = manager.theme.rgb
        self._rule_565 = [rgb(*c) for c in RULE_COLORS]
        self._btn_565 = [rgb(*c) for c in BTN_COLORS]

    def exit(self):
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
        # Pause menu
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

        # Buttons 4-7 are inactive in this mode — give gentle feedback
        if btn >= NUM_BUTTONS:
            if self._audio:
                self._audio.boop()
            btn = -1  # don't feed to engine

        now = time.ticks_ms()
        dt = time.ticks_diff(now, self._last_ms)
        self._last_ms = now
        prev_state = self._engine.state
        self._engine.update(btn, dt)

        # Detect state changes
        state = self._engine.state
        if state != self._prev_state:
            self._prev_state = state
            self._dirty = True
            self._full_clear = True
            self._leds_dirty = True
            # Update cat face
            if self._secondary:
                emotion = _STATE_EMOTIONS.get(state, NEUTRAL)
                self._secondary.set_emotion(emotion)
            # Audio feedback on state transitions
            self._play_audio(prev_state, state)

        # Button press during stimulus also triggers visual update
        if btn >= 0 and btn < NUM_BUTTONS:
            self._dirty = True
            self._leds_dirty = True

        # Update brightness from encoder A (velocity-aware)
        prev_bri = self._brightness.value
        self._brightness.update(
            inp.enc_delta[config.ENC_A], inp.enc_velocity[config.ENC_A]
        )
        if self._brightness.value != prev_bri:
            self._leds_dirty = True

        # Write LEDs only when state changes
        if self._leds_dirty:
            self._leds_dirty = False
            brightness = self._brightness.value
            lid_bright = min(brightness, config.NEOPIXEL_LID_BRIGHTNESS)

            leds = self._engine.make_static_leds(brightness)
            for i in range(16):
                r, g, b = leds[i]
                neo.set_pixel(i, r, g, b)

            eng = self._engine
            if eng.state == CORRECT:
                neo.zone_pattern(
                    neo.ZONE_LID_RING,
                    neo.PAT_PULSE,
                    speed=3,
                    colour=(0, 255, 0),
                    brightness=lid_bright,
                )
            elif eng.state == WRONG:
                neo.zone_pattern(
                    neo.ZONE_LID_RING,
                    neo.PAT_PULSE,
                    speed=2,
                    colour=(255, 0, 0),
                    brightness=lid_bright,
                )
            elif eng.state == RULE_SWITCH:
                neo.zone_pattern(
                    neo.ZONE_LID_RING,
                    neo.PAT_CHASE,
                    speed=4,
                    colour=RULE_COLORS[eng.current_rule],
                    brightness=lid_bright,
                )
            elif eng.state in (SHOW_RULE, STIMULUS):
                neo.zone_pattern(
                    neo.ZONE_LID_RING,
                    neo.PAT_SOLID,
                    colour=eng.rule_color,
                    brightness=lid_bright,
                )
            else:
                neo.zone_off(neo.ZONE_LID_RING)

        # Arcade LEDs: animated per-state (runs every frame)
        arc = self._arcade
        if arc:
            state = self._engine.state
            if state == CORRECT:
                if not any(arc._flash_ttl):
                    for i in range(5):
                        arc.flash(i, duration=15)
                arc.tick_flash()
            elif state == STIMULUS:
                arc.all_blink(frame, speed=3)
            elif state == SHOW_RULE:
                arc.all_pulse(frame, speed=1)
            elif state == RULE_SWITCH:
                arc.wave(frame, speed=3)
            elif state in (READY, GAME_OVER):
                arc.wave(frame, speed=1)
            elif state == WRONG:
                arc.all_glow()
            else:
                arc.all_off()
            arc.flush()

    def _play_audio(self, prev_state, new_state):
        """Play tone feedback on state transitions."""
        audio = self._audio
        if audio is None:
            return
        if new_state == STIMULUS:
            btn = self._engine.stimulus_button
            if 0 <= btn < len(_STIM_TONES):
                audio.tone(_STIM_TONES[btn], 200, channel=1)
        elif new_state == CORRECT:
            audio.play_sound("correct", channel="sfx")
        elif new_state == WRONG:
            audio.play_sound("wrong", channel="sfx")
        elif new_state == RULE_SWITCH:
            audio.play_sound("rule_switch", channel="sfx")

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

        self._pause.render(tft, theme, frame)

    def _render_game(self, tft, theme, frame):
        eng = self._engine
        w = theme.width
        h = theme.height
        held = self._manager.inp.btn_held if self._manager else [False] * 8

        if eng.state == READY:
            draw_centered(tft, t("rf_title"), 20, theme.CYAN, w, scale=2)
            draw_centered(tft, t("rf_instructions1"), h // 2 - 16, theme.WHITE, w)
            draw_centered(tft, t("rf_instructions2"), h // 2 + 4, theme.WHITE, w)
            draw_centered(tft, t("rf_press_start"), h - 30, theme.MUTED, w)
            return

        if eng.state == GAME_OVER:
            draw_centered(tft, t("rf_great"), 20, theme.YELLOW, w, scale=2)
            draw_centered(
                tft,
                "{}/{}".format(eng.score, eng.total),
                h // 2 - 16,
                theme.WHITE,
                w,
                scale=2,
            )
            if eng.best_streak > 0:
                draw_centered(
                    tft,
                    t("rf_best_streak", eng.best_streak),
                    h // 2 + 20,
                    theme.CYAN,
                    w,
                )
            draw_centered(tft, t("rf_press_again"), h - 30, theme.MUTED, w)
            return

        # --- Active game states ---
        rule_565 = self._rule_565[eng.current_rule]

        if eng.state == SHOW_RULE:
            rule_name = (
                t("rf_match") if eng.current_rule == RULE_MATCH else t("rf_opposite")
            )
            draw_centered(tft, rule_name, 20, rule_565, w, scale=2)
            # Draw rule pictogram: circle for match, X for opposite
            cx = w // 2
            cy = h // 2
            self._draw_rule_icon(tft, theme, cx, cy, eng.current_rule, rule_565)
            return

        if eng.state == RULE_SWITCH:
            draw_centered(tft, t("rf_new_rule"), 20, theme.YELLOW, w, scale=2)
            rule_name = (
                t("rf_match") if eng.current_rule == RULE_MATCH else t("rf_opposite")
            )
            draw_centered(tft, rule_name, h // 2 - 8, rule_565, w, scale=2)
            return

        if eng.state == STIMULUS:
            # Rule reminder at top
            rule_label = (
                t("rf_match_short")
                if eng.current_rule == RULE_MATCH
                else t("rf_opposite_short")
            )
            draw_centered(tft, rule_label, 4, rule_565, w)

            # Big stimulus color block
            stim_color = self._btn_565[eng.stimulus_button]
            block_size = min(w // 3, h // 2 - 20)
            bx = (w - block_size) // 2
            by = 24
            tft.fill_rect(bx, by, block_size, block_size, stim_color)

            # Button swatches below — colour circles matching the physical
            # cap colours 1:1. No text labels: the child matches by colour.
            btn_y = by + block_size + 12
            cell_w = w // NUM_BUTTONS
            cell_h = h - btn_y - 24
            r = min(cell_w, cell_h) // 2 - 4
            cy = btn_y + cell_h // 2
            for i in range(NUM_BUTTONS):
                cx = i * cell_w + cell_w // 2
                color = self._btn_565[i]
                if i < len(held) and held[i]:
                    fill_circle(tft, cx, cy, r, color)
                else:
                    draw_circle(tft, cx, cy, r, color)

            # Score bar
            tft.fill_rect(0, h - 18, w, 18, theme.BLACK)
            tft.text(
                "{}/{}".format(eng.score, eng.total),
                4,
                h - 14,
                theme.MUTED,
            )
            return

        if eng.state == CORRECT:
            draw_centered(tft, t("rf_yes"), 30, theme.GREEN, w, scale=2)
            # Show what the correct answer was
            stim_color = self._btn_565[eng.stimulus_button]
            block = min(40, h // 4)
            tft.fill_rect(
                (w - block) // 2, h // 2 - block // 2, block, block, stim_color
            )
            draw_centered(
                tft,
                t("rf_streak", eng.streak),
                h - 30,
                theme.CYAN,
                w,
            )
            return

        if eng.state == WRONG:
            draw_centered(tft, t("rf_try_again"), 30, theme.RED, w, scale=2)
            # Show what the correct color was
            if eng.correct_button >= 0:
                correct_color = self._btn_565[eng.correct_button]
                block = min(40, h // 4)
                tft.fill_rect(
                    (w - block) // 2, h // 2 - block // 2, block, block, correct_color
                )
                draw_centered(
                    tft,
                    t(_COLOR_KEYS[eng.correct_button]),
                    h // 2 + block // 2 + 8,
                    theme.WHITE,
                    w,
                )
            return

    def _draw_rule_icon(self, tft, theme, cx, cy, rule, color):
        """Draw a large procedural rule pictogram centered at (cx, cy)."""
        r = 30
        if rule == RULE_MATCH:
            # Filled circle via horizontal spans (x^2 + y^2 <= r^2)
            r_sq = r * r
            for dy in range(-r, r + 1):
                # half-width at this row: floor(sqrt(r^2 - dy^2))
                dx_sq = r_sq - dy * dy
                # integer sqrt via Newton's method (3 iterations suffice for r<=30)
                dx = r
                dx = (dx + dx_sq // dx) >> 1
                dx = (dx + dx_sq // dx) >> 1
                dx = (dx + dx_sq // dx) >> 1
                tft.fill_rect(cx - dx, cy + dy, dx * 2, 1, color)
        else:
            # X cross for "opposite" — two thick diagonal bars
            thick = 6
            for i in range(r * 2):
                x = cx - r + i
                y1 = cy - r + i
                y2 = cy + r - i
                tft.fill_rect(x, y1, 1, thick, color)
                tft.fill_rect(x, y2 - thick, 1, thick, color)
