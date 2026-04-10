# bodn/ui/sequencer.py — Loop sequencer mode screen
#
# Live-jam step sequencer: press arcade buttons (percussion) or mini buttons
# (melody) while the loop plays. Presses quantize to the nearest step.
# sw[0] toggles play/pause, sw[1] toggles 8/16 steps, sw[2] toggles metronome.

try:
    import time
except ImportError:
    import utime as time

from micropython import const

from bodn import config
from bodn.ui.screen import Screen
from bodn.ui.pause import PauseMenu
from bodn.ui.widgets import draw_centered
from bodn.i18n import t
from bodn.sequencer_rules import (
    SequencerEngine,
    STOPPED,
    PLAYING,
    NUM_PERC_TRACKS,
    MELODY_FREQS,
    BPM_STEP,
)

# Try to import native audio mixer for sample-accurate step clock
try:
    import _audiomix

    _has_clock = True
except ImportError:
    _has_clock = False

# Try to import native input module for C-driven LED beat sync
try:
    import _mcpinput

    _has_led_sync = hasattr(_mcpinput, "led_init")
except ImportError:
    _has_led_sync = False

ENC_A = const(1)  # config.ENC_A — BPM control

# Preview voice for button feedback — separate from clock voices (0-5)
_PREVIEW_VOICE = const(6)
# Dedicated voice for metronome clicks — won't steal from preview or clock
_METRO_VOICE = const(7)
# Metronome click frequencies (Hz)
_METRO_HI = const(1200)  # downbeat accent
_METRO_LO = const(800)  # other beats

# Drum sample names on SD — index matches arcade button hardware index
_DRUM_NAMES = ["hihat", "snare", "kick", "tom", "crash"]


def preload_sequencer_assets(on_progress=None):
    """Preload drum kit WAVs into PSRAM.  Call from the mode factory so the
    home screen can show a loading bar while the SD reads happen."""
    from bodn.assets import preload_sounds

    return preload_sounds("/sounds/kits/basic/", _DRUM_NAMES, on_progress=on_progress)


# Grid layout constants (computed once in enter)
_HEADER_H = const(22)
_FOOTER_H = const(26)
_MARKER_H = const(6)  # playhead marker strip height
_NUM_ROWS = const(6)  # 5 percussion + 1 melody


class SequencerScreen(Screen):
    """Interactive loop sequencer for the primary display."""

    def __init__(
        self,
        np,
        overlay,
        audio=None,
        arcade=None,
        settings=None,
        secondary_screen=None,
        on_exit=None,
        drum_bufs=None,
    ):
        self._np = np
        self._overlay = overlay
        self._audio = audio
        self._arcade = arcade
        self._settings = settings or {}
        self._secondary = secondary_screen
        self._on_exit = on_exit
        self._manager = None
        self._pause = PauseMenu(settings=settings)

        self._engine = SequencerEngine()
        self._drum_bufs = drum_bufs  # PSRAM preloaded percussion WAVs (or None)
        self._c_leds = False  # True when C drives arcade LEDs (beat-sync mode)
        self._prev_step = -1  # last step seen by update() (for step_advanced)
        self._render_step = -1  # last step drawn by render (for marker clear)
        self._prev_sw0 = None
        self._prev_sw1 = None
        self._prev_sw2 = None
        self._last_ms = 0
        self._dirty = True
        self._full_clear = True
        self._marker_dirty = False  # playhead marker needs redraw (cheap)
        self._cells_dirty = False  # grid cells changed (redraw affected cells)
        self._flash_msg = None  # temporary overlay text (e.g. "Cleared!")
        self._flash_end = 0

        # Grid geometry (computed in enter based on screen dimensions)
        self._col_w = 0
        self._row_h = 0
        self._grid_x = 0
        self._grid_y = 0
        self._grid_w = 0
        self._grid_h = 0
        self._label_w = 0
        self._marker_y = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._engine = SequencerEngine()
        self._prev_step = -1
        self._render_step = -1
        self._dirty = True
        self._full_clear = True
        self._flash_msg = None

        # Read initial switch state (no edge on first frame)
        sw = manager.inp.sw
        self._prev_sw0 = sw[0] if len(sw) > 0 else False
        self._prev_sw1 = sw[1] if len(sw) > 1 else False
        self._prev_sw2 = sw[2] if len(sw) > 2 else False
        # Initialise metronome from outer toggle position
        if len(sw) > 2 and sw[2]:
            self._engine.metronome = True

        # Preload drum samples into PSRAM (skip if already loaded by factory)
        if self._drum_bufs is None:
            try:
                self._drum_bufs = preload_sequencer_assets()
            except Exception as e:
                print("seq: drum preload error:", e)
                self._drum_bufs = [None] * NUM_PERC_TRACKS

        self._last_ms = time.ticks_ms()

        # Register drum buffers with C clock for sample-accurate triggering
        if _has_clock:
            _audiomix.clock_clear_grid()
            if self._drum_bufs:
                for ti in range(min(NUM_PERC_TRACKS, len(self._drum_bufs))):
                    buf = self._drum_bufs[ti]
                    if buf:
                        _audiomix.clock_set_perc_buffer(ti, buf, len(buf))

            # Melody tone track (track 0, voice 5)
            _audiomix.clock_set_tone_track(0, 5, 0)  # mask filled by _sync_all

            # Metronome tone track (track 1, voice 7)
            # Pre-fill step data for all 16 possible steps
            for s in range(16):
                freq = _METRO_HI if (s % 4 == 0) else _METRO_LO
                _audiomix.clock_set_tone_step(
                    1, s, freq, 30, _audiomix.WAVE_SQUARE, 0, 5, 100
                )
            metro_mask = self._metro_mask() if self._engine.metronome else 0
            _audiomix.clock_set_tone_track(1, _METRO_VOICE, metro_mask)

        # Enable C-driven beat-sync LEDs if available
        self._c_leds = False
        if _has_led_sync and _has_clock and self._arcade:
            try:
                if _mcpinput.led_init():
                    _mcpinput.led_mode(_mcpinput.LED_BEAT_SYNC)
                    self._c_leds = True
            except Exception as e:
                print("seq: C LED init failed:", e)

        # Compute grid geometry
        w = manager.tft.width if hasattr(manager.tft, "width") else 320
        h = manager.tft.height if hasattr(manager.tft, "height") else 240
        self._label_w = 24  # track label column
        self._grid_x = self._label_w
        self._grid_y = _HEADER_H
        self._grid_w = w - self._label_w
        self._grid_h = h - _HEADER_H - _FOOTER_H - _MARKER_H
        self._recompute_grid()

    def _recompute_grid(self):
        """Recompute column/row sizes from current step count."""
        n = self._engine.n_steps
        self._col_w = self._grid_w // n
        self._row_h = self._grid_h // _NUM_ROWS
        # Marker strip sits between grid bottom and footer
        self._marker_y = self._grid_y + self._grid_h

    def exit(self):
        # Restore default LED mode before cleanup
        if self._c_leds:
            try:
                _mcpinput.led_mode(_mcpinput.LED_PYTHON)
            except Exception:
                pass
            self._c_leds = False
        if _has_clock:
            _audiomix.clock_stop()
        self._drum_bufs = None
        if self._audio:
            self._audio.stop("sfx")
            self._audio.stop("music")
        if self._arcade:
            self._arcade.all_off()
            self._arcade.flush()
        if self._on_exit:
            self._on_exit()

    def on_reveal(self):
        self._dirty = True
        self._full_clear = True

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, inp, frame):
        # Pause menu first (standard pattern)
        result = self._pause.update(inp, frame)
        if result == "quit" and self._manager:
            self._manager.pop()
            return
        if result == "resume":
            self._dirty = True
            self._full_clear = True
        if self._pause.is_open or self._pause.is_holding:
            return

        # Timing
        now = time.ticks_ms()
        delta = time.ticks_diff(now, self._last_ms)
        self._last_ms = now

        eng = self._engine

        # --- Toggle switches (edge-triggered) ---
        sw = inp.sw
        sw0 = sw[0] if len(sw) > 0 else False
        sw1 = sw[1] if len(sw) > 1 else False

        if self._prev_sw0 is not None and sw0 != self._prev_sw0:
            if eng.state == PLAYING:
                eng.stop()
                if _has_clock:
                    _audiomix.clock_stop()
            else:
                eng.start()
                if _has_clock:
                    self._sync_all_to_clock()
                    _audiomix.clock_start(eng.bpm, eng.n_steps)
            self._dirty = True
        self._prev_sw0 = sw0

        if self._prev_sw1 is not None and sw1 != self._prev_sw1:
            new_steps = 16 if sw1 else 8
            eng.set_steps(new_steps)
            if _has_clock:
                _audiomix.clock_set_steps(new_steps)
                self._sync_all_to_clock()
                # Update metronome mask for new step count
                if eng.metronome:
                    _audiomix.clock_set_tone_track(1, _METRO_VOICE, self._metro_mask())
            self._recompute_grid()
            self._dirty = True
            self._full_clear = True
        self._prev_sw1 = sw1

        # sw[2] → metronome on/off (outer left toggle)
        sw2 = sw[2] if len(sw) > 2 else False
        if self._prev_sw2 is not None and sw2 != self._prev_sw2:
            eng.toggle_metronome()
            if _has_clock:
                mask = self._metro_mask() if eng.metronome else 0
                _audiomix.clock_set_tone_track(1, _METRO_VOICE, mask)
            self._dirty = True
        self._prev_sw2 = sw2

        # --- Encoder A: BPM ---
        enc_delta = inp.enc_delta[ENC_A]
        if enc_delta:
            eng.set_bpm(eng.bpm + enc_delta * BPM_STEP)
            if _has_clock:
                _audiomix.clock_set_bpm(eng.bpm)
            self._dirty = True

        # --- Encoder A long-press: clear all ---
        enc_a_ch = inp.gesture_enc(config.ENC_A)
        if inp.gestures.long_press[enc_a_ch]:
            eng.clear_all()
            if _has_clock:
                _audiomix.clock_clear_grid()
                # Re-setup tone tracks (clear_grid zeros them)
                _audiomix.clock_set_tone_track(0, 5, 0)  # melody
                # Re-fill metronome step data and restore mask if active
                for s in range(16):
                    freq = _METRO_HI if (s % 4 == 0) else _METRO_LO
                    _audiomix.clock_set_tone_step(
                        1, s, freq, 30, _audiomix.WAVE_SQUARE, 0, 5, 100
                    )
                metro_mask = self._metro_mask() if eng.metronome else 0
                _audiomix.clock_set_tone_track(1, _METRO_VOICE, metro_mask)
            if self._c_leds:
                self._sync_track_active()
            self._dirty = True
            self._full_clear = True
            self._flash_msg = t("seq_cleared")
            self._flash_end = now + 1000

        # --- Arcade buttons: percussion ---
        any_toggled_on = False
        perc_changed = False
        for i in range(NUM_PERC_TRACKS):
            if i < len(inp.arc_just_pressed) and inp.arc_just_pressed[i]:
                step, val = eng.toggle_perc(i)
                perc_changed = True
                if _has_clock:
                    self._sync_step_to_clock(step)
                if val:
                    any_toggled_on = True
                    self._play_drum(i)
                self._cells_dirty = True
        if perc_changed and self._c_leds:
            self._sync_track_active()

        # --- Mini buttons: melody ---
        for i in range(8):
            if i < len(inp.btn_just_pressed) and inp.btn_just_pressed[i]:
                step, val = eng.set_melody(i)
                if _has_clock:
                    self._sync_step_to_clock(step)
                if val:
                    any_toggled_on = True
                    self._play_melody_note(i)
                self._cells_dirty = True

        # Auto-start on first interaction
        if any_toggled_on and eng.state == STOPPED:
            eng.start()
            if _has_clock:
                self._sync_all_to_clock()
                _audiomix.clock_start(eng.bpm, eng.n_steps)
            if self._c_leds:
                self._sync_track_active()
            self._dirty = True

        # --- Advance playhead ---
        if _has_clock and eng.state == PLAYING:
            # C clock drives timing — read current step for UI + quantization
            c_step = _audiomix.clock_get_step()
            eng.step = c_step
            eng._frac = float(c_step)  # keep nearest_step() in sync
            eng.step_advanced = c_step != self._prev_step
        else:
            # Fallback: Python-driven timing
            eng.advance(delta)
            if eng.step_advanced:
                self._trigger_step_sounds(eng.step)

        # --- Metronome click on beat (fallback: no C clock) ---
        if (
            not _has_clock
            and eng.metronome
            and eng.state == PLAYING
            and eng.step_advanced
        ):
            if eng.is_beat(eng.step):
                self._play_metronome(eng.is_downbeat(eng.step))

        # Update prev_step in update() so step_advanced is frame-accurate
        self._prev_step = eng.step

        # --- Playhead movement (marker-only redraw) ---
        if eng.step != self._render_step:
            self._marker_dirty = True

        # --- Update secondary display ---
        if self._secondary:
            self._secondary.update_state(
                eng.bpm, eng.state == PLAYING, eng.n_steps, eng.metronome
            )

        # Arcade LEDs: C handles beat-sync, Python fallback otherwise
        arc = self._arcade
        if arc and not self._c_leds:
            step = eng.step
            step_changed = eng.step_advanced
            for i in range(NUM_PERC_TRACKS):
                if eng.state == PLAYING and step_changed and eng.perc[i][step]:
                    arc.on(i)
                elif any(eng.perc[i]):
                    arc.glow(i)
                else:
                    arc.off(i)
            arc.flush()

        # Clear flash message if expired
        if self._flash_msg and now >= self._flash_end:
            self._flash_msg = None
            self._dirty = True

    # ------------------------------------------------------------------
    # C clock grid sync
    # ------------------------------------------------------------------

    def _sync_step_to_clock(self, step):
        """Push one grid step's perc + melody data to the C clock."""
        if not _has_clock:
            return
        eng = self._engine
        mask = 0
        for ti in range(NUM_PERC_TRACKS):
            if eng.perc[ti][step]:
                mask |= 1 << ti
        _audiomix.clock_set_perc(step, mask)
        # Melody via tone track 0
        mel = eng.melody[step]
        if mel > 0:
            freq = MELODY_FREQS[mel - 1]
            _audiomix.clock_set_tone_step(
                0, step, freq, 150, _audiomix.WAVE_SINE, 2, 10, 100
            )
        else:
            _audiomix.clock_set_tone_step(0, step, 0, 0, 0, 0, 0, 0)

    def _sync_all_to_clock(self):
        """Push entire grid to C clock."""
        if not _has_clock:
            return
        mel_mask = 0
        for s in range(self._engine.n_steps):
            self._sync_step_to_clock(s)
            if self._engine.melody[s] > 0:
                mel_mask |= 1 << s
        _audiomix.clock_set_tone_track(0, 5, mel_mask)

    def _sync_track_active(self):
        """Push track-active bitmask to C LED driver."""
        eng = self._engine
        mask = 0
        for i in range(NUM_PERC_TRACKS):
            if any(eng.perc[i]):
                mask |= 1 << i
        _mcpinput.led_set_track_active(mask)

    def _metro_mask(self):
        """Build step bitmask for metronome beats (every 2nd step = quarter note)."""
        mask = 0
        for s in range(self._engine.n_steps):
            if self._engine.is_beat(s):
                mask |= 1 << s
        return mask

    # ------------------------------------------------------------------
    # Audio helpers
    # ------------------------------------------------------------------

    def _play_drum(self, track):
        """Play a percussion sample immediately (button feedback)."""
        if not self._audio or not self._drum_bufs:
            return
        buf = self._drum_bufs[track] if track < len(self._drum_bufs) else None
        if not buf:
            return
        if _has_clock:
            _audiomix.clock_preview(track)  # suppress clock trigger for this track
        self._audio.play_buffer(buf, voice=_PREVIEW_VOICE)

    def _play_melody_note(self, btn_idx):
        """Play a melody tone immediately (button feedback)."""
        if not self._audio or btn_idx >= len(MELODY_FREQS):
            return
        freq = MELODY_FREQS[btn_idx]
        if _has_clock:
            _audiomix.clock_tone_preview(0)  # suppress clock trigger for melody
            self._update_melody_mask()
        self._audio.tone(freq, 150, "sine", voice=_PREVIEW_VOICE)

    def _update_melody_mask(self):
        """Recompute and push the melody tone track step mask."""
        mel_mask = 0
        eng = self._engine
        for s in range(eng.n_steps):
            if eng.melody[s] > 0:
                mel_mask |= 1 << s
        _audiomix.clock_set_tone_track(0, 5, mel_mask)

    def _play_metronome(self, downbeat):
        """Play a short metronome click. Accented on downbeats."""
        if not self._audio:
            return
        freq = _METRO_HI if downbeat else _METRO_LO
        self._audio.tone(freq, 30, "square", voice=_METRO_VOICE)

    def _trigger_step_sounds(self, step):
        """Trigger all active sounds at a grid step (called on step tick)."""
        if not self._audio:
            return
        eng = self._engine
        for t_idx in range(NUM_PERC_TRACKS):
            if eng.perc[t_idx][step]:
                self._play_drum(t_idx)
        mel = eng.melody[step]
        if mel > 0:
            freq = MELODY_FREQS[mel - 1]
            self._audio.tone(freq, 150, "sine", channel="music")

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def needs_redraw(self):
        return (
            self._dirty
            or self._cells_dirty
            or self._marker_dirty
            or self._pause.needs_render
        )

    def render(self, tft, theme, frame):
        if self._pause.is_open:
            if self._dirty:
                self._dirty = False
                self._cells_dirty = False
                self._marker_dirty = False
                tft.fill(theme.BLACK)
                self._render_game(tft, theme)
            self._pause.render(tft, theme, frame)
            return

        if self._dirty:
            self._dirty = False
            self._cells_dirty = False
            self._marker_dirty = False
            if self._full_clear:
                self._full_clear = False
                tft.fill(theme.BLACK)
            self._render_game(tft, theme)
            self._engine.dirty_steps.clear()
            self._render_step = self._engine.step
        elif self._cells_dirty:
            # Redraw only the toggled cells (engine tracks which steps changed)
            self._cells_dirty = False
            self._render_dirty_cells(tft, theme)
            self._engine.dirty_steps.clear()
            # Also update marker since cells_dirty often comes with a step change
            if self._marker_dirty:
                self._marker_dirty = False
                self._render_marker(tft, theme)
                self._render_step = self._engine.step
        elif self._marker_dirty:
            # Cheapest path: only move the playhead marker strip
            self._marker_dirty = False
            self._render_marker(tft, theme)
            self._render_step = self._engine.step

        self._pause.render(tft, theme, frame)

    def _render_game(self, tft, theme):
        """Full grid render (header + grid + marker + footer)."""
        eng = self._engine
        w = theme.width

        # Header
        tft.fill_rect(0, 0, w, _HEADER_H, theme.BLACK)
        title = t("mode_sequencer").upper()
        tft.text(title, 4, 4, theme.WHITE)
        bpm_str = str(eng.bpm)
        bpm_x = w - len(bpm_str) * 8 - 4
        tft.text(bpm_str, bpm_x, 4, theme.CYAN)

        # Grid rows (static — no playhead highlight in cells)
        for row in range(_NUM_ROWS):
            self._render_row(tft, theme, row)

        # Playhead marker strip
        self._render_marker(tft, theme)

        # Footer
        self._render_footer(tft, theme)

    def _render_row(self, tft, theme, row):
        """Draw one track row with squares (no playhead highlight)."""
        eng = self._engine
        y = self._grid_y + row * self._row_h
        row_h = self._row_h
        n = eng.n_steps

        # Track label (left margin)
        if row < NUM_PERC_TRACKS:
            label_color = theme.ARC_565[row]
        else:
            label_color = theme.MUTED
        sq_size = min(12, row_h - 4)
        sq_y = y + (row_h - sq_size) // 2
        tft.fill_rect(2, sq_y, sq_size, sq_size, label_color)

        # Grid cells
        for s in range(n):
            self._draw_cell(tft, theme, row, s)

    def _draw_cell(self, tft, theme, row, step):
        """Draw a single grid cell."""
        eng = self._engine
        col_w = self._col_w
        row_h = self._row_h
        cx = self._grid_x + step * col_w + col_w // 2
        cy = self._grid_y + row * row_h + row_h // 2
        r = min(col_w, row_h) // 2 - 2
        if r < 2:
            r = 2

        if row < NUM_PERC_TRACKS:
            active = eng.perc[row][step]
            color = theme.ARC_565[row] if active else theme.DIM
        else:
            mel_val = eng.melody[step]
            active = mel_val > 0
            color = theme.BTN_565[mel_val - 1] if active else theme.DIM

        if active:
            tft.fill_rect(cx - r, cy - r, r * 2, r * 2, color)
        else:
            # Clear then outline (cell might have been filled before)
            tft.fill_rect(cx - r, cy - r, r * 2, r * 2, theme.BLACK)
            tft.rect(cx - r, cy - r, r * 2, r * 2, color)

    def _render_dirty_cells(self, tft, theme):
        """Redraw only cells that changed (from engine.dirty_steps)."""
        eng = self._engine
        for step in eng.dirty_steps:
            for row in range(_NUM_ROWS):
                self._draw_cell(tft, theme, row, step)

    def _render_marker(self, tft, theme):
        """Draw the playhead marker strip — tiny dirty rect."""
        eng = self._engine
        col_w = self._col_w
        old_step = self._render_step
        new_step = eng.step
        my = self._marker_y

        # Clear old marker
        if 0 <= old_step < eng.n_steps:
            ox = self._grid_x + old_step * col_w
            tft.fill_rect(ox, my, col_w, _MARKER_H, theme.BLACK)

        # Draw new marker
        if eng.state == PLAYING:
            nx = self._grid_x + new_step * col_w
            tft.fill_rect(nx + 1, my + 1, col_w - 2, _MARKER_H - 2, theme.WHITE)

    def _render_footer(self, tft, theme):
        """Draw footer: play state and step count."""
        eng = self._engine
        w = theme.width
        h = theme.height
        fy = h - _FOOTER_H + 4

        if self._flash_msg:
            draw_centered(tft, self._flash_msg, fy, theme.YELLOW, w, scale=2)
            return

        if eng.state == STOPPED:
            draw_centered(tft, t("seq_press_start"), fy, theme.MUTED, w)
        else:
            # Play indicator + step info
            state_str = t("seq_playing")
            steps_str = t("seq_steps", eng.n_steps)
            tft.text(state_str, 4, fy, theme.GREEN)
            steps_x = w - len(steps_str) * 8 - 4
            tft.text(steps_str, steps_x, fy, theme.MUTED)

    # ------------------------------------------------------------------
    # LED stub (for future use)
    # ------------------------------------------------------------------

    def _update_leds(self, frame, brightness):
        pass
