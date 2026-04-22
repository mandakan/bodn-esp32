# bodn/ui/tone_explorer.py — Tone Lab screen (primary display)
#
# Free-play sandbox: encoders + arcade buttons shape one sustained voice,
# 8 mini buttons hold-to-apply effects, toggles pick viz and octave.
# See bodn.tone_explorer_rules for the pure-logic engine; this file handles
# I/O wiring, pre-rendered blob sprites, and the small scope strip.

import framebuf

from micropython import const

from bodn.ui.screen import Screen
from bodn.ui.pause import PauseMenu
from bodn.ui.widgets import blit_sprite, draw_centered
from bodn.ui.draw import waveform as draw_waveform, text as draw_text, text_width
from bodn.i18n import t, capitalize
from bodn.neo import neo
from bodn.tone_explorer_rules import (
    EFFECT_STUTTER,
    EFFECT_TREMOLO,
    EFFECT_VIBRATO,
    MINI_BUTTON_EFFECT,
    MINI_BUTTON_LABEL_KEYS,
    NOTES_PER_OCTAVE,
    NUM_PITCHES,
    NUM_TIMBRES,
    ToneExplorer,
)

_BLOB_SIZE = const(96)
_SCOPE_H = const(48)
_SCOPE_SAMPLES = const(256)  # samples drawn per frame (<= _audiomix.SCOPE_SAMPLES)
_HEADER_H = const(22)
_FOOTER_H = const(26)

# Arcade LED animation ids — plain int constants so the _mcpinput C driver
# doesn't need to be queried on every update().
_ARC_OFF = const(0)
_ARC_GLOW = const(1)
_ARC_ON = const(2)

# Pitch step → RGB (matches the physical arcade button colours so the stick
# LEDs light up in the same shade as whichever button plays that note).
# Order: 0=green, 1=blue, 2=white, 3=yellow, 4=red.  Brightness intentionally
# left low — the sticks are peripheral, not the focus.
_STEP_RGB = (
    (0, 255, 80),  # green
    (40, 90, 255),  # blue
    (220, 220, 220),  # white
    (255, 200, 0),  # yellow
    (255, 40, 40),  # red
)

# Timbre → NeoPixel pattern and base speed.  Sine = solid (calm), triangle =
# gentle pulse, saw = faster pulse (bright), square = chase (edgy), noise_pitched
# = sparkle (fuzzy).  Pattern ids resolve against neo.PAT_* at init time.
_TIMBRE_PATTERN = (
    neo.PAT_SOLID,
    neo.PAT_PULSE,
    neo.PAT_PULSE,
    neo.PAT_CHASE,
    neo.PAT_SPARKLE,
)
_TIMBRE_SPEED = (0, 2, 4, 3, 5)

# Left encoder = pitch, right encoder = timbre.
_ENC_PITCH = const(0)  # config.ENC_NAV
_ENC_TIMBRE = const(1)  # config.ENC_A

# Switch indices in inp.sw — see main.input_scan_task for the MCP layout.
_SW_AUDIO_OUT = const(0)  # MCP1 GPB0 — True = speaker on, False = silent
_SW_GATE_MODE = const(1)  # MCP1 GPB1 — True = arcade-gated, False = continuous
_SW_VIZ_LEFT = const(2)  # MCP2 SW_LEFT — True = scope on primary
_SW_OCT_RIGHT = const(3)  # MCP2 SW_RIGHT — True = high octave

# Sprite transparency key (matches widgets._TRANSPARENT).
_TRANSPARENT = 0x1FF8


def _make_blob_sprite(shape_id, size, color):
    """Pre-render one blob shape into a FrameBuffer for fast per-frame blit.

    Five shapes mapped to Bouba/Kiki cross-modal axis — round sine → spiky
    noise.  All fit within a size×size square sprite with _TRANSPARENT bg.
    """
    buf = bytearray(size * size * 2)
    fb = framebuf.FrameBuffer(buf, size, size, framebuf.RGB565)
    fb.fill(_TRANSPARENT)

    cx = size // 2
    cy = size // 2

    if shape_id == 0:
        # Smooth sine → perfect circle.
        r = size // 2 - 4
        _fill_circle(fb, cx, cy, r, color)
    elif shape_id == 1:
        # Soft sine → slightly tall oval.
        rx = size // 2 - 6
        ry = size // 2 - 3
        _fill_ellipse(fb, cx, cy, rx, ry, color)
    elif shape_id == 2:
        # Bright sawtooth → rounded triangle.
        r = size // 2 - 4
        _fill_circle(fb, cx, cy, r - 2, color)
        # Cut a triangular wedge to give a "pointy" bias on top.
        for dy in range(-r, 0):
            w = r + dy  # narrows as we go up
            if w <= 0:
                continue
            fb.fill_rect(cx - w, cy + dy, w * 2, 1, color)
    elif shape_id == 3:
        # Edgy square → rounded square.
        pad = 6
        s = size - pad * 2
        fb.fill_rect(pad, pad, s, s, color)
    else:
        # Fuzzy noise → spiky star (8 rays + central disc).
        r = size // 3
        _fill_circle(fb, cx, cy, r, color)
        for ang in range(8):
            # Approximate diagonal rays with short bars.
            dx = [1, 1, 0, -1, -1, -1, 0, 1][ang]
            dy = [0, 1, 1, 1, 0, -1, -1, -1][ang]
            for d in range(r, r + 10):
                x = cx + dx * d
                y = cy + dy * d
                if 0 <= x < size and 0 <= y < size:
                    fb.pixel(x, y, color)

    return (fb, size, size)


def _fill_circle(fb, cx, cy, r, color):
    """Integer midpoint-circle fill (no libm)."""
    for dy in range(-r, r + 1):
        dx = _isqrt(r * r - dy * dy)
        fb.fill_rect(cx - dx, cy + dy, dx * 2, 1, color)


def _fill_ellipse(fb, cx, cy, rx, ry, color):
    """Scanline ellipse fill."""
    for dy in range(-ry, ry + 1):
        # x^2/rx^2 + y^2/ry^2 = 1  →  x = rx * sqrt(1 - y^2/ry^2)
        num = (ry * ry - dy * dy) * rx * rx
        dx = _isqrt(num) // ry if ry else 0
        fb.fill_rect(cx - dx, cy + dy, dx * 2, 1, color)


def _isqrt(n):
    if n <= 0:
        return 0
    x = n
    y = (x + 1) // 2
    while y < x:
        x = y
        y = (x + n // x) // 2
    return x


class ToneExplorerScreen(Screen):
    """Tone Lab — free-play sandbox for pitch + timbre + effects."""

    def __init__(
        self,
        overlay,
        audio=None,
        arcade=None,
        settings=None,
        secondary_screen=None,
        on_exit=None,
    ):
        self._overlay = overlay
        self._audio = audio
        self._arcade = arcade
        self._settings = settings or {}
        self._secondary = secondary_screen
        self._on_exit = on_exit
        self._manager = None
        self._pause = PauseMenu(settings=settings)

        self._engine = ToneExplorer()
        self._dirty = True
        self._full_clear = True

        # Audio voice handles (set in enter()).  Voices come from the "music"
        # pool so concurrent SFX on voices 0-9 don't steal the sustained tone.
        self._voice = None
        self._harmony_voice = None

        # Last state snapshot — used to decide which C calls to send.
        self._last_eff_freq = 0
        self._last_waveform = -1
        self._last_mask = -1

        # Pre-rendered blob sprites (built in enter()).
        self._blob_sprites = None
        self._blob_color = None

        # Scope scratch buffer: 256 int16 samples = 512 bytes.
        self._scope_buf = bytearray(_SCOPE_SAMPLES * 2)
        self._have_scope = False

        # Ephemeral audio-output mute via sw[0] — stash the entry-time value so
        # exit() can restore it without touching persisted storage.
        self._saved_audio_enabled = True
        self._last_audio_sw = None

        # Gate-mode state (sw[1]): when True, the voice only sounds while an
        # arcade button is held.  _voice_active tracks whether the mixer is
        # currently producing sound on self._voice — we fade in on first press
        # and fade out on release so transitions stay click-free.
        self._voice_active = False
        self._gate_mode = False
        self._gate_any_arcade_held = False

        # Cached switch state for the MUTE/GATE status badges on the primary
        # display.  We diff against this so the badges only repaint on change.
        self._muted = False
        self._last_muted_painted = None
        self._last_gate_painted = None

        # Arcade LED state cache — one entry per button (0..4), each _ARC_*.
        # Diffing avoids spamming I2C writes via _mcpinput.led_anim().
        self._last_arcade_led = [None] * NOTES_PER_OCTAVE

        # NeoPixel sticks: cache last (pitch_step, timbre, speed) tuple so we
        # only re-issue zone_pattern when something actually changes.
        self._last_stick_key = None

    # ---- lifecycle ------------------------------------------------------

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._dirty = True
        self._full_clear = True
        self._last_mask = -1
        self._last_waveform = -1
        self._last_eff_freq = 0

        self._saved_audio_enabled = self._settings.get("audio_enabled", True)
        self._last_audio_sw = None
        self._last_muted_painted = None
        self._last_gate_painted = None
        self._last_arcade_led = [None] * NOTES_PER_OCTAVE
        self._last_stick_key = None

        # Pick blob colour — cyan reads well on black; pitch shifts hue later
        # via the background tint.  Keeping the sprite one colour avoids
        # re-rendering 5 sprites on every pitch change.
        theme = manager.theme
        self._blob_color = theme.CYAN

        # Pre-render all five timbre sprites once.
        self._blob_sprites = [
            _make_blob_sprite(i, _BLOB_SIZE, self._blob_color)
            for i in range(NUM_TIMBRES)
        ]

        # Scope is only meaningful when the native audio engine is present.
        self._have_scope = hasattr(self._audio, "scope_peek") if self._audio else False

        # Allocate a voice slot from the "music" pool.  Whether it starts
        # sounding depends on the gate-mode switch — we (re)start it from
        # _sync_audio() once we know the current sw[1] state.
        self._voice_active = False
        self._gate_mode = False
        if self._audio:
            try:
                self._voice = self._audio.tone_sustained(
                    self._engine.base_freq_hz,
                    wave=_wave_name(self._engine.waveform_id),
                    channel="music",
                )
                self._voice_active = True
                self._audio.set_freq(self._voice, self._engine.base_freq_hz)
            except Exception as e:
                print("tone_explorer: failed to start voice:", e)
                self._voice = None

    def exit(self):
        if self._audio and self._voice is not None:
            self._audio.clear_mods(self._voice)
            self._audio.stop(voice=self._voice)
        if self._audio and self._harmony_voice is not None:
            self._audio.clear_mods(self._harmony_voice)
            self._audio.stop(voice=self._harmony_voice)
        self._voice = None
        self._harmony_voice = None
        self._blob_sprites = None
        if self._arcade:
            self._arcade.all_off()
            self._arcade.flush()
        # Release the NeoPixel sticks so the next mode starts clean.
        if neo.active:
            neo.zone_off(neo.ZONE_STICK_A)
            neo.zone_off(neo.ZONE_STICK_B)
        # Restore audio-enabled flag to its entry-time value. The housekeeping
        # task will sync audio.volume within 500 ms; push it now for no gap.
        self._settings["audio_enabled"] = self._saved_audio_enabled
        if self._audio:
            self._audio.volume = (
                self._settings.get("volume", 30) if self._saved_audio_enabled else 0
            )
        if self._on_exit:
            self._on_exit()

    def on_reveal(self):
        self._dirty = True
        self._full_clear = True

    def needs_redraw(self):
        # Scope is animated, so we want a render every frame even when the
        # engine's discrete state hasn't changed.
        return True

    # ---- input → rules --------------------------------------------------

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

        # Toggles — read every frame (cheap, idempotent).
        if len(inp.sw) > _SW_OCT_RIGHT:
            eng.on_octave_toggle(inp.sw[_SW_OCT_RIGHT])
        if len(inp.sw) > _SW_VIZ_LEFT:
            eng.on_viz_toggle(inp.sw[_SW_VIZ_LEFT])
        if len(inp.sw) > _SW_AUDIO_OUT:
            self._apply_audio_switch(inp.sw[_SW_AUDIO_OUT])
        prev_gate = self._gate_mode
        self._gate_mode = (
            inp.sw[_SW_GATE_MODE] if len(inp.sw) > _SW_GATE_MODE else False
        )
        if self._gate_mode != prev_gate:
            self._dirty = True
        self._gate_any_arcade_held = any(
            inp.arc_held[i] for i in range(min(NOTES_PER_OCTAVE, len(inp.arc_held)))
        )

        # Encoders — each detent = one pentatonic / timbre step.  Clamping
        # lives in the engine so the screen doesn't need to know the bounds.
        if len(inp.enc_delta) > _ENC_PITCH and inp.enc_delta[_ENC_PITCH]:
            eng.on_pitch_delta(inp.enc_delta[_ENC_PITCH])
            self._dirty = True
        if len(inp.enc_delta) > _ENC_TIMBRE and inp.enc_delta[_ENC_TIMBRE]:
            eng.on_timbre_delta(inp.enc_delta[_ENC_TIMBRE])
            self._dirty = True

        # Encoder pushes: left = panic, right = reset timbre to sine.
        if len(inp.enc_btn_pressed) > _ENC_PITCH and inp.enc_btn_pressed[_ENC_PITCH]:
            eng.on_panic()
            self._dirty = True
        if len(inp.enc_btn_pressed) > _ENC_TIMBRE and inp.enc_btn_pressed[_ENC_TIMBRE]:
            eng.on_reset_timbre()
            self._dirty = True

        # Arcade buttons — last-note-priority monosynth: press pushes onto
        # the engine's held-stack, release pops it, and the top drives pitch.
        n_arc = min(
            NOTES_PER_OCTAVE, len(inp.arc_just_pressed), len(inp.arc_just_released)
        )
        for i in range(n_arc):
            if inp.arc_just_pressed[i]:
                eng.on_arcade(i, True)
                self._dirty = True
            if inp.arc_just_released[i]:
                eng.on_arcade(i, False)
                self._dirty = True

        # Mini buttons — hold-to-apply effects.
        mask_before = eng.effects_mask
        for i in range(min(len(MINI_BUTTON_EFFECT), len(inp.btn_just_pressed))):
            if inp.btn_just_pressed[i]:
                eng.on_mini_button(i, True)
            if inp.btn_just_released[i]:
                eng.on_mini_button(i, False)
        # Also reconcile with held state in case we missed an edge (e.g. entered
        # the screen with a button already down).
        for i in range(min(len(MINI_BUTTON_EFFECT), len(inp.btn_held))):
            held = inp.btn_held[i]
            bit = MINI_BUTTON_EFFECT[i]
            if held and not (eng.effects_mask & bit):
                eng.on_mini_button(i, True)
            elif not held and (eng.effects_mask & bit):
                eng.on_mini_button(i, False)
        if eng.effects_mask != mask_before:
            self._dirty = True

        # Push derived state to the audio engine.
        self._sync_audio()

        # Mirror state onto the arcade button LEDs and the NeoPixel sticks.
        self._sync_leds()

        # Push status to the secondary display.
        if self._secondary and hasattr(self._secondary, "update_state"):
            self._secondary.update_state(
                eng.pitch_idx,
                eng.timbre_idx,
                eng.effects_mask,
                eng.viz_big_scope,
            )

    def _apply_audio_switch(self, sw_on):
        """Ephemerally mirror sw[0] into settings['audio_enabled'] so the
        housekeeping task mutes/unmutes the engine.  Never persisted — the
        global parental setting stashed in enter() is restored on exit.
        A globally-disabled setting cannot be overridden up by this switch.
        """
        if sw_on == self._last_audio_sw:
            return
        self._last_audio_sw = sw_on
        enabled = bool(sw_on) and self._saved_audio_enabled
        self._settings["audio_enabled"] = enabled
        # Muted whenever the physical switch is off *or* audio is globally
        # disabled.  Drives the on-screen MUTE badge.
        self._muted = not enabled
        self._dirty = True
        if self._audio:
            self._audio.volume = self._settings.get("volume", 30) if enabled else 0

    def _sync_audio(self):
        """Translate engine state into C-mixer commands.  Idempotent — only
        sends calls when the relevant field has changed."""
        if not self._audio or self._voice is None:
            return
        eng = self._engine
        eff_freq = eng.effective_freq_hz()

        # Gate mode: voice only sounds while an arcade button is held.  We
        # fade the voice out on release (voice_stop) and re-trigger it on the
        # next press — tone_sustained's fade-in keeps that click-free.
        if self._gate_mode:
            should_sound = self._gate_any_arcade_held
        else:
            should_sound = True

        if should_sound and not self._voice_active:
            self._voice = self._audio.tone_sustained(
                eff_freq,
                wave=_wave_name(eng.waveform_id),
                channel="music",
                voice=self._voice,
            )
            self._voice_active = True
            self._last_eff_freq = eff_freq
            self._last_waveform = eng.waveform_id
            self._last_mask = -1  # reapply effects after retrigger
        elif not should_sound and self._voice_active:
            # voice_stop() triggers a graceful fade-out in the mixer before
            # the voice is released.  No need to touch effect state — the
            # next tone_sustained() reapplies everything.
            self._audio.stop(voice=self._voice)
            self._voice_active = False
            # Drop the harmony too so it doesn't linger past the gate close.
            if self._harmony_voice is not None:
                self._audio.stop(voice=self._harmony_voice)
                self._harmony_voice = None

        if not self._voice_active:
            # Keep derived state in sync so the next gate-open starts cleanly.
            self._last_eff_freq = eff_freq
            self._last_waveform = eng.waveform_id
            return

        if eff_freq != self._last_eff_freq:
            self._audio.set_freq(self._voice, eff_freq)
            self._last_eff_freq = eff_freq
            # Harmony tracks the base pitch, not the effective one — the
            # octave-jump mod buttons only bend the main voice.  Refresh it
            # whenever the pitch changes so holding the duo effect doesn't
            # freeze the fifth at whatever note it was triggered on.
            if self._harmony_voice is not None:
                h_freq = eng.harmony_freq_hz()
                if h_freq:
                    self._audio.set_freq(self._harmony_voice, h_freq)

        # Waveform change: phase-preserving crossfade (no voice retrigger).
        if eng.waveform_id != self._last_waveform:
            wave_name = _wave_name(eng.waveform_id)
            self._audio.set_wave(self._voice, wave_name)
            self._last_waveform = eng.waveform_id
            # Keep the harmony voice on the same timbre as the main voice —
            # otherwise changing timbre while duo is held gives you two
            # different waveforms at once.
            if self._harmony_voice is not None:
                self._audio.set_wave(self._harmony_voice, wave_name)

        if eng.effects_mask != self._last_mask:
            self._apply_effects()
            self._last_mask = eng.effects_mask

    def _apply_effects(self):
        """Translate the effect bitmask into mixer modulation calls."""
        a = self._audio
        v = self._voice
        eng = self._engine

        rate, depth = eng.vibrato_params()
        a.set_vibrato(v, rate_hz=rate, depth_cents=depth)

        rate, depth = eng.tremolo_params()
        a.set_tremolo(v, rate_hz=rate, depth_pct=depth)

        rate, limit = eng.bend_params()
        a.set_bend(v, cents_per_s=rate, limit_cents=limit)

        rate, duty = eng.stutter_params()
        a.set_stutter(v, rate_hz=rate, duty_pct=duty)

        # Harmony = allocate a second voice and mirror pitch.
        h_freq = eng.harmony_freq_hz()
        if h_freq:
            if self._harmony_voice is None:
                self._harmony_voice = a.tone_sustained(
                    h_freq, wave=_wave_name(eng.waveform_id), channel="music"
                )
            else:
                a.set_freq(self._harmony_voice, h_freq)
        elif self._harmony_voice is not None:
            a.stop(voice=self._harmony_voice)
            self._harmony_voice = None

    # ---- LEDs -----------------------------------------------------------

    def _sync_leds(self):
        """Mirror engine state onto the arcade LEDs and NeoPixel sticks.

        Called from update() — diffed against cached state so we only issue
        I2C / NeoPixel writes when something actually changed.  No per-frame
        spam even when nothing is happening.
        """
        eng = self._engine
        active_step = eng.arcade_active_step()  # 0..4 held top of stack, or -1
        pitch_step = eng.pitch_idx % NOTES_PER_OCTAVE

        # --- Arcade LEDs: bright on the sounding note, dim glow on held but
        # inactive notes, dim glow on the pitch-matching step when nothing is
        # held (so the child sees "which button plays this note"), else off.
        if self._arcade is not None:
            any_held = active_step >= 0
            for i in range(NOTES_PER_OCTAVE):
                if i == active_step:
                    target = _ARC_ON
                elif eng.arcade_is_held(i):
                    target = _ARC_GLOW
                elif not any_held and i == pitch_step:
                    target = _ARC_GLOW
                else:
                    target = _ARC_OFF
                if target != self._last_arcade_led[i]:
                    self._last_arcade_led[i] = target
                    if target == _ARC_ON:
                        self._arcade.on(i)
                    elif target == _ARC_GLOW:
                        self._arcade.glow(i)
                    else:
                        self._arcade.off(i)

        # --- NeoPixel sticks: pitch-coloured pattern whose motion picks up the
        # current timbre, and whose speed bumps while motion effects are held.
        if neo.active:
            timbre = eng.timbre_idx
            pattern = _TIMBRE_PATTERN[timbre]
            speed = _TIMBRE_SPEED[timbre]
            # Motion effects (vibrato / tremolo / stutter) nudge the speed up so
            # the sticks visibly react when the child holds a mod button.
            if eng.is_effect(EFFECT_VIBRATO | EFFECT_TREMOLO | EFFECT_STUTTER):
                speed += 3
            r, g, b = _STEP_RGB[pitch_step]
            key = (pitch_step, pattern, speed)
            if key != self._last_stick_key:
                self._last_stick_key = key
                # Both sticks share the same animation — they're symmetric on
                # the lid, so animating them together reads as "one state".
                # Deliberately low — the sticks are peripheral ambience in this
                # mode, not the focus.  Anything above ~25 overpowers the TFT
                # backlight and the PCA9685-driven arcade button LEDs.
                stick_brightness = 18
                neo.zone_pattern(
                    neo.ZONE_STICK_A,
                    pattern,
                    speed=speed,
                    colour=(r, g, b),
                    brightness=stick_brightness,
                )
                neo.zone_pattern(
                    neo.ZONE_STICK_B,
                    pattern,
                    speed=speed,
                    colour=(r, g, b),
                    brightness=stick_brightness,
                )

    # ---- render ---------------------------------------------------------

    def render(self, tft, theme, frame):
        if self._pause.is_open:
            if self._dirty:
                tft.fill(theme.BLACK)
                self._full_clear = False
                self._render_static(tft, theme)
                self._dirty = False
            self._pause.render(tft, theme, frame)
            return

        if self._full_clear:
            tft.fill(theme.BLACK)
            self._full_clear = False
            self._dirty = True  # force full repaint of static regions

        if self._dirty:
            self._render_static(tft, theme)
            self._dirty = False

        # Scope is the only per-frame animation; keep it bounded to its strip
        # (≤ 50 rows = 1 DMA chunk per PERFORMANCE_GUIDELINES §3.05).
        self._render_scope_strip(tft, theme)

    def _render_static(self, tft, theme):
        """Blob + header + footer.  Called only when discrete engine state
        changes (pitch, timbre, effects mask, viz toggle, octave)."""
        w = theme.width
        h = theme.height
        eng = self._engine

        if eng.viz_big_scope:
            # Scope owns the middle; clear header/footer only.
            # (The scope itself will fill the middle on the next per-frame
            # call — we just black out the rest to avoid ghosting.)
            tft.fill_rect(0, _HEADER_H, w, h - _HEADER_H - _FOOTER_H, theme.BLACK)
        else:
            self._render_blob(tft, theme)

        self._render_header(tft, theme)
        self._render_footer(tft, theme)
        self._render_status_badges(tft, theme)

    def _render_scope_strip(self, tft, theme):
        """The animated region.  Picks primary-big or bottom-strip mode."""
        w = theme.width
        h = theme.height
        if self._engine.viz_big_scope:
            self._render_scope(
                tft, theme, 0, _HEADER_H, w, h - _HEADER_H - _FOOTER_H, big=True
            )
        else:
            self._render_scope(
                tft, theme, 0, h - _FOOTER_H - _SCOPE_H, w, _SCOPE_H, big=False
            )

    def _render_header(self, tft, theme):
        """Active-effect labels — short coloured pills, one per held effect.

        The secondary display carries the full 8-slot ribbon (visual state
        at a glance); here we only show the effects that are actually held
        so the child sees the *name* of each live effect right above the
        blob.  Lays out left-to-right, wrapping to a second row when more
        than four are held simultaneously (mini-button count is 8, so
        two rows are enough).
        """
        w = theme.width
        # Reserve the top-right corner for MUTE / GATE badges so they never
        # collide with the effect labels.
        badge_corner_w = 56
        avail_w = w - badge_corner_w - 4
        tft.fill_rect(0, 0, w, _HEADER_H, theme.BLACK)

        mask = self._engine.effects_mask
        # (button_index, label_text) for each currently-held effect.
        active = []
        for i, bit in enumerate(MINI_BUTTON_EFFECT):
            if mask & bit:
                active.append((i, t(MINI_BUTTON_LABEL_KEYS[i])))
        if not active:
            return

        pad_x = 3
        pad_y = 1
        gap = 3
        row_h = 10

        # Pack labels into rows — greedy fill, wrap to a second row when the
        # next pill would overflow the available width.
        row1, row2 = [], []
        row1_w = 0
        for idx, label in active:
            pill_w = text_width(label) + 2 * pad_x
            need = pill_w + (gap if row1 else 0)
            if row1_w + need <= avail_w:
                row1.append((idx, label, pill_w))
                row1_w += need
            else:
                row2.append((idx, label, pill_w))

        def _draw_row(row, y):
            if not row:
                return
            total_w = sum(pw for _, _, pw in row) + gap * (len(row) - 1)
            x = (avail_w - total_w) // 2
            if x < 2:
                x = 2
            for idx, label, pill_w in row:
                fg = theme.BTN_565[idx]
                # Colour the pill with the button's own colour so the child can
                # map "this label ↔ this physical button" by colour alone.
                tft.fill_rect(x, y, pill_w, row_h, fg)
                draw_text(tft, x + pad_x, y + pad_y, label, theme.BLACK, bg=fg)
                x += pill_w + gap

        if row2:
            # Two rows — fill the header.
            _draw_row(row1, 1)
            _draw_row(row2, 1 + row_h + 1)
        else:
            # One row — vertically centred in the header.
            _draw_row(row1, (_HEADER_H - row_h) // 2)

    def _render_blob(self, tft, theme):
        """Blob centred horizontally, y maps to pitch (higher = higher)."""
        w = theme.width
        h = theme.height
        eng = self._engine

        # Vertical band where the blob can move.
        band_top = _HEADER_H + 4
        band_bot = h - _FOOTER_H - _SCOPE_H - 4
        band_h = band_bot - band_top - _BLOB_SIZE
        if band_h < 0:
            band_h = 0

        # pitch_idx 0 → bottom of band; NUM_PITCHES-1 → top.
        frac = eng.pitch_idx / (NUM_PITCHES - 1) if NUM_PITCHES > 1 else 0
        y = band_bot - _BLOB_SIZE - int(frac * band_h)
        x = (w - _BLOB_SIZE) // 2

        # Clear the band so the previous blob position doesn't ghost.
        tft.fill_rect(0, band_top, w, band_bot - band_top, theme.BLACK)
        sprite = self._blob_sprites[eng.timbre_idx]
        blit_sprite(tft, sprite, x, y)

    def _render_scope(self, tft, theme, x, y, w, h, big):
        """Draw the oscilloscope trace.  Falls back to a flat line when the
        C scope isn't available (e.g. _audiomix without the scope tap)."""
        if self._have_scope and self._audio and self._voice is not None:
            try:
                self._audio.scope_peek(self._scope_buf)
            except Exception:
                pass
        gain = 768 if big else 256  # boost amplitude when the scope is big
        draw_waveform(
            tft, x, y, w, h, self._scope_buf, theme.CYAN, theme.BLACK, gain_q8=gain
        )

    def _render_status_badges(self, tft, theme):
        """Top-right pills showing which toggle switches are currently engaged.

        Only drawn when at least one badge is active, so most of the time this
        corner is clean.  Labels are translated via i18n and sit inside a
        coloured box that signals "flip the matching switch to turn off".
        """
        w = theme.width
        # Rightmost 56 px of the header are reserved for these badges — the
        # effect-label layout in _render_header() stops before this column so
        # the two never collide.  Each badge is 10 px tall; MUTE on top,
        # GATE underneath.
        pad_x = 4
        pad_y = 1
        gap = 2
        badge_h = 10
        y = 2
        # Always clear the corner first so cleared badges don't leave ghosts.
        corner_w = 56
        tft.fill_rect(w - corner_w, 0, corner_w, _HEADER_H, theme.BLACK)

        if self._muted:
            label = t("tone_explorer_status_mute")
            tw = text_width(label)
            bw = tw + 2 * pad_x
            x = w - bw - 2
            tft.fill_rect(x, y, bw, badge_h, theme.RED)
            draw_text(tft, x + pad_x, y + pad_y, label, theme.WHITE, bg=theme.RED)
            y += badge_h + gap
        if self._gate_mode:
            label = t("tone_explorer_status_gate")
            tw = text_width(label)
            bw = tw + 2 * pad_x
            x = w - bw - 2
            tft.fill_rect(x, y, bw, badge_h, theme.YELLOW)
            draw_text(tft, x + pad_x, y + pad_y, label, theme.BLACK, bg=theme.YELLOW)

        self._last_muted_painted = self._muted
        self._last_gate_painted = self._gate_mode

    def _render_footer(self, tft, theme):
        w = theme.width
        h = theme.height
        fy = h - _FOOTER_H
        tft.fill_rect(0, fy, w, _FOOTER_H, theme.BLACK)
        # Left: current pentatonic step (as a number 1..5 within the octave +
        # a small up-arrow for high octave).  Right: timbre label.
        eng = self._engine
        step = (eng.pitch_idx % NOTES_PER_OCTAVE) + 1
        octave_mark = "^" if eng.octave_shift else "_"
        left = "{}{}".format(octave_mark, step)
        draw_centered(tft, left, fy + 6, theme.WHITE, w // 2, scale=2)
        label = t(eng.timbre_label_key)
        draw_centered(tft, capitalize(label), fy + 6, theme.MUTED, w, scale=1)
        # Right-justify the label by writing into the right half via a second
        # call with an offset — simpler to just centre on w above and accept
        # overlap if the translation is long.  Keep the text short in sv.py.


# Convenience: map _audiomix wave constant → audio.py wave name.
def _wave_name(wave_id):
    if wave_id == 0:
        return "square"
    if wave_id == 2:
        return "sawtooth"
    if wave_id == 3:
        return "noise"
    if wave_id == 4:
        return "triangle"
    if wave_id == 5:
        return "noise_pitched"
    return "sine"
