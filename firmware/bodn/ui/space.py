# bodn/ui/space.py — Spaceship Cockpit game screen
#
# Open-ended pretend play: every input does something ship-related.
# Ship AI "Stellar" narrates scenarios via TTS.  No win/lose state —
# the ship keeps flying regardless.


import os

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
from bodn.ui.android import NEUTRAL, CURIOUS, HAPPY, SURPRISED

NAV = const(0)  # config.ENC_NAV

# ─────────────────────────────────────────────────────────────────────────────
# AUDIO — WAV override system
# ─────────────────────────────────────────────────────────────────────────────
#
# Every sound has a procedural fallback (tone) that plays when no WAV file is
# present.  To add real sounds, drop WAV files on the SD card — no code changes
# needed.  Paths are resolved once at mode enter (see _resolve_sound_paths) so
# there is zero per-press overhead during play.
#
# Directory: /sd/sounds/space/
#
# Regular buttons (0–7) — named by ship system (index = list position):
#   thruster.wav  shields.wav  scanner.wav  comms.wav
#   repair.wav    cargo.wav    lights.wav   horn.wav
#
# Arcade buttons (0–4) — named by role (see space_rules.ARC_* constants):
#   land.wav  course.wav  engines.wav  repair.wav  distress.wav
#
# Engine drone (looped, one per throttle zone — plays on music channel):
#   low_engine_loop.wav  engine_loop.wav  high_engine_loop.wav
#
# Alarm loops (looped, replace engine drone on music channel during scenarios):
#   soft_alarm_loop.wav    — low danger (course, landing)
#   medium_alarm_loop.wav  — medium danger (shield, engine)
#   alarm_loop.wav         — high danger (asteroid)
#
# TTS announcements live separately — see assets/audio/tts.json ("storage":"sd").
# To add a new scenario sound: add its i18n key there and run tools/generate_tts.py.
# ─────────────────────────────────────────────────────────────────────────────

# Regular button sounds — index matches button index 0–7
_BTN_WAV_NAMES = [
    "thruster",  # 0
    "shields",  # 1
    "scanner",  # 2
    "comms",  # 3
    "repair",  # 4
    "cargo",  # 5
    "lights",  # 6
    "horn",  # 7
]

# Arcade button sounds — index matches ARC_* constants in space_rules
_ARC_WAV_NAMES = [
    "land",  # 0 ARC_LAND     green
    "course",  # 1 ARC_COURSE   blue
    "engines",  # 2 ARC_ENGINES  white
    "repair",  # 3 ARC_REPAIR   yellow
    "distress",  # 4 ARC_DISTRESS red
]

_SPACE_SND_DIR = "/sounds/space/"


def _resolve_sound_paths(names):
    from bodn.assets import resolve_sounds

    return resolve_sounds(_SPACE_SND_DIR, names)


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIO LOOKUP TABLES
# Indexed by SC_* constant from space_rules.  Add a new entry to all three
# lists when adding a scenario (keep them in sync with NUM_SCENARIOS).
# ─────────────────────────────────────────────────────────────────────────────

# TTS key spoken by Stellar on the "announce" event
_SC_TTS = [
    "space_sc_asteroid",  # SC_ASTEROID
    "space_sc_course",  # SC_COURSE
    "space_sc_shield",  # SC_SHIELD
    "space_sc_engine",  # SC_ENGINE
    "space_sc_landing",  # SC_LANDING
]

# Short display label shown on screen during ANNOUNCE and ACTIVE
_SC_LABEL = [
    "space_sc_asteroid_short",  # SC_ASTEROID
    "space_sc_course_short",  # SC_COURSE
    "space_sc_shield_short",  # SC_SHIELD
    "space_sc_engine_short",  # SC_ENGINE
    "space_sc_landing_short",  # SC_LANDING
]

# Instruction text shown during ACTIVE ("what to do")
_SC_INSTR = [
    "space_instr_asteroid",  # SC_ASTEROID
    "space_instr_course",  # SC_COURSE
    "space_instr_shield",  # SC_SHIELD
    "space_instr_engine",  # SC_ENGINE
    "space_instr_landing",  # SC_LANDING
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
        self._drone_zone = -1  # current throttle zone (0/1/2), -1 = not started
        self._alarm_active = False
        self._bridge_next = 0  # frame when next bridge ambience can play
        self._bridge_path = None
        self._btn_wav_paths = None  # resolved at enter(); None = use procedural tones
        self._arc_wav_paths = None
        self._drone_wav_paths = None
        self._alarm_wav_paths = None

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
        self._drone_zone = -1
        self._alarm_active = False
        self._bridge_next = 0
        self._btn_wav_paths = _resolve_sound_paths(_BTN_WAV_NAMES)
        self._arc_wav_paths = _resolve_sound_paths(_ARC_WAV_NAMES)
        self._drone_wav_paths = _resolve_sound_paths(self._DRONE_WAV_NAMES)
        self._alarm_wav_paths = _resolve_sound_paths(self._ALARM_WAV_NAMES)
        paths = _resolve_sound_paths(["bridge_loop"])
        self._bridge_path = paths[0] if paths else None
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
        if self._audio:
            self._audio.stop("music")
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
            self._start_alarm(sc)
            if self._audio and 0 <= sc < len(_SC_TTS):
                try:
                    from bodn import tts

                    if not tts.say(_SC_TTS[sc], self._audio):
                        pass
                except Exception:
                    pass
            if self._secondary:
                self._secondary.set_emotion(SURPRISED)

        elif event == "success":
            self._dirty = True
            self._full_clear = True
            self._leds_dirty = True
            self._stop_alarm()
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
            self._stop_alarm()
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

        # Throttle/steering changes → redraw instruments + update drone pitch
        if (
            abs(self._engine.throttle - self._prev_throttle) >= 4
            or abs(self._engine.steering - self._prev_steering) >= 4
        ):
            self._prev_throttle = self._engine.throttle
            self._prev_steering = self._engine.steering
            self._dirty = True
            self._leds_dirty = True

        self._update_drone(self._engine.throttle)
        self._maybe_play_bridge(frame)

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

    # (freq_hz, duration_ms, wave) — one distinct sound per ship system
    _BTN_SFX = [
        (110, 220, "square"),  # 0 Thrusters  — deep engine pulse
        (880, 100, "sine"),  # 1 Shields     — bright chime
        (1320, 70, "sine"),  # 2 Scanner     — high-pitched ping
        (440, 160, "square"),  # 3 Comms       — radio buzz
        (587, 120, "triangle"),  # 4 Repair      — soft mid beep
        (165, 250, "square"),  # 5 Cargo       — low thud
        (1760, 55, "sine"),  # 6 Lights      — crisp click
        (220, 320, "square"),  # 7 Horn        — long foghorn blast
    ]

    def _play_btn_tone(self, btn):
        """Play a ship-system sound for each button.

        Uses a pre-cached WAV path if one was found at enter(); otherwise
        falls back to the procedural tone defined in _BTN_SFX.
        """
        path = self._btn_wav_paths[btn] if self._btn_wav_paths else None
        if path:
            self._audio.play(path, channel="sfx")
        else:
            freq, dur, wave = self._BTN_SFX[btn % len(self._BTN_SFX)]
            self._audio.tone(freq, dur, wave, channel="sfx")

    # Engine drone: three throttle zones → three WAV loops (or procedural tones).
    # WAV files are resolved at enter() from /sounds/space/.
    # Zone changes stop the current loop and start the new one immediately.
    _DRONE_WAV_NAMES = ["low_engine_loop", "engine_loop", "high_engine_loop"]
    _DRONE_FREQS = [55, 82, 110]  # procedural fallback: A1 / E2 / A2

    # Alarm loops: played on the music channel during scenarios, replacing the
    # engine drone.  Indexed by danger level (0=low, 1=medium, 2=high).
    # The music channel auto-ducks to 25 % when TTS speaks, so announcements
    # are always audible above the alarm.
    _ALARM_WAV_NAMES = ["soft_alarm_loop", "medium_alarm_loop", "alarm_loop"]
    _ALARM_FREQS = [220, 440, 880]  # procedural fallback tones

    # Scenario type → alarm danger level (0=low, 1=medium, 2=high)
    _SC_DANGER = [2, 0, 1, 1, 0]  # asteroid, course, shield, engine, landing

    def _update_drone(self, throttle):
        """Keep the engine drone in sync with the throttle zone."""
        if not self._audio or self._alarm_active:
            return
        zone = 0 if throttle < 85 else (1 if throttle < 170 else 2)
        if zone != self._drone_zone:
            self._drone_zone = zone
            path = self._drone_wav_paths[zone] if self._drone_wav_paths else None
            if path:
                self._audio.play(path, loop=True, channel="music")
            else:
                self._audio.tone(
                    self._DRONE_FREQS[zone], 60000, "square", channel="music"
                )

    # Bridge ambience: plays the bridge_loop once on an SFX channel at random
    # intervals during CRUISING.  ~8–20 s between plays at 30 fps.
    _BRIDGE_MIN = const(240)  # ~8 s
    _BRIDGE_SPREAD = const(360)  # +0–12 s

    def _maybe_play_bridge(self, frame):
        """Occasionally play bridge ambience during cruising."""
        if not self._bridge_path or not self._audio:
            return
        if self._engine.state != CRUISING:
            return
        if frame < self._bridge_next:
            return
        self._audio.play(self._bridge_path, channel="sfx")
        rand = int.from_bytes(os.urandom(2), "big") % self._BRIDGE_SPREAD
        self._bridge_next = frame + self._BRIDGE_MIN + rand

    def _start_alarm(self, sc):
        """Start the alarm loop for the given scenario type on the music channel."""
        if not self._audio or sc < 0 or sc >= len(self._SC_DANGER):
            return
        danger = self._SC_DANGER[sc]
        path = self._alarm_wav_paths[danger] if self._alarm_wav_paths else None
        if path:
            self._audio.play(path, loop=True, channel="music")
        else:
            self._audio.tone(
                self._ALARM_FREQS[danger], 60000, "square", channel="music"
            )
        self._alarm_active = True

    def _stop_alarm(self):
        """Stop the alarm and resume the engine drone."""
        self._alarm_active = False
        self._drone_zone = -1  # force re-trigger on next update

    def _play_arc_tone(self, arc):
        """Big satisfying tone for arcade buttons.

        Uses a pre-cached WAV path if one was found at enter(); otherwise
        falls back to the procedural tone.
        """
        path = self._arc_wav_paths[arc] if self._arc_wav_paths else None
        if path:
            self._audio.play(path, channel="sfx")
        else:
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
            if sc in (SC_LANDING, SC_COURSE):
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

        # For SC_COURSE / SC_LANDING: show target arcade button colour swatch
        if sc in (SC_COURSE, SC_LANDING) and eng.target_arc_idx >= 0:
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
