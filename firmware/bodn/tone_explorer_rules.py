# bodn/tone_explorer_rules.py — Tone Lab state model (pure logic)
#
# Free-play mode: one sustained voice, pentatonic pitch + morphable timbre +
# live modulation effects held on the 8 mini buttons.  Designed for 4-year-olds
# per docs/UX_GUIDELINES.md: one concept (sound-shape), direct contingency,
# never a "wrong" note (strict pentatonic).
#
# Scientific framings:
#   - Bouba/Kiki cross-modal sound-shape binding (Köhler 1929; Maurer 2006)
#     drives the encoder-controlled timbre morph matched to blob shape.
#   - Pitch-height and pitch-brightness correspondences (Dolscheid 2014)
#     drive the LED strip pitch trail and blob vertical position.
#   - Contingency detection (Watson 1985) — every input has one unambiguous
#     audible + visual effect.
#
# No hardware imports — testable on host with pytest.

try:
    from micropython import const
except ImportError:

    def const(x):
        return x


# ---------------------------------------------------------------------------
# Pentatonic scale (major, 2 octaves starting at C4).
# Frequencies in integer Hz — the mixer takes uint32 Hz anyway, so sub-Hz
# precision would just be rounded off.
# ---------------------------------------------------------------------------

# Low octave: C4 D4 E4 G4 A4
# High octave: C5 D5 E5 G5 A5
PENTATONIC_HZ = (262, 294, 330, 392, 440, 523, 587, 659, 784, 880)
NUM_PITCHES = const(10)
NOTES_PER_OCTAVE = const(5)

# Arcade button colours align with pitch (green=lowest, red=highest).
# ARCADE_COLORS in config.py: ("green", "blue", "white", "yellow", "red").
# Matching that order maps low→high pitch left→right.

# Timbre morph — 5 steps, each picks a waveform and a blob-shape sprite.
# Waveform IDs match _audiomix.WAVE_* constants.
_W_SQUARE = const(0)
_W_SINE = const(1)
_W_SAW = const(2)
_W_TRIANGLE = const(4)
_W_NOISE_PITCHED = const(5)

# (waveform_id, blob_shape_id, display_label_i18n_key)
TIMBRE_TABLE = (
    (_W_SINE, 0, "tone_explorer_timbre_smooth"),
    (_W_TRIANGLE, 1, "tone_explorer_timbre_soft"),
    (_W_SAW, 2, "tone_explorer_timbre_bright"),
    (_W_SQUARE, 3, "tone_explorer_timbre_edgy"),
    (_W_NOISE_PITCHED, 4, "tone_explorer_timbre_fuzzy"),
)
NUM_TIMBRES = const(5)

# ---------------------------------------------------------------------------
# Effect bitmask (mini button index -> bit).  Bit N = mini button N held.
# ---------------------------------------------------------------------------

EFFECT_VIBRATO = const(1 << 0)
EFFECT_TREMOLO = const(1 << 1)
EFFECT_BEND_UP = const(1 << 2)
EFFECT_BEND_DOWN = const(1 << 3)
EFFECT_OCTAVE_UP = const(1 << 4)
EFFECT_OCTAVE_DOWN = const(1 << 5)
EFFECT_STUTTER = const(1 << 6)
EFFECT_HARMONY = const(1 << 7)

# Mini button index → effect bit.  Physical left-to-right.
MINI_BUTTON_EFFECT = (
    EFFECT_VIBRATO,
    EFFECT_TREMOLO,
    EFFECT_BEND_UP,
    EFFECT_BEND_DOWN,
    EFFECT_OCTAVE_UP,
    EFFECT_OCTAVE_DOWN,
    EFFECT_STUTTER,
    EFFECT_HARMONY,
)

# Short display labels for each mini-button effect (i18n keys, parallel to
# MINI_BUTTON_EFFECT).  Rendered on the secondary display so the child (and
# parent) can see *which* effect is active while buttons are held.
MINI_BUTTON_LABEL_KEYS = (
    "tone_explorer_effect_vibrato",
    "tone_explorer_effect_tremolo",
    "tone_explorer_effect_bend_up",
    "tone_explorer_effect_bend_down",
    "tone_explorer_effect_octave_up",
    "tone_explorer_effect_octave_down",
    "tone_explorer_effect_stutter",
    "tone_explorer_effect_harmony",
)

# ---------------------------------------------------------------------------
# Effect parameters (tuneable — defaults chosen for clear, kid-friendly feel).
# Kept as a dict so the screen or a future settings page can override per
# session without touching the rule engine.
# ---------------------------------------------------------------------------

DEFAULT_PARAMS = {
    # Vibrato
    "vibrato_rate_hz": 5.0,
    "vibrato_depth_cents": 30,
    # Tremolo
    "tremolo_rate_hz": 5.0,
    "tremolo_depth_pct": 40,
    # Bend (cents/s ramp, clamped at limit)
    "bend_rate_cents_per_s": 500,
    "bend_limit_cents": 1200,
    # Stutter
    "stutter_rate_hz": 8.0,
    "stutter_duty_pct": 50,
    # Octave jump (semitones above/below base; harmony fifth interval)
    "octave_jump_cents": 1200,
    "harmony_interval_cents": 702,  # 3:2 perfect fifth
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ToneExplorer:
    """State model for the Tone Lab mode.

    Controllers feed events via the on_*() methods; renderers read state.
    The engine never talks to audio or display — that's the screen's job.
    """

    def __init__(self, params=None):
        p = dict(DEFAULT_PARAMS)
        if params:
            p.update(params)
        self.params = p

        # Free play starts at middle of the low octave (G4 — pentatonic index 3).
        self.pitch_idx = 3
        self.timbre_idx = 0
        self.octave_shift = 0  # -1, 0, +1 from SW_RIGHT toggle
        self.effects_mask = 0  # bitmask of EFFECT_*
        self.viz_big_scope = (
            False  # SW_LEFT: False=blob on primary, True=scope on primary
        )
        self.playing = False  # becomes True on first interaction

        # Last-note-priority monosynth stack.  Stores arcade step indices
        # (0..NOTES_PER_OCTAVE-1, unscaled by octave_shift) in press order.
        # The top of the stack drives pitch_idx; releasing the top falls back
        # to the previous held note — MS-20 / SH-101 style.
        self._arcade_stack = []

    # ---- Input events ----------------------------------------------------

    def on_arcade(self, idx, pressed):
        """Arcade button 0..4 press/release — last-note-priority voicing.

        Holding a second button while the first is held plays the second note;
        releasing it falls back to the still-held first.  Releasing the final
        held button leaves pitch_idx at the last sounding note (the screen's
        gate logic handles whether audio is still produced).
        """
        if not (0 <= idx < NOTES_PER_OCTAVE):
            return
        stack = self._arcade_stack
        if pressed:
            # Re-pressing a held button shouldn't duplicate it on the stack.
            if idx in stack:
                stack.remove(idx)
            stack.append(idx)
            self._apply_arcade_top()
            self.playing = True
        else:
            if idx in stack:
                stack.remove(idx)
            if stack:
                self._apply_arcade_top()

    def _apply_arcade_top(self):
        """Snap pitch to the top of the arcade held-stack."""
        if not self._arcade_stack:
            return
        base = 0 if self.octave_shift <= 0 else NOTES_PER_OCTAVE
        self.pitch_idx = base + self._arcade_stack[-1]

    def arcade_active_step(self):
        """Return the currently sounding arcade step (0..4), or -1 if none held.

        Readers (e.g. LED layer) use this to light the button that's actually
        driving the pitch right now, not just the most recently pressed one.
        """
        if not self._arcade_stack:
            return -1
        return self._arcade_stack[-1]

    def arcade_is_held(self, idx):
        """True if arcade step `idx` is currently held."""
        return idx in self._arcade_stack

    def on_pitch_delta(self, delta):
        """Left encoder: step pentatonic pitch by `delta` notes (clamped)."""
        if delta == 0:
            return
        new_idx = self.pitch_idx + delta
        if new_idx < 0:
            new_idx = 0
        elif new_idx >= NUM_PITCHES:
            new_idx = NUM_PITCHES - 1
        if new_idx != self.pitch_idx:
            self.pitch_idx = new_idx
            self.playing = True

    def on_timbre_delta(self, delta):
        """Right encoder: step timbre by `delta` (clamped to 0..NUM_TIMBRES-1)."""
        if delta == 0:
            return
        new_idx = self.timbre_idx + delta
        if new_idx < 0:
            new_idx = 0
        elif new_idx >= NUM_TIMBRES:
            new_idx = NUM_TIMBRES - 1
        self.timbre_idx = new_idx

    def on_mini_button(self, idx, pressed):
        """Mini button 0..7 hold-to-apply effect.  True = press, False = release."""
        if not (0 <= idx < len(MINI_BUTTON_EFFECT)):
            return
        bit = MINI_BUTTON_EFFECT[idx]
        if pressed:
            self.effects_mask |= bit
            self.playing = True
        else:
            self.effects_mask &= ~bit

    def on_octave_toggle(self, high):
        """SW_RIGHT toggle: True = high octave, False = low octave."""
        new_shift = 1 if high else 0
        if new_shift != self.octave_shift:
            # Preserve the same scale-step position when shifting octaves.
            step = self.pitch_idx % NOTES_PER_OCTAVE
            self.pitch_idx = step + new_shift * NOTES_PER_OCTAVE
            self.octave_shift = new_shift

    def on_viz_toggle(self, big_scope):
        """SW_LEFT toggle: True = oscilloscope fills primary, False = blob."""
        self.viz_big_scope = bool(big_scope)

    def on_reset_timbre(self):
        """Right encoder push: snap timbre back to smooth sine."""
        self.timbre_idx = 0

    def on_panic(self):
        """Left encoder push: silence everything, release all effects."""
        self.effects_mask = 0
        self.playing = False
        self._arcade_stack = []

    # ---- Derived state (read by screen / audio adapter) ------------------

    @property
    def base_freq_hz(self):
        """Current pentatonic pitch in Hz, before effect modulation."""
        return PENTATONIC_HZ[self.pitch_idx]

    @property
    def waveform_id(self):
        return TIMBRE_TABLE[self.timbre_idx][0]

    @property
    def blob_shape_id(self):
        return TIMBRE_TABLE[self.timbre_idx][1]

    @property
    def timbre_label_key(self):
        return TIMBRE_TABLE[self.timbre_idx][2]

    def is_effect(self, bit):
        return bool(self.effects_mask & bit)

    # ---- Effect-parameter snapshot (for the audio adapter to apply) ------

    def vibrato_params(self):
        """Return (rate_hz, depth_cents).  (0, 0) if inactive."""
        if self.is_effect(EFFECT_VIBRATO):
            return self.params["vibrato_rate_hz"], self.params["vibrato_depth_cents"]
        return (0.0, 0)

    def tremolo_params(self):
        if self.is_effect(EFFECT_TREMOLO):
            return self.params["tremolo_rate_hz"], self.params["tremolo_depth_pct"]
        return (0.0, 0)

    def bend_params(self):
        """Return (cents_per_s, limit_cents).  Sign encodes direction."""
        rate = self.params["bend_rate_cents_per_s"]
        limit = self.params["bend_limit_cents"]
        if self.is_effect(EFFECT_BEND_UP):
            return (rate, limit)
        if self.is_effect(EFFECT_BEND_DOWN):
            return (-rate, limit)
        return (0, 0)

    def stutter_params(self):
        if self.is_effect(EFFECT_STUTTER):
            return self.params["stutter_rate_hz"], self.params["stutter_duty_pct"]
        return (0.0, 0)

    def octave_jump_cents(self):
        """While held, transpose the base pitch by this many cents."""
        cents = self.params["octave_jump_cents"]
        if self.is_effect(EFFECT_OCTAVE_UP):
            return cents
        if self.is_effect(EFFECT_OCTAVE_DOWN):
            return -cents
        return 0

    def harmony_freq_hz(self):
        """Return the companion voice frequency, or 0 if harmony off."""
        if not self.is_effect(EFFECT_HARMONY):
            return 0
        # 3:2 perfect fifth — nice consonance, always pentatonic-compatible.
        return (self.base_freq_hz * 3) // 2

    def effective_freq_hz(self):
        """Base pitch × octave-jump effect.  Vibrato/bend are applied by the
        mixer's modulation layer and do NOT appear here."""
        freq = self.base_freq_hz
        jump = self.octave_jump_cents()
        if jump > 0:
            freq *= 2
        elif jump < 0:
            freq //= 2
        return freq
