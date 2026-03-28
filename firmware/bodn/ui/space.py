# bodn/ui/space.py — Spaceship Cockpit game screen
#
# Open-ended pretend play: every input does something ship-related.
# Ship AI "Stellar" narrates scenarios via TTS.  No win/lose state —
# the ship keeps flying regardless.

from micropython import const
from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.input import BrightnessControl
from bodn.ui.widgets import draw_centered
from bodn.ui.pause import PauseMenu
from bodn.i18n import t
from bodn.space_rules import (
    SpaceEngine,
    CRUISING,
    ANNOUNCE,
    ACTIVE,
    SUCCESS,
    HINT,
    SC_ASTEROID,
    SC_COURSE,
    SC_SHIELD,
    SC_ENGINE,
    SC_LANDING,
    ARC_COLORS,
)
from bodn.patterns import (
    N_LEDS,
    zone_pulse,
    zone_rainbow,
    zone_chase,
    zone_clear,
    ZONE_LID_RING,
)
from bodn.ui.catface import NEUTRAL, CURIOUS, HAPPY, SURPRISED

NAV = const(0)  # config.ENC_NAV

# Scenario type → TTS key (played on "announce" event)
_SC_TTS = [
    "space_sc_asteroid",
    "space_sc_course",
    "space_sc_shield",
    "space_sc_engine",
    "space_sc_landing",
]

# Scenario type → short display label key
_SC_LABEL = [
    "space_sc_asteroid_short",
    "space_sc_course_short",
    "space_sc_shield_short",
    "space_sc_engine_short",
    "space_sc_landing_short",
]

# Scenario type → instruction key
_SC_INSTR = [
    "space_instr_asteroid",
    "space_instr_course",
    "space_instr_shield",
    "space_instr_engine",
    "space_instr_landing",
]

# Cat face emotions per state
_STATE_EMOTIONS = {
    CRUISING: NEUTRAL,
    ANNOUNCE: SURPRISED,
    ACTIVE: CURIOUS,
    SUCCESS: HAPPY,
    HINT: CURIOUS,
}


class SpaceScreen(Screen):
    """Spaceship Cockpit — open-ended pretend play with random scenarios.

    Encoder A (right): throttle (engine speed).
    Encoder B / Nav (left): steering (course heading).
    Buttons 0–7: ship systems (sounds + LED feedback).
    Toggle 0: shields on/off — spoken confirmation on every toggle.
    Toggle 1: stealth mode — spoken confirmation on every toggle.
    Arcade 0–4: emergency action stations; target LED pulses during SC_LANDING.
    Hold nav encoder button to pause.
    """

    def __init__(
        self,
        np,
        overlay,
        audio=None,
        arcade=None,
        settings=None,
        secondary_screen=None,
        on_exit=None,
    ):
        self._np = np
        self._overlay = overlay
        self._audio = audio
        self._arcade = arcade
        self._secondary = secondary_screen
        self._on_exit = on_exit
        self._engine = SpaceEngine()
        self._brightness = BrightnessControl(settings=settings)
        self._manager = None
        self._pause = PauseMenu(settings=settings)
        self._prev_state = None
        self._dirty = True
        self._full_clear = True
        self._leds_dirty = True
        self._prev_throttle = 128
        self._prev_steering = 0
        self._active_state_frame = 0  # frame when ACTIVE began (for countdown)
        self._prev_sw0 = None  # None = not yet initialised
        self._prev_sw1 = None

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._engine.reset()
        self._brightness.reset()
        self._dirty = True
        self._full_clear = True
        self._leds_dirty = True
        self._prev_state = None
        self._prev_sw0 = None  # reset so first-frame state is read without TTS
        self._prev_sw1 = None
        if self._arcade:
            self._arcade.all_off()
        # Welcome message
        if self._audio:
            try:
                from bodn import tts

                tts.say("space_welcome", self._audio)
            except Exception:
                pass

    def exit(self):
        if self._arcade:
            self._arcade.all_off()
        if self._on_exit:
            self._on_exit()

    def needs_redraw(self):
        # Redraw every frame during ACTIVE/ANNOUNCE for countdown + animations
        if self._engine.state in (ACTIVE, ANNOUNCE):
            return True
        return self._dirty or self._pause.needs_render

    def update(self, inp, frame):
        # Pause menu: hold nav button to open
        result = self._pause.update(inp, frame)
        if result == "quit" and self._manager:
            self._manager.pop()
            return
        elif result == "resume":
            self._dirty = True
            self._full_clear = True
        if self._pause.is_open or self._pause.is_holding:
            return

        btn = inp.first_btn_pressed()
        arc = inp.first_arc_pressed()
        enc_a = inp.enc_delta[config.ENC_A]
        enc_b = inp.enc_delta[config.ENC_B]
        sw0 = inp.sw[0] if len(inp.sw) > 0 else False
        sw1 = inp.sw[1] if len(inp.sw) > 1 else False

        event = self._engine.update(btn, arc, enc_a, enc_b, sw0, sw1, frame)

        # Button ambient sounds (always, regardless of scenario)
        if btn >= 0 and self._audio:
            self._play_btn_tone(btn)
            self._leds_dirty = True
            self._dirty = True

        if arc >= 0 and self._audio:
            self._play_arc_tone(arc)
            self._leds_dirty = True

        # Handle events
        if event == "announce":
            self._dirty = True
            self._full_clear = True
            self._leds_dirty = True
            sc = self._engine.scenario_type
            if self._audio and 0 <= sc < len(_SC_TTS):
                try:
                    from bodn import tts

                    if not tts.say(_SC_TTS[sc], self._audio):
                        # Fallback: alarm tone
                        self._audio.tone(440, 300, "square", channel="sfx")
                except Exception:
                    pass
            if self._secondary:
                self._secondary.set_emotion(SURPRISED)

        elif event == "success":
            self._dirty = True
            self._full_clear = True
            self._leds_dirty = True
            if self._audio:
                try:
                    from bodn import tts

                    if not tts.say("space_success", self._audio):
                        self._audio.play_sound("win")
                except Exception:
                    pass
            if self._secondary:
                self._secondary.set_emotion(HAPPY)

        elif event == "hint":
            self._dirty = True
            self._full_clear = True
            self._leds_dirty = True
            if self._audio:
                try:
                    from bodn import tts

                    if not tts.say("space_hint", self._audio):
                        self._audio.tone(330, 200, "sine", channel="ui")
                except Exception:
                    pass

        elif event == "resolve":
            self._dirty = True
            self._full_clear = True
            self._leds_dirty = True
            if self._secondary:
                self._secondary.set_emotion(NEUTRAL)

        # State change → update cat face + mark dirty
        state = self._engine.state
        if state != self._prev_state:
            self._prev_state = state
            self._dirty = True
            self._full_clear = True
            self._leds_dirty = True
            if state == ACTIVE:
                self._active_state_frame = frame
            if self._secondary:
                self._secondary.set_emotion(_STATE_EMOTIONS.get(state, NEUTRAL))

        # Throttle/steering changes → redraw instruments
        if (
            abs(self._engine.throttle - self._prev_throttle) >= 4
            or abs(self._engine.steering - self._prev_steering) >= 4
        ):
            self._prev_throttle = self._engine.throttle
            self._prev_steering = self._engine.steering
            self._dirty = True
            self._leds_dirty = True

        # Toggle switches: detect edges, play spoken confirmation
        if self._prev_sw0 is None:
            self._prev_sw0 = sw0  # initialise silently on first frame
        elif sw0 != self._prev_sw0:
            self._prev_sw0 = sw0
            self._speak_toggle("space_shield_on" if sw0 else "space_shield_off", sw0)
            self._dirty = True

        if self._prev_sw1 is None:
            self._prev_sw1 = sw1
        elif sw1 != self._prev_sw1:
            self._prev_sw1 = sw1
            self._speak_toggle("space_stealth_on" if sw1 else "space_stealth_off", sw1)
            self._dirty = True

        # Arcade LEDs — called every frame (animation driven by frame counter)
        self._update_arcade_leds(state, frame)

        # Brightness from encoder A
        prev_bri = self._brightness.value
        self._brightness.update(
            inp.enc_delta[config.ENC_A], inp.enc_velocity[config.ENC_A]
        )
        if self._brightness.value != prev_bri:
            self._leds_dirty = True

        # Write LEDs
        if self._leds_dirty:
            self._leds_dirty = False
            self._write_leds(state, frame)

    def _play_btn_tone(self, btn):
        """Play a unique tone for each button (ship system feedback)."""
        # Map buttons 0–7 to pentatonic-ish frequencies
        freqs = [261, 294, 329, 392, 440, 523, 587, 659]
        freq = freqs[btn % len(freqs)]
        self._audio.tone(freq, 150, "sine", channel="sfx")

    def _play_arc_tone(self, arc):
        """Big satisfying tone for arcade buttons."""
        freqs = [220, 277, 330, 415, 523]
        freq = freqs[arc % len(freqs)]
        self._audio.tone(freq, 250, "square", channel="sfx")

    def _speak_toggle(self, tts_key, state_on):
        """Speak a toggle confirmation; fall back to a short tone."""
        if not self._audio:
            return
        try:
            from bodn import tts

            if not tts.say(tts_key, self._audio):
                # Fallback: rising tone for ON, falling for OFF
                self._audio.tone(880 if state_on else 440, 120, "sine", channel="ui")
        except Exception:
            pass

    def _update_arcade_leds(self, state, frame):
        """Drive arcade button LEDs based on game state.

        Called every frame from update() so animations stay smooth.
        All LED writes are no-ops when self._arcade is None.
        """
        arc = self._arcade
        if arc is None:
            return

        if state == SUCCESS:
            # All buttons lit solid briefly
            arc.set_all_leds(220)

        elif state in (ACTIVE, HINT):
            sc = self._engine.scenario_type
            if sc == SC_LANDING:
                tgt = self._engine.target_arc_idx
                for i in range(5):
                    if i == tgt:
                        arc.pulse_led(i, frame, speed=5)  # fast bright pulse
                    else:
                        arc.set_led(i, 18)  # dim background
            else:
                # Slow uniform heartbeat — buttons are "on standby"
                for i in range(5):
                    arc.pulse_led(i, frame, speed=1)

        elif state == ANNOUNCE:
            # Fast unified flash — alert!
            for i in range(5):
                arc.pulse_led(i, frame, speed=4)

        elif state == CRUISING:
            # Gentle slow heartbeat — ship is alive
            for i in range(5):
                arc.pulse_led(i, frame, speed=1)

        else:
            arc.set_all_leds(0)

    def _write_leds(self, state, frame):
        """Update NeoPixel sticks and lid ring."""
        brightness = self._brightness.value
        lid_bright = min(brightness, config.NEOPIXEL_LID_BRIGHTNESS)

        leds = self._engine.make_static_leds(brightness)

        # Lid ring: state-appropriate effect
        if state == SUCCESS:
            zone_rainbow(ZONE_LID_RING, frame, 3, 0, lid_bright)
        elif state in (ACTIVE, HINT):
            sc = self._engine.scenario_type
            if sc == SC_ASTEROID:
                zone_chase(ZONE_LID_RING, frame, 3, (255, 80, 0), lid_bright)
            elif sc == SC_SHIELD:
                zone_pulse(ZONE_LID_RING, frame, 4, (255, 0, 0), lid_bright)
            elif sc == SC_ENGINE:
                zone_pulse(ZONE_LID_RING, frame, 2, (255, 140, 0), lid_bright)
            elif sc == SC_COURSE:
                col = self._engine.target_color or (255, 200, 0)
                zone_pulse(ZONE_LID_RING, frame, 2, col, lid_bright)
            elif sc == SC_LANDING:
                col = self._engine.target_color or (0, 200, 60)
                zone_pulse(ZONE_LID_RING, frame, 2, col, lid_bright)
            else:
                zone_clear(ZONE_LID_RING)
        elif state == ANNOUNCE:
            zone_pulse(ZONE_LID_RING, frame, 3, (200, 50, 255), lid_bright)
        else:
            # CRUISING: slow blue sweep
            zone_chase(ZONE_LID_RING, frame, 1, (0, 40, 160), lid_bright // 2)

        ses_state = self._overlay.session_mgr.state
        leds = self._overlay.static_led_override(ses_state, leds, brightness)

        np = self._np
        for i in range(N_LEDS):
            np[i] = leds[i]
        np.write()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, tft, theme, frame):
        if self._pause.is_open:
            if self._dirty:
                self._dirty = False
                self._full_clear = False
                tft.fill(theme.BLACK)
                self._render_game(tft, theme, frame)
            self._pause.render(tft, theme, frame)
            return

        if self._dirty or self._engine.state in (ACTIVE, ANNOUNCE):
            self._dirty = False
            if self._full_clear:
                self._full_clear = False
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
        w = theme.width  # 320
        h = theme.height  # 240

        state = eng.state

        # Header bar (always)
        tft.fill_rect(0, 0, w, 18, theme.BLACK)
        title = t("space_title")
        tft.text(title, 8, 4, theme.CYAN)
        # Difficulty stars
        stars = "* " * eng.difficulty
        tft.text(stars, w - len(stars) * 8 - 8, 4, theme.YELLOW)

        if state == CRUISING:
            self._render_cruising(tft, theme, frame, w, h)
        elif state == ANNOUNCE:
            self._render_announce(tft, theme, frame, w, h)
        elif state in (ACTIVE, HINT):
            self._render_active(tft, theme, frame, w, h)
        elif state == SUCCESS:
            self._render_success(tft, theme, frame, w, h)

        # Bottom instrument bar (always)
        self._render_instruments(tft, theme, w, h, eng)

    def _render_cruising(self, tft, theme, frame, w, h):
        """Starfield + 'all clear' display."""
        # Simple deterministic starfield
        tft.fill_rect(0, 20, w, h - 40, theme.BLACK)
        for i in range(24):
            sx = (i * 53 + frame // 3) % w
            sy = (i * 37 + i * 11) % (h - 50) + 22
            tft.pixel(sx, sy, theme.WHITE if i % 3 != 0 else theme.MUTED)

        draw_centered(tft, t("space_cruising_label"), h // 2 - 8, theme.CYAN, w)
        # Shield indicator
        sw_color = theme.GREEN if self._engine.shields_on else theme.MUTED
        tft.text(t("space_shields"), 8, h // 2 + 8, sw_color)
        if self._engine.stealth:
            tft.text(t("space_stealth"), w // 2, h // 2 + 8, theme.DIM)

    def _render_announce(self, tft, theme, frame, w, h):
        """Full-screen scenario announcement with pulsing border."""
        sc = self._engine.scenario_type
        tft.fill_rect(0, 20, w, h - 40, theme.BLACK)

        # Pulsing border
        phase = (frame * 6) & 0xFF
        v = phase if phase < 128 else 255 - phase
        border_col = theme.MAGENTA if (v > 64) else theme.CYAN
        tft.rect(2, 22, w - 4, h - 44, border_col)
        tft.rect(3, 23, w - 6, h - 46, border_col)

        label_key = _SC_LABEL[sc] if 0 <= sc < len(_SC_LABEL) else "space_alert"
        draw_centered(tft, t(label_key), h // 2 - 16, theme.YELLOW, w, scale=2)
        draw_centered(tft, t("space_alert"), h // 2 + 8, theme.WHITE, w)

    def _render_active(self, tft, theme, frame, w, h):
        """Scenario active: instruction + countdown bar."""
        eng = self._engine
        sc = eng.scenario_type
        tft.fill_rect(0, 20, w, h - 40, theme.BLACK)

        # Scenario label
        if 0 <= sc < len(_SC_LABEL):
            label = t(_SC_LABEL[sc])
            tft.text(label, 8, 24, theme.YELLOW)

        # Instruction
        if 0 <= sc < len(_SC_INSTR):
            instr = t(_SC_INSTR[sc])
            draw_centered(tft, instr, h // 2 - 16, theme.WHITE, w)

        # For SC_COURSE: show coloured button hint
        if sc == SC_COURSE and eng.target_btn_idx >= 0:
            btn_col = theme.BTN_565[eng.target_btn_idx]
            bw = 40
            bx = (w - bw) // 2
            by = h // 2 + 4
            tft.fill_rect(bx, by, bw, 20, btn_col)

        # For SC_LANDING: show arcade button colour swatch
        if sc == SC_LANDING and eng.target_arc_idx >= 0:
            arc_rgb = ARC_COLORS[eng.target_arc_idx]
            # Convert RGB888 to RGB565
            r5 = (arc_rgb[0] >> 3) & 0x1F
            g6 = (arc_rgb[1] >> 2) & 0x3F
            b5 = (arc_rgb[2] >> 3) & 0x1F
            arc_col = (r5 << 11) | (g6 << 5) | b5
            bw = 40
            bx = (w - bw) // 2
            by = h // 2 + 4
            tft.fill_rect(bx, by, bw, 20, arc_col)

        # For SC_ENGINE: show click progress bar
        if sc == SC_ENGINE:
            prog = eng.engine_progress
            bar_w = w - 40
            bar_x = 20
            bar_y = h // 2 + 8
            tft.rect(bar_x, bar_y, bar_w, 14, theme.MUTED)
            filled = int(prog * (bar_w - 2))
            if filled > 0:
                tft.fill_rect(bar_x + 1, bar_y + 1, filled, 12, theme.YELLOW)

        # Hint state: extra nudge text
        if eng.state == HINT:
            draw_centered(tft, t("space_hint_label"), h // 2 + 28, theme.CYAN, w)

        # Countdown bar (time remaining)
        limit = [240, 180, 150][eng.difficulty - 1]
        elapsed = frame - self._active_state_frame
        remaining = max(0, limit - elapsed)
        prog = remaining / limit
        bar_w = w - 16
        tft.rect(8, h - 36, bar_w, 8, theme.MUTED)
        filled = int(prog * (bar_w - 2))
        if filled > 0:
            col = (
                theme.GREEN
                if prog > 0.5
                else (theme.YELLOW if prog > 0.25 else theme.RED)
            )
            tft.fill_rect(9, h - 35, filled, 6, col)

    def _render_success(self, tft, theme, frame, w, h):
        """Celebration screen."""
        tft.fill_rect(0, 20, w, h - 40, theme.BLACK)
        draw_centered(
            tft, t("space_success_label"), h // 2 - 12, theme.YELLOW, w, scale=2
        )
        draw_centered(tft, t("space_success_sub"), h // 2 + 12, theme.GREEN, w)

    def _render_instruments(self, tft, theme, w, h, eng):
        """Bottom bar: throttle + steering gauges."""
        bar_y = h - 18
        tft.fill_rect(0, bar_y, w, 18, theme.BLACK)

        # Throttle bar (left half)
        tft.text(t("space_throttle_short"), 8, bar_y + 4, theme.MUTED)
        tx = 36
        tbar_w = w // 2 - 44
        tft.rect(tx, bar_y + 3, tbar_w, 10, theme.MUTED)
        filled = int(eng.throttle / 255 * (tbar_w - 2))
        if filled > 0:
            tft.fill_rect(tx + 1, bar_y + 4, filled, 8, theme.CYAN)

        # Steering indicator (right half)
        cx = w * 3 // 4
        steer_w = 60
        sx0 = cx - steer_w // 2
        tft.text(t("space_steer_short"), w // 2 + 4, bar_y + 4, theme.MUTED)
        tft.rect(sx0, bar_y + 3, steer_w, 10, theme.MUTED)
        mid = steer_w // 2
        dot_x = sx0 + mid + int(eng.steering * mid // 128)
        dot_x = max(sx0 + 1, min(sx0 + steer_w - 3, dot_x))
        tft.fill_rect(dot_x, bar_y + 4, 4, 8, theme.GREEN)

    def _render_portrait(self, tft, theme, frame):
        """Portrait layout for secondary/rotated mounting."""
        eng = self._engine
        w = theme.width
        h = theme.height

        tft.fill_rect(0, 0, w, 14, theme.BLACK)
        tft.text(t("space_title_short"), 4, 3, theme.CYAN)

        state = eng.state
        if state == CRUISING:
            draw_centered(tft, t("space_cruising_label"), h // 2 - 8, theme.CYAN, w)
        elif state == ANNOUNCE:
            sc = eng.scenario_type
            if 0 <= sc < len(_SC_LABEL):
                draw_centered(tft, t(_SC_LABEL[sc]), h // 2, theme.YELLOW, w)
        elif state in (ACTIVE, HINT):
            sc = eng.scenario_type
            if 0 <= sc < len(_SC_INSTR):
                draw_centered(tft, t(_SC_INSTR[sc]), h // 2 - 8, theme.WHITE, w)
        elif state == SUCCESS:
            draw_centered(tft, t("space_success_label"), h // 2, theme.YELLOW, w)

        # Mini throttle bar at bottom
        by = h - 14
        tft.fill_rect(0, by, w, 14, theme.BLACK)
        filled = int(eng.throttle / 255 * (w - 2))
        if filled > 0:
            tft.fill_rect(1, by + 3, filled, 8, theme.CYAN)
        tft.rect(0, by + 2, w, 10, theme.MUTED)
