# bodn/ui/highfive.py — High-Five Friends game screen
#
# Animals pop up on arcade buttons wanting high-fives. Tap the lit
# button before it disappears. C scan task drives LED pulse + hit
# detection at 500 Hz for snappy response.

try:
    import time
except ImportError:
    import utime as time

try:
    import os
except ImportError:
    import uos as os

from micropython import const

from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.pause import PauseMenu
from bodn.ui.widgets import draw_centered
from bodn.i18n import t
from bodn.highfive_rules import (
    HighFiveEngine,
    READY,
    SHOWING,
    HIT_FLASH,
    MISS_FLASH,
    GAME_OVER,
    NUM_BUTTONS,
)
from bodn.patterns import N_LEDS, ZONE_LID_RING, zone_pulse, zone_rainbow, zone_clear
from bodn.assets import preload_sounds

# Try native LED driver for C-level hit detection
try:
    import _mcpinput

    _has_whack = hasattr(_mcpinput, "led_set_whack_target")
except ImportError:
    _has_whack = False

# Arcade button colors (RGB) for NeoPixel feedback
_ARC_RGB = (
    (60, 220, 60),  # green
    (60, 100, 255),  # blue
    (255, 255, 255),  # white
    (255, 220, 60),  # yellow
    (255, 60, 60),  # red
)

# Cat face emotions per state
_EMOTIONS = {
    READY: "neutral",
    SHOWING: "curious",
    HIT_FLASH: "happy",
    MISS_FLASH: "surprised",
    GAME_OVER: "neutral",
}

# Tones per button (pentatonic, same as Simon)
_TONES = (262, 330, 392, 523, 659)
_TONE_HIT = const(880)  # celebration tone
_TONE_MISS = const(150)  # sad tone

_HEADER_H = const(20)
_FOOTER_H = const(20)

# Sound effect names on SD: /sounds/highfive/<name>.wav
# Multiple variants per event — game picks randomly for variation.
_SND_DIR = "/sounds/highfive/"
_SND_POP = ["pop_1", "pop_2", "pop_3"]  # animal popping up
_SND_CLAP = ["clap_1", "clap_2"]  # high-five slap
_SND_CHEER = ["cheer_1", "cheer_2"]  # success celebration
_SND_AWW = ["aww_1", "aww_2"]  # missed / too slow
_ALL_SND_NAMES = _SND_POP + _SND_CLAP + _SND_CHEER + _SND_AWW


def _rand_pick(bufs):
    """Pick a random non-None buffer from a list."""
    valid = [b for b in bufs if b]
    if not valid:
        return None
    idx = int.from_bytes(os.urandom(1), "big") % len(valid)
    return valid[idx]


def preload_highfive_assets(on_progress=None):
    """Preload all High-Five sound variations into PSRAM."""
    return preload_sounds(_SND_DIR, _ALL_SND_NAMES, on_progress=on_progress)


class HighFiveScreen(Screen):
    """High-Five Friends — tap the animal before it disappears."""

    def __init__(
        self,
        np,
        overlay,
        arcade=None,
        audio=None,
        settings=None,
        secondary_screen=None,
        on_exit=None,
        sound_bufs=None,
    ):
        self._np = np
        self._overlay = overlay
        self._arcade = arcade
        self._audio = audio
        self._settings = settings or {}
        self._secondary = secondary_screen
        self._on_exit = on_exit
        self._manager = None
        self._pause = PauseMenu(settings=settings)
        self._engine = HighFiveEngine()
        self._c_leds = False
        self._prev_state = -1
        self._dirty = True
        self._full_clear = True
        self._leds_dirty = True
        # Sound buffers grouped by event type
        self._snd_bufs = sound_bufs
        self._snd_pop = []
        self._snd_clap = []
        self._snd_cheer = []
        self._snd_aww = []

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._engine.start(manager._frame)
        self._prev_state = -1
        self._dirty = True
        self._full_clear = True
        self._leds_dirty = True

        # Split preloaded sound buffers into event groups
        bufs = self._snd_bufs or [None] * len(_ALL_SND_NAMES)
        n_pop = len(_SND_POP)
        n_clap = len(_SND_CLAP)
        n_cheer = len(_SND_CHEER)
        off = 0
        self._snd_pop = bufs[off : off + n_pop]
        off += n_pop
        self._snd_clap = bufs[off : off + n_clap]
        off += n_clap
        self._snd_cheer = bufs[off : off + n_cheer]
        off += n_cheer
        self._snd_aww = bufs[off : off + len(_SND_AWW)]

        # Init C LED driver for whack mode (hit detection at 500Hz)
        self._c_leds = False
        if _has_whack and self._arcade:
            try:
                if _mcpinput.led_init():
                    _mcpinput.led_set_whack_pins(config.MCP_ARC_PINS)
                    _mcpinput.led_mode(_mcpinput.LED_WHACK)
                    self._c_leds = True
            except Exception as e:
                print("highfive: C LED init failed:", e)

        # Register scan-time audio callback for immediate button tones
        if self._audio:
            manager.inp.set_on_press(self._on_press)

    def exit(self):
        if self._c_leds:
            try:
                _mcpinput.led_set_whack_target(0xFF, 0)
                _mcpinput.led_mode(_mcpinput.LED_PYTHON)
            except Exception:
                pass
            self._c_leds = False

        # Free sound buffers (PSRAM)
        self._snd_bufs = None
        self._snd_pop = []
        self._snd_clap = []
        self._snd_cheer = []
        self._snd_aww = []

        if self._arcade:
            self._arcade.all_off()
            self._arcade.flush()

        # Clear press callback
        if self._manager:
            self._manager.inp.set_on_press(None)

        # Clear NeoPixels
        np = self._np
        for i in range(N_LEDS):
            np[i] = (0, 0, 0)
        np.write()

        if self._on_exit:
            self._on_exit()

    def on_reveal(self):
        self._dirty = True
        self._full_clear = True

    def needs_redraw(self):
        return self._dirty or self._pause.needs_render

    def _on_press(self, kind, index):
        """Scan-time audio callback (~200 Hz). Tone fallback when no WAVs."""
        if kind != "arc" or index >= NUM_BUTTONS:
            return
        # When WAV files are loaded, all audio comes from state transitions
        # (pop/clap/cheer/aww). Only play procedural tones as a fallback
        # when no sound files are available.
        if any(self._snd_pop):
            return
        eng = self._engine
        if self._audio and eng.state == SHOWING:
            self._audio.tone(_TONES[index], 100)

    def _play_sfx(self, bufs, fallback_freq, fallback_ms, wave="sine", channel="sfx"):
        """Play a random WAV variation, or fall back to a procedural tone."""
        buf = _rand_pick(bufs)
        if buf:
            self._audio.play_buffer(buf, channel=channel)
        else:
            self._audio.tone(fallback_freq, fallback_ms, wave, channel=channel)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, inp, frame):
        result = self._pause.update(inp, frame)
        if result == "quit" and self._manager:
            self._manager.pop()
            return
        if result == "resume":
            self._dirty = True
            self._full_clear = True
        if self._pause.is_open or self._pause.is_holding:
            return

        eng = self._engine
        prev_state = eng.state

        # Poll C driver for hit/miss events
        hit = False
        miss = False
        if self._c_leds:
            try:
                hit, miss = _mcpinput.led_get_whack_result()
            except Exception:
                pass
        else:
            # Fallback: check arcade button presses from Python input
            if eng.state == SHOWING and eng.target >= 0:
                for i in range(NUM_BUTTONS):
                    if i < len(inp.arc_just_pressed) and inp.arc_just_pressed[i]:
                        if i == eng.target:
                            hit = True
                        break

        # Advance game state
        eng.advance(hit, miss, frame)

        # State transition effects
        if eng.state != prev_state:
            self._dirty = True
            self._leds_dirty = True

            # Audio feedback (WAV with random variation, tone fallback)
            if eng.state == SHOWING and self._audio:
                self._play_sfx(self._snd_pop, _TONES[eng.target % len(_TONES)], 100)
            elif eng.state == HIT_FLASH and self._audio:
                self._play_sfx(self._snd_clap, _TONE_HIT, 100)
                self._play_sfx(self._snd_cheer, _TONE_HIT, 200, channel="music")
            elif eng.state == MISS_FLASH and self._audio:
                self._play_sfx(self._snd_aww, _TONE_MISS, 300, wave="square")
            elif eng.state == GAME_OVER and self._audio:
                self._play_sfx(self._snd_aww, _TONE_MISS, 500, wave="sawtooth")

            # Cat face emotion
            if self._secondary:
                emotion = _EMOTIONS.get(eng.state, "neutral")
                self._secondary.set_emotion(emotion)

            # Set next C target when entering SHOWING
            if eng.state == SHOWING and self._c_leds and eng.target >= 0:
                now_ms = time.ticks_ms()
                deadline = now_ms + eng.window_ms
                _mcpinput.led_set_whack_target(eng.target, deadline, eng.pulse_speed)

        # Python-fallback arcade LED control (when C not available)
        if self._arcade and not self._c_leds:
            self._update_arcade_leds(eng, frame)

        # NeoPixel strip (every 3rd frame)
        if frame % 3 == 0:
            self._update_neopixels(eng, frame)

    def _update_arcade_leds(self, eng, frame):
        """Python fallback: drive arcade LEDs from game state."""
        arc = self._arcade
        if eng.state == SHOWING and eng.target >= 0:
            for i in range(NUM_BUTTONS):
                if i == eng.target:
                    arc.pulse(i, frame, speed=eng.pulse_speed)
                else:
                    arc.off(i)
        elif eng.state == HIT_FLASH:
            arc.all_off()
            if eng.target >= 0:
                arc.flash(eng.target)
            arc.tick_flash()
        elif eng.state == MISS_FLASH:
            for i in range(NUM_BUTTONS):
                arc.blink(i, frame, speed=6)
        else:
            arc.all_off()
        arc.flush()

    def _update_neopixels(self, eng, frame):
        """Update NeoPixel strip based on game state."""
        np = self._np
        brightness = 80

        if eng.state == SHOWING and eng.target >= 0:
            color = _ARC_RGB[eng.target]
            zone_pulse(ZONE_LID_RING, frame, 2, color, brightness)
        elif eng.state == HIT_FLASH:
            if eng.streak >= 3:
                zone_rainbow(ZONE_LID_RING, frame, 3, 0, brightness)
            else:
                zone_pulse(ZONE_LID_RING, frame, 4, (60, 255, 60), brightness)
        elif eng.state == MISS_FLASH:
            zone_pulse(ZONE_LID_RING, frame, 6, (255, 40, 40), brightness)
        else:
            zone_clear(ZONE_LID_RING)

        for i in range(N_LEDS):
            np[i] = np[i]  # force buffer sync
        np.write()

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(self, tft, theme, frame):
        if self._pause.is_open:
            if self._dirty:
                self._dirty = False
                tft.fill(theme.BLACK)
                self._full_clear = False
                self._render_game(tft, theme)
            self._pause.render(tft, theme, frame)
            return

        if not self._dirty:
            self._pause.render(tft, theme, frame)
            return
        self._dirty = False
        if self._full_clear:
            self._full_clear = False
            tft.fill(theme.BLACK)
        self._render_game(tft, theme)
        self._pause.render(tft, theme, frame)

    def _render_game(self, tft, theme):
        eng = self._engine
        w = theme.width
        h = theme.height

        # Header
        tft.fill_rect(0, 0, w, _HEADER_H, theme.BLACK)
        title = t("mode_highfive").upper()
        tft.text(title, 4, 4, theme.WHITE)
        # Round on right
        rd_txt = t("hf_round", eng.round)
        tft.text(rd_txt, w - len(rd_txt) * 8 - 4, 4, theme.CYAN)

        # Center area
        cy = h // 2 - 8
        tft.fill_rect(0, _HEADER_H, w, h - _HEADER_H - _FOOTER_H, theme.BLACK)

        if eng.state == READY:
            draw_centered(tft, t("hf_ready"), cy, theme.MUTED, w, scale=2)
        elif eng.state == SHOWING:
            # Show which button to hit — translated color name
            if 0 <= eng.target < len(config.ARCADE_COLORS):
                color_key = "color_" + config.ARCADE_COLORS[eng.target]
                draw_centered(tft, t("hf_go"), cy - 16, theme.WHITE, w, scale=2)
                draw_centered(tft, t(color_key), cy + 16, theme.CYAN, w, scale=2)
        elif eng.state == HIT_FLASH:
            draw_centered(tft, t("hf_hit"), cy, theme.GREEN, w, scale=2)
        elif eng.state == MISS_FLASH:
            draw_centered(tft, t("hf_miss"), cy, theme.RED, w, scale=2)
            # Show remaining lives
            lives = 3 - eng.misses
            lives_txt = t("hf_lives", lives)
            draw_centered(tft, lives_txt, cy + 24, theme.MUTED, w)
        elif eng.state == GAME_OVER:
            draw_centered(tft, t("hf_gameover"), cy - 12, theme.RED, w, scale=2)
            score_txt = t("hf_final", eng.score)
            draw_centered(tft, score_txt, cy + 16, theme.WHITE, w)
            if eng.high_score > 0:
                best_txt = t("hf_best", eng.high_score)
                draw_centered(tft, best_txt, cy + 32, theme.YELLOW, w)

        # Footer: score + streak
        fy = h - _FOOTER_H + 2
        tft.fill_rect(0, fy - 2, w, _FOOTER_H, theme.BLACK)
        score_txt = t("hf_score", eng.score)
        tft.text(score_txt, 4, fy, theme.WHITE)
        if eng.streak > 1:
            streak_txt = t("hf_streak", eng.streak)
            tft.text(
                streak_txt,
                w - len(streak_txt) * 8 - 4,
                fy,
                theme.YELLOW,
            )
