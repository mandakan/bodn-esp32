# bodn/ui/rulefollow.py — Rule Follow game screen

from micropython import const
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered, draw_button_grid
from bodn.ui.pause import PauseMenu
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
from bodn.patterns import (
    N_LEDS,
    zone_fill,
    zone_pulse,
    zone_chase,
    zone_clear,
    ZONE_LID_RING,
)
from bodn.ui.catface import NEUTRAL, CURIOUS, HAPPY

NAV = const(0)  # config.ENC_NAV

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

    def __init__(self, np, overlay, audio=None, secondary_screen=None, on_exit=None):
        self._np = np
        self._overlay = overlay
        self._audio = audio
        self._secondary = secondary_screen
        self._on_exit = on_exit
        self._engine = RuleFollowEngine()
        self._manager = None
        self._pause = PauseMenu()
        self._prev_state = None
        self._dirty = True
        self._leds_dirty = True

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._engine.reset()
        self._dirty = True

    def exit(self):
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
        if self._pause.is_open or self._pause.is_holding:
            return

        # Find first just-pressed button
        btn = inp.first_btn_pressed()
        prev_state = self._engine.state
        self._engine.update(btn, frame)

        # Detect state changes
        state = self._engine.state
        if state != self._prev_state:
            self._prev_state = state
            self._dirty = True
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

        # Write LEDs only when state changes
        if self._leds_dirty:
            self._leds_dirty = False
            brightness = min(255, max(10, inp.enc_pos[config.ENC_A] * 255 // 20))
            lid_bright = min(brightness, config.NEOPIXEL_LID_BRIGHTNESS)

            # Sticks: game feedback
            leds = self._engine.make_static_leds(brightness)

            # Lid ring: context-dependent
            eng = self._engine
            if eng.state == CORRECT:
                zone_pulse(ZONE_LID_RING, frame, 3, (0, 255, 0), lid_bright)
            elif eng.state == WRONG:
                zone_pulse(ZONE_LID_RING, frame, 2, (255, 0, 0), lid_bright)
            elif eng.state == RULE_SWITCH:
                zone_chase(
                    ZONE_LID_RING, frame, 4, RULE_COLORS[eng.current_rule], lid_bright
                )
            elif eng.state in (SHOW_RULE, STIMULUS):
                zone_fill(ZONE_LID_RING, eng.rule_color, lid_bright)
            else:
                zone_clear(ZONE_LID_RING)

            ses_state = self._overlay.session_mgr.state
            leds = self._overlay.static_led_override(ses_state, leds, brightness)

            np = self._np
            n = N_LEDS
            for i in range(n):
                np[i] = leds[i]
            np.write()

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
            audio.tone(_CORRECT_TONE, 150, channel=1)
        elif new_state == WRONG:
            audio.tone(_WRONG_TONE, 250, channel=1)
        elif new_state == RULE_SWITCH:
            audio.tone(_SWITCH_TONE, 300, channel=1)

    def render(self, tft, theme, frame):
        if self._pause.is_open:
            if self._dirty:
                self._dirty = False
                tft.fill(theme.BLACK)
                self._render_game(tft, theme, frame)
            self._pause.render(tft, theme, frame)
            return

        if self._dirty:
            self._dirty = False
            tft.fill(theme.BLACK)
            self._render_game(tft, theme, frame)

        self._pause.render(tft, theme, frame)

    def _render_game(self, tft, theme, frame):
        landscape = theme.width > theme.height
        if landscape:
            self._render_landscape(tft, theme, frame)
        else:
            self._render_portrait(tft, theme, frame)

    def _render_landscape(self, tft, theme, frame):
        eng = self._engine
        w = theme.width
        h = theme.height
        held = self._manager.inp.btn_held if self._manager else [False] * 8

        if eng.state == READY:
            draw_centered(tft, "RULE FOLLOW", 20, theme.CYAN, w, scale=2)
            draw_centered(tft, "Watch the rule,", h // 2 - 16, theme.WHITE, w)
            draw_centered(tft, "press the color!", h // 2 + 4, theme.WHITE, w)
            draw_centered(tft, "Press any button", h - 30, theme.MUTED, w)
            return

        if eng.state == GAME_OVER:
            draw_centered(tft, "GREAT JOB!", 20, theme.YELLOW, w, scale=2)
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
                    "Best streak: {}".format(eng.best_streak),
                    h // 2 + 20,
                    theme.CYAN,
                    w,
                )
            draw_centered(tft, "Press to play again", h - 30, theme.MUTED, w)
            return

        # --- Active game states ---
        rule_565 = theme.rgb(*RULE_COLORS[eng.current_rule])

        if eng.state == SHOW_RULE:
            rule_name = "MATCH!" if eng.current_rule == RULE_MATCH else "OPPOSITE!"
            draw_centered(tft, rule_name, 20, rule_565, w, scale=2)
            # Draw rule pictogram: circle for match, X for opposite
            cx = w // 2
            cy = h // 2
            self._draw_rule_icon(tft, theme, cx, cy, eng.current_rule, rule_565)
            return

        if eng.state == RULE_SWITCH:
            draw_centered(tft, "NEW RULE!", 20, theme.YELLOW, w, scale=2)
            rule_name = "MATCH!" if eng.current_rule == RULE_MATCH else "OPPOSITE!"
            draw_centered(tft, rule_name, h // 2 - 8, rule_565, w, scale=2)
            return

        if eng.state == STIMULUS:
            # Rule reminder at top
            rule_label = "Match" if eng.current_rule == RULE_MATCH else "Opposite"
            draw_centered(tft, rule_label, 4, rule_565, w)

            # Big stimulus color block
            stim_color = theme.rgb(*BTN_COLORS[eng.stimulus_button])
            block_size = min(w // 3, h // 2 - 20)
            bx = (w - block_size) // 2
            by = 24
            tft.fill_rect(bx, by, block_size, block_size, stim_color)

            # Button grid below
            btn_y = by + block_size + 12
            btn_names = theme.BTN_NAMES[:NUM_BUTTONS]
            btn_held = held[:NUM_BUTTONS]
            cell_w = w // 4 - 4
            cell_h = h - btn_y - 20
            btn_x0 = (w - 4 * cell_w) // 2
            draw_button_grid(
                tft,
                theme,
                btn_names,
                btn_held,
                cols=4,
                x0=btn_x0,
                y0=btn_y,
                cell_w=cell_w,
                cell_h=cell_h,
            )

            # Score bar
            tft.text(
                "{}/{}".format(eng.score, eng.total),
                4,
                h - 14,
                theme.MUTED,
            )
            return

        if eng.state == CORRECT:
            draw_centered(tft, "YES!", 30, theme.GREEN, w, scale=2)
            # Show what the correct answer was
            stim_color = theme.rgb(*BTN_COLORS[eng.stimulus_button])
            block = min(40, h // 4)
            tft.fill_rect(
                (w - block) // 2, h // 2 - block // 2, block, block, stim_color
            )
            draw_centered(
                tft,
                "Streak: {}".format(eng.streak),
                h - 30,
                theme.CYAN,
                w,
            )
            return

        if eng.state == WRONG:
            draw_centered(tft, "TRY AGAIN", 30, theme.RED, w, scale=2)
            # Show what the correct color was
            if eng.correct_button >= 0:
                correct_color = theme.rgb(*BTN_COLORS[eng.correct_button])
                block = min(40, h // 4)
                tft.fill_rect(
                    (w - block) // 2, h // 2 - block // 2, block, block, correct_color
                )
                draw_centered(
                    tft,
                    theme.BTN_NAMES[eng.correct_button],
                    h // 2 + block // 2 + 8,
                    theme.WHITE,
                    w,
                )
            return

    def _render_portrait(self, tft, theme, frame):
        eng = self._engine
        w = theme.width
        h = theme.height
        held = self._manager.inp.btn_held if self._manager else [False] * 8

        if eng.state == READY:
            draw_centered(tft, "RULE", 20, theme.CYAN, w, scale=2)
            draw_centered(tft, "FOLLOW", 40, theme.CYAN, w, scale=2)
            draw_centered(tft, "Watch &", h // 2 - 16, theme.WHITE, w)
            draw_centered(tft, "press!", h // 2, theme.WHITE, w)
            draw_centered(tft, "Press to start", h - 20, theme.MUTED, w)
            return

        if eng.state == GAME_OVER:
            draw_centered(tft, "GREAT!", 20, theme.YELLOW, w, scale=2)
            draw_centered(
                tft,
                "{}/{}".format(eng.score, eng.total),
                h // 2 - 8,
                theme.WHITE,
                w,
                scale=2,
            )
            if eng.best_streak > 0:
                draw_centered(
                    tft,
                    "Streak:{}".format(eng.best_streak),
                    h // 2 + 20,
                    theme.CYAN,
                    w,
                )
            draw_centered(tft, "Press again", h - 16, theme.MUTED, w)
            return

        rule_565 = theme.rgb(*RULE_COLORS[eng.current_rule])

        if eng.state == SHOW_RULE:
            rule_name = "MATCH!" if eng.current_rule == RULE_MATCH else "OPPOSITE!"
            draw_centered(tft, rule_name, 8, rule_565, w, scale=2)
            cx = w // 2
            cy = h // 2
            self._draw_rule_icon(tft, theme, cx, cy, eng.current_rule, rule_565)
            return

        if eng.state == RULE_SWITCH:
            draw_centered(tft, "NEW", 20, theme.YELLOW, w, scale=2)
            draw_centered(tft, "RULE!", 44, theme.YELLOW, w, scale=2)
            rule_name = "MATCH!" if eng.current_rule == RULE_MATCH else "OPPOSITE!"
            draw_centered(tft, rule_name, h // 2, rule_565, w)
            return

        if eng.state == STIMULUS:
            rule_label = "Match" if eng.current_rule == RULE_MATCH else "Opposite"
            draw_centered(tft, rule_label, 2, rule_565, w)

            stim_color = theme.rgb(*BTN_COLORS[eng.stimulus_button])
            block_size = min(w - 20, h // 3)
            bx = (w - block_size) // 2
            by = 18
            tft.fill_rect(bx, by, block_size, block_size, stim_color)

            btn_y = by + block_size + 8
            btn_names = theme.BTN_NAMES[:NUM_BUTTONS]
            btn_held = held[:NUM_BUTTONS]
            cell_w = w // 2 - 2
            cell_h = (h - btn_y - 16) // 2
            btn_x0 = (w - 2 * cell_w) // 2
            draw_button_grid(
                tft,
                theme,
                btn_names,
                btn_held,
                cols=2,
                x0=btn_x0,
                y0=btn_y,
                cell_w=cell_w,
                cell_h=cell_h,
            )

            tft.text("{}/{}".format(eng.score, eng.total), 2, h - 12, theme.MUTED)
            return

        if eng.state == CORRECT:
            draw_centered(tft, "YES!", 20, theme.GREEN, w, scale=2)
            return

        if eng.state == WRONG:
            draw_centered(tft, "TRY AGAIN", 20, theme.RED, w)
            if eng.correct_button >= 0:
                correct_color = theme.rgb(*BTN_COLORS[eng.correct_button])
                block = min(30, w // 3)
                tft.fill_rect(
                    (w - block) // 2, h // 2 - block // 2, block, block, correct_color
                )
            return

    def _draw_rule_icon(self, tft, theme, cx, cy, rule, color):
        """Draw a large procedural rule pictogram centered at (cx, cy)."""
        size = 30
        if rule == RULE_MATCH:
            # Filled circle (approximated with concentric rects)
            for r in range(size, 0, -2):
                tft.fill_rect(cx - r, cy - r, r * 2, r * 2, color)
        else:
            # X cross for "opposite"
            thick = 6
            for i in range(size * 2):
                x = cx - size + i
                y1 = cy - size + i
                y2 = cy + size - i
                tft.fill_rect(x, y1, 1, thick, color)
                tft.fill_rect(x, y2 - thick, 1, thick, color)
