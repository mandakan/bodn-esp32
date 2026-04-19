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
from bodn.ui.draw import waveform as draw_waveform
from bodn.i18n import t, capitalize
from bodn.tone_explorer_rules import (
    MINI_BUTTON_EFFECT,
    NOTES_PER_OCTAVE,
    NUM_PITCHES,
    NUM_TIMBRES,
    ToneExplorer,
)

_BLOB_SIZE = const(96)
_SCOPE_H = const(48)
_SCOPE_SAMPLES = const(256)   # samples drawn per frame (<= _audiomix.SCOPE_SAMPLES)
_HEADER_H = const(22)
_FOOTER_H = const(26)

# Left encoder = pitch, right encoder = timbre.
_ENC_PITCH = const(0)  # config.ENC_NAV
_ENC_TIMBRE = const(1)  # config.ENC_A

# Switch indices in inp.sw — see main.input_scan_task for the MCP layout.
_SW_VIZ_LEFT = const(2)   # MCP2 SW_LEFT — True = scope on primary
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
            w = r + dy          # narrows as we go up
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

    # ---- lifecycle ------------------------------------------------------

    def enter(self, manager):
        self._manager = manager
        self._pause.set_manager(manager)
        self._dirty = True
        self._full_clear = True
        self._last_mask = -1
        self._last_waveform = -1
        self._last_eff_freq = 0

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

        # Start the sustained voice.  Initial pitch is the engine's default.
        if self._audio:
            try:
                self._voice = self._audio.tone_sustained(
                    self._engine.base_freq_hz,
                    wave=_wave_name(self._engine.waveform_id),
                    channel="music",
                )
                # Zero gain until the first interaction — avoids a startup chirp.
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

        # Arcade buttons — snap to pentatonic step.
        for i in range(min(NOTES_PER_OCTAVE, len(inp.arc_just_pressed))):
            if inp.arc_just_pressed[i]:
                eng.on_arcade_press(i)
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

        # Push status to the secondary display.
        if self._secondary and hasattr(self._secondary, "update_state"):
            self._secondary.update_state(
                eng.pitch_idx,
                eng.timbre_idx,
                eng.effects_mask,
                eng.viz_big_scope,
            )

    def _sync_audio(self):
        """Translate engine state into C-mixer commands.  Idempotent — only
        sends calls when the relevant field has changed."""
        if not self._audio or self._voice is None:
            return
        eng = self._engine
        eff_freq = eng.effective_freq_hz()
        if eff_freq != self._last_eff_freq:
            self._audio.set_freq(self._voice, eff_freq)
            self._last_eff_freq = eff_freq

        # Re-trigger the voice when waveform changes (different generator path).
        if eng.waveform_id != self._last_waveform:
            self._audio.tone_sustained(
                eff_freq, wave=_wave_name(eng.waveform_id),
                channel="music", voice=self._voice,
            )
            self._last_waveform = eng.waveform_id
            self._last_mask = -1  # force re-apply of mods after retrigger

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
                    h_freq, wave=_wave_name(eng.waveform_id), channel="music")
            else:
                a.set_freq(self._harmony_voice, h_freq)
        elif self._harmony_voice is not None:
            a.stop(voice=self._harmony_voice)
            self._harmony_voice = None

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
            self._dirty = True   # force full repaint of static regions

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

    def _render_scope_strip(self, tft, theme):
        """The animated region.  Picks primary-big or bottom-strip mode."""
        w = theme.width
        h = theme.height
        if self._engine.viz_big_scope:
            self._render_scope(tft, theme, 0, _HEADER_H,
                               w, h - _HEADER_H - _FOOTER_H, big=True)
        else:
            self._render_scope(tft, theme, 0, h - _FOOTER_H - _SCOPE_H,
                               w, _SCOPE_H, big=False)

    def _render_header(self, tft, theme):
        """Active-effect row — one small block per held effect."""
        w = theme.width
        tft.fill_rect(0, 0, w, _HEADER_H, theme.BLACK)
        # 8 slots spaced across the width; lit if the matching bit is set.
        slot_w = w // 10
        y = 6
        for i, bit in enumerate(MINI_BUTTON_EFFECT):
            x = slot_w + i * slot_w
            col = theme.BTN_565[i] if (self._engine.effects_mask & bit) else theme.DIM
            tft.fill_rect(x, y, slot_w - 4, 10, col)

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
        gain = 768 if big else 256   # boost amplitude when the scope is big
        draw_waveform(tft, x, y, w, h, self._scope_buf,
                      theme.CYAN, theme.BLACK, gain_q8=gain)

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
        draw_centered(tft, capitalize(label), fy + 6, theme.MUTED,
                      w, scale=1)
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
    return "sine"
