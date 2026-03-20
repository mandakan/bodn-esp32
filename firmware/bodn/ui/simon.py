# bodn/ui/simon.py — Pattern Copy (Simon) game screen

from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.widgets import draw_centered, draw_button_grid
from bodn.ui.pause import PauseMenu
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
from bodn.patterns import N_LEDS
from bodn.ui.catface import NEUTRAL, CURIOUS, HAPPY

NAV = config.ENC_NAV

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

    Buttons 0–5 are the play buttons (6 colors).
    Hold nav encoder button to open the pause menu.
    """

    def __init__(self, np, overlay, secondary_screen=None, on_exit=None):
        self._np = np
        self._overlay = overlay
        self._secondary = secondary_screen
        self._on_exit = on_exit
        self._engine = SimonEngine()
        self._manager = None
        self._pause = PauseMenu()
        self._prev_state = None
        self._prev_active_btn = -1
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
        # Pause menu handles hold-to-open and menu navigation
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

        # Active button advances during SHOWING — only the dot row changes,
        # so use a partial push instead of a full redraw.
        active_btn = self._engine.active_button
        if active_btn != self._prev_active_btn:
            self._prev_active_btn = active_btn
            self._leds_dirty = True
            if state == SHOWING and not self._dirty and self._manager:
                self._push_dot_row()
            else:
                self._dirty = True
        # Button press feedback
        if btn >= 0:
            self._dirty = True
            self._leds_dirty = True

        # Write LEDs only when state changes (static patterns, no animation)
        if self._leds_dirty:
            self._leds_dirty = False
            brightness = min(255, max(10, inp.enc_pos[config.ENC_A] * 255 // 20))
            leds = self._engine.make_static_leds(brightness)

            ses_state = self._overlay.session_mgr.state
            leds = self._overlay.static_led_override(ses_state, leds, brightness)

            for i in range(N_LEDS):
                self._np[i] = leds[i]
            self._np.write()

    def _push_dot_row(self):
        """Partial push of just the sequence dot row during SHOWING.

        Called from update() when active_button advances and the rest of
        the screen hasn't changed. Pushes only the dot row rectangle
        (~12 KB for landscape) instead of the full framebuffer (~150 KB).
        """
        tft = self._manager.tft
        theme = self._manager.theme
        eng = self._engine
        landscape = theme.width > theme.height
        round_num = eng.sequence_length

        if landscape:
            dot_y = 40
            dot_size = min(20, (theme.width - 40) // max(1, round_num) - 4)
            step = dot_size + 4
            total_w = round_num * step - 4
        else:
            dot_y = 20
            dot_size = min(14, (theme.width - 16) // max(1, round_num) - 2)
            step = dot_size + 2
            total_w = round_num * step - 2

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
                self._render_game(tft, theme, frame)
            self._pause.render(tft, theme, frame)
            return

        if self._dirty:
            self._dirty = False
            tft.fill(theme.BLACK)
            self._render_game(tft, theme, frame)

        # Hold-to-pause progress bar (always called so PauseMenu can clear its dirty flag)
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
            draw_centered(tft, "PATTERN COPY", 20, theme.CYAN, w, scale=2)
            draw_centered(tft, "Watch & repeat!", h // 2 - 8, theme.WHITE, w)
            draw_centered(tft, "Press any button", h // 2 + 16, theme.MUTED, w)
            if eng.high_score > 0:
                draw_centered(
                    tft,
                    "Best: {}".format(eng.high_score),
                    h - 30,
                    theme.YELLOW,
                    w,
                )
            return

        if eng.state == GAME_OVER:
            draw_centered(tft, "GREAT JOB!", 30, theme.YELLOW, w, scale=2)
            draw_centered(
                tft,
                "Score: {}".format(eng.score),
                h // 2 - 8,
                theme.WHITE,
                w,
                scale=2,
            )
            if eng.high_score > 0:
                draw_centered(
                    tft, "Best: {}".format(eng.high_score), h // 2 + 24, theme.CYAN, w
                )
            draw_centered(tft, "Press to play again", h - 30, theme.MUTED, w)
            return

        # --- Active game states ---

        # Top: state label + round info
        round_num = eng.sequence_length
        if eng.state == SHOWING:
            draw_centered(tft, "WATCH!", 8, theme.YELLOW, w, scale=2)
        elif eng.state == WAITING:
            draw_centered(tft, "YOUR TURN!", 8, theme.GREEN, w, scale=2)
        elif eng.state == WIN:
            draw_centered(tft, "YES!", 8, theme.YELLOW, w, scale=2)
        elif eng.state == FAIL:
            draw_centered(tft, "TRY AGAIN", 8, theme.RED, w, scale=2)

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

        # Button grid — bottom portion
        btn_y = h // 2 + 20
        # Show only 6 buttons (2 rows × 3 cols)
        btn_names = theme.BTN_NAMES[:NUM_BUTTONS]
        btn_held = held[:NUM_BUTTONS]
        cell_w = w // 3 - 8
        cell_h = (h - btn_y - 24) // 2
        btn_x0 = (w - 3 * cell_w) // 2
        draw_button_grid(
            tft,
            theme,
            btn_names,
            btn_held,
            cols=3,
            x0=btn_x0,
            y0=btn_y,
            cell_w=cell_w,
            cell_h=cell_h,
        )

        # Bottom bar: score
        tft.text("Round {}".format(round_num), 8, h - 14, theme.MUTED)
        if eng.high_score > 0:
            hs_text = "Best:{}".format(eng.high_score)
            tft.text(hs_text, w - len(hs_text) * 8 - 8, h - 14, theme.YELLOW)

    def _render_portrait(self, tft, theme, frame):
        eng = self._engine
        w = theme.width
        h = theme.height
        held = self._manager.inp.btn_held if self._manager else [False] * 8

        if eng.state == READY:
            draw_centered(tft, "PATTERN", 20, theme.CYAN, w, scale=2)
            draw_centered(tft, "COPY", 40, theme.CYAN, w, scale=2)
            draw_centered(tft, "Watch &", h // 2 - 16, theme.WHITE, w)
            draw_centered(tft, "repeat!", h // 2, theme.WHITE, w)
            draw_centered(tft, "Press to start", h - 30, theme.MUTED, w)
            return

        if eng.state == GAME_OVER:
            draw_centered(tft, "GREAT!", 20, theme.YELLOW, w, scale=2)
            draw_centered(
                tft, "Score:{}".format(eng.score), h // 2, theme.WHITE, w, scale=2
            )
            draw_centered(tft, "Press again", h - 20, theme.MUTED, w)
            return

        # State label
        if eng.state == SHOWING:
            draw_centered(tft, "WATCH!", 4, theme.YELLOW, w)
        elif eng.state == WAITING:
            draw_centered(tft, "YOUR TURN!", 4, theme.GREEN, w)
        elif eng.state == WIN:
            draw_centered(tft, "YES!", 4, theme.YELLOW, w)
        elif eng.state == FAIL:
            draw_centered(tft, "TRY AGAIN", 4, theme.RED, w)

        # Sequence dots
        round_num = eng.sequence_length
        dot_y = 20
        dot_size = min(14, (w - 16) // max(1, round_num) - 2)
        total_w = round_num * (dot_size + 2) - 2
        dot_x0 = (w - total_w) // 2

        for i in range(round_num):
            x = dot_x0 + i * (dot_size + 2)
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
            else:
                tft.fill_rect(x, dot_y, dot_size, dot_size, color)

        # Button grid — 2 rows × 3 cols
        btn_y = h * 3 // 5
        btn_names = theme.BTN_NAMES[:NUM_BUTTONS]
        btn_held = held[:NUM_BUTTONS]
        cell_w = w // 3 - 2
        cell_h = (h - btn_y - 16) // 2
        btn_x0 = (w - 3 * cell_w) // 2
        draw_button_grid(
            tft,
            theme,
            btn_names,
            btn_held,
            cols=3,
            x0=btn_x0,
            y0=btn_y,
            cell_w=cell_w,
            cell_h=cell_h,
        )

        # Score
        tft.text("R{}".format(round_num), 4, h - 12, theme.MUTED)
