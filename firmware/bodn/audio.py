# bodn/audio.py — AudioEngine for Bodn ESP32
#
# Native backend (_audiomix C module): mixing runs on core 0 in a FreeRTOS
# task, completely independent of the Python VM on core 1.  16 uniform voices.
#
# The public API allocates voices from named pools by convention:
#   voices 0-9:   "sfx" pool (round-robin, steal-oldest)
#   voices 10-13: "music" pool
#   voice  14-15: "ui" (reserved for TTS/feedback)

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

try:
    from micropython import const
except ImportError:

    def const(x):
        return x


import _audiomix

from bodn import tones
from bodn.wav import WavReader

# ---------------------------------------------------------------------------
# Voice layout (conventions — not enforced by C module)
# ---------------------------------------------------------------------------

_NUM_VOICES = const(16)

# Pool ranges (inclusive start, exclusive end)
_SFX_START = const(0)
_SFX_END = const(10)
_MUSIC_START = const(10)
_MUSIC_END = const(14)
_UI_START = const(14)
_UI_END = const(16)

# Channel name → pool range
_POOLS = {
    "sfx": (_SFX_START, _SFX_END),
    "music": (_MUSIC_START, _MUSIC_END),
    "ui": (_UI_START, _UI_END),
}

# Legacy aliases — kept for test compatibility
V_MUSIC = const(0)
V_SFX_BASE = const(1)
V_SFX_END = const(5)
V_UI = const(5)
CH_MUSIC = V_MUSIC
CH_SFX = V_SFX_BASE
CH_UI = V_UI
CHANNEL_NAMES = {"music": V_MUSIC, "sfx": V_SFX_BASE, "ui": V_UI}

_MONO_BUF_SIZE = const(
    512
)  # bytes per mono read buffer (256 samples at 16-bit = 16 ms)

# Default gain (fixed-point 16.16) — ~70%
_GAIN_DEFAULT = const(45875)

# Legacy gain constants (for test compatibility)
_GAIN_MUSIC = _GAIN_DEFAULT
_GAIN_MUSIC_DUCKED = const(16384)
_GAIN_SFX = _GAIN_DEFAULT
_GAIN_UI = _GAIN_DEFAULT

# Wave name → C enum mapping
_WAVE_MAP = {"square": 0, "sine": 1, "sawtooth": 2, "noise": 3}


# ---------------------------------------------------------------------------
# Pure-Python DSP helpers (used by host tests only)
# ---------------------------------------------------------------------------


def _apply_volume_py(buf, n_bytes, mult):
    """Pure-Python volume scaling (host tests)."""
    for i in range(0, n_bytes, 2):
        lo = buf[i]
        hi = buf[i + 1]
        val = lo | (hi << 8)
        if val >= 0x8000:
            val -= 0x10000
        val = (val * mult) >> 16
        val = val & 0xFFFF
        buf[i] = val & 0xFF
        buf[i + 1] = (val >> 8) & 0xFF


def _mix_add_py(dst, src, n_bytes):
    """Pure-Python saturating int16 mix (host tests)."""
    for i in range(0, n_bytes, 2):
        d_lo = dst[i]
        d_hi = dst[i + 1]
        d_val = d_lo | (d_hi << 8)
        if d_val >= 0x8000:
            d_val -= 0x10000
        s_lo = src[i]
        s_hi = src[i + 1]
        s_val = s_lo | (s_hi << 8)
        if s_val >= 0x8000:
            s_val -= 0x10000
        total = d_val + s_val
        if total > 32767:
            total = 32767
        elif total < -32768:
            total = -32768
        total = total & 0xFFFF
        dst[i] = total & 0xFF
        dst[i + 1] = (total >> 8) & 0xFF


_FADE_SAMPLES = const(16)  # 16 samples @ 16kHz = 1ms


def _apply_fade(buf, n_bytes, fade_in, fade_out):
    """Apply linear fade-in and/or fade-out to int16 samples in buf."""
    n_samples = n_bytes // 2
    fade = _FADE_SAMPLES
    if fade_in:
        fin = min(fade, n_samples)
        for i in range(fin):
            off = i * 2
            lo = buf[off]
            hi = buf[off + 1]
            val = lo | (hi << 8)
            if val >= 0x8000:
                val -= 0x10000
            val = val * i // max(1, fin - 1) if fin > 1 else 0
            val = val & 0xFFFF
            buf[off] = val & 0xFF
            buf[off + 1] = (val >> 8) & 0xFF
    if fade_out:
        fout = min(fade, n_samples)
        start = n_samples - fout
        for i in range(fout):
            off = (start + i) * 2
            lo = buf[off]
            hi = buf[off + 1]
            val = lo | (hi << 8)
            if val >= 0x8000:
                val -= 0x10000
            val = val * (fout - 1 - i) // max(1, fout - 1)
            val = val & 0xFFFF
            buf[off] = val & 0xFF
            buf[off + 1] = (val >> 8) & 0xFF


# ---------------------------------------------------------------------------
# Source classes (WAV streaming used by native ring buffer feeder)
# ---------------------------------------------------------------------------


class ToneSource:
    """Adapter that wraps tones.generate() with the same interface as WavReader."""

    def __init__(self, freq_hz, duration_ms, wave, sample_rate=16000):
        self.freq_hz = freq_hz
        self.wave = wave
        self.sample_rate = sample_rate
        self._total_bytes = (sample_rate * duration_ms // 1000) * 2
        self._bytes_left = self._total_bytes
        self._phase = 0
        self._first_chunk = True

    def read_chunk(self, buf):
        if self._bytes_left <= 0:
            return 0
        to_fill = min(len(buf), self._bytes_left)
        to_fill = (to_fill // 2) * 2
        n, self._phase = tones.generate(
            buf, self.freq_hz, self.sample_rate, self.wave, self._phase
        )
        n = min(n, to_fill)
        self._bytes_left -= n
        is_first = self._first_chunk
        is_last = self._bytes_left <= 0
        if is_first or is_last:
            _apply_fade(buf, n, is_first, is_last)
            self._first_chunk = False
        return n

    def seek_start(self):
        self._bytes_left = self._total_bytes
        self._phase = 0
        self._first_chunk = True


class SequenceSource:
    """Plays a list of (freq_hz, duration_ms, wave) steps in order."""

    def __init__(self, steps, sample_rate=16000):
        self._steps = steps
        self._sample_rate = sample_rate
        self._idx = 0
        self._current = self._make_tone(0) if steps else None

    def _make_tone(self, idx):
        if idx >= len(self._steps):
            return None
        freq, dur, wave = self._steps[idx]
        if freq <= 0:
            return ToneSource(1, dur, "square", self._sample_rate)
        return ToneSource(freq, dur, wave, self._sample_rate)

    def read_chunk(self, buf):
        while self._current is not None:
            n = self._current.read_chunk(buf)
            if n > 0:
                if self._steps[self._idx][0] <= 0:
                    for i in range(n):
                        buf[i] = 0
                return n
            self._idx += 1
            self._current = self._make_tone(self._idx)
        return 0

    def seek_start(self):
        self._idx = 0
        self._current = self._make_tone(0)


class MemorySource:
    """Plays raw 16-bit mono PCM data from a pre-loaded bytearray."""

    __slots__ = ("_data", "_len", "_pos")

    def __init__(self, data):
        self._data = memoryview(data)
        self._len = len(data)
        self._pos = 0

    def read_chunk(self, buf):
        if self._pos >= self._len:
            return 0
        n = min(len(buf), self._len - self._pos)
        n = (n // 2) * 2
        buf[:n] = self._data[self._pos : self._pos + n]
        self._pos += n
        return n

    def seek_start(self):
        self._pos = 0


# ---------------------------------------------------------------------------
# Streaming voice state (Python-side bookkeeping for WAV ring buffer feed)
# ---------------------------------------------------------------------------


class _StreamingVoice:
    """Tracks a WAV file being streamed into a native ring buffer."""

    __slots__ = ("idx", "wav_reader", "file_obj", "feed_buf", "loop")

    def __init__(self, idx, wav_reader, file_obj, feed_buf, loop):
        self.idx = idx
        self.wav_reader = wav_reader
        self.file_obj = file_obj
        self.feed_buf = feed_buf
        self.loop = loop

    def close(self):
        if self.file_obj:
            try:
                self.file_obj.close()
            except Exception:
                pass
            self.file_obj = None
        self.wav_reader = None


# ---------------------------------------------------------------------------
# AudioEngine — public API (native _audiomix backend)
# ---------------------------------------------------------------------------


class AudioEngine:
    """Multi-voice audio engine using the native _audiomix C mixer on core 0.

    16 uniform voices allocated from named pools by convention:
      "sfx"   — voices 0-9   (general sound effects, round-robin)
      "music" — voices 10-13 (background music, loops)
      "ui"    — voices 14-15 (TTS, UI feedback)

    Use voice=N for direct voice access (e.g. sequencer clock integration).
    """

    def __init__(self, native=True, **kwargs):
        bck = kwargs.get("bck", 13)
        ws = kwargs.get("ws", 45)
        din = kwargs.get("din", 7)
        amp = kwargs.get("amp", 3)
        rate = kwargs.get("rate", 16000)
        ibuf = kwargs.get("ibuf", 16384)
        _audiomix.init(bck=bck, ws=ws, din=din, amp=amp, rate=rate, ibuf=ibuf)
        self._streaming = []
        self._buf_refs = {}
        self._feed_buf = bytearray(_MONO_BUF_SIZE)
        self._num_voices = _audiomix.NUM_VOICES

        self._seq_counter = 0
        self._volume = 10
        self._burst_max = 0

        # Per-pool round-robin counters
        self._pool_rr = {}

    @property
    def volume(self):
        return _audiomix.get_volume()

    @volume.setter
    def volume(self, val):
        val = max(0, min(100, val))
        self._volume = val
        _audiomix.set_volume(val)

    @property
    def burst(self):
        return self._burst_max

    @burst.setter
    def burst(self, val):
        self._burst_max = max(0, min(6, val))

    @property
    def playing(self):
        """True if any voice is active."""
        for i in range(self._num_voices):
            if _audiomix.voice_active(i):
                return True
        return False

    def channel_active(self, channel):
        """True if any voice in the given channel pool is active."""
        start, end = self._pool_range(channel)
        for i in range(start, end):
            if _audiomix.voice_active(i):
                return True
        return False

    @property
    def sfx_active(self):
        """Number of SFX pool voices currently playing."""
        start, end = self._pool_range("sfx")
        count = 0
        for i in range(start, end):
            if _audiomix.voice_active(i):
                count += 1
        return count

    # -----------------------------------------------------------------------
    # Voice allocation
    # -----------------------------------------------------------------------

    def _pool_range(self, channel):
        """Return (start, end) voice indices for a channel pool."""
        return _POOLS.get(channel, (_SFX_START, _SFX_END))

    def _allocate_voice(self, channel):
        """Allocate a voice from a pool. Returns voice index."""
        start, end = self._pool_range(channel)
        pool_size = end - start

        # Find a free voice
        for i in range(start, end):
            if not _audiomix.voice_active(i):
                return i

        # All busy — round-robin steal oldest
        rr = self._pool_rr.get(channel, start)
        idx = rr
        # Advance round-robin
        self._pool_rr[channel] = start + ((rr - start + 1) % pool_size)
        self._stop_voice(idx)
        return idx

    def _stop_voice(self, idx):
        """Stop a single voice by index."""
        _audiomix.voice_stop(idx)
        self._stop_streaming(idx)

    def _stop_streaming(self, idx):
        """Remove any active streaming voice for the given index.

        Mutates the list in-place (never replaces the reference) so the
        async start() loop's iteration stays valid.

        Does NOT drop _buf_refs — callers that replace the buffer set
        _buf_refs[idx] themselves; callers that just stop a voice call
        _drop_buf_ref() separately.  This prevents a window where the
        old buffer has no Python reference while the C mixer may still
        be reading from it.
        """
        i = 0
        while i < len(self._streaming):
            sv = self._streaming[i]
            if sv.idx == idx:
                sv.close()
                self._streaming.pop(i)
            else:
                i += 1

    def _resolve_voice(self, voice, channel):
        """Resolve a voice= or channel= argument to a voice index."""
        if voice is not None:
            # Direct voice access — stop existing and return
            self._stop_voice(voice)
            return voice
        return self._allocate_voice(channel or "sfx")

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def play(self, path, loop=False, channel="sfx", voice=None):
        """Play a WAV file."""
        idx = self._resolve_voice(voice, channel)
        self._stop_streaming(idx)
        try:
            f = open(path, "rb")
            wav = WavReader(f)
            _audiomix.voice_start_stream(idx, loop)
            sv = _StreamingVoice(idx, wav, f, self._feed_buf, loop)
            self._fill_ringbuf(sv)
            self._streaming.append(sv)
        except Exception as e:
            print("audio.play error:", e)
            _audiomix.voice_stop(idx)

    def play_buffer(self, data, loop=False, channel="sfx", voice=None):
        """Play pre-loaded PCM data (bytearray)."""
        idx = self._resolve_voice(voice, channel)
        self._stop_streaming(idx)
        # Set the new buffer reference BEFORE telling C to play.
        # voice_play_buffer atomically swaps source_type via the
        # writing flag, so the mixer won't read the old buf_ptr
        # after this call.  Keeping _buf_refs[idx] = data ensures
        # GC can't free the buffer while C is using it.
        self._buf_refs[idx] = data
        _audiomix.voice_play_buffer(idx, data, len(data), loop)

    def tone(self, freq_hz, duration_ms=200, wave="square", channel="sfx", voice=None):
        """Play a procedural tone."""
        idx = self._resolve_voice(voice, channel)
        self._stop_streaming(idx)
        wave_id = _WAVE_MAP.get(wave, 0)
        _audiomix.voice_tone(idx, freq_hz, duration_ms, wave_id)

    def play_sound(self, name, channel="ui", voice=None):
        """Play a named sound from the sound design system."""
        from bodn.sounds import WAV, SOUNDS

        path = WAV.get("sfx", {}).get(name)
        if path:
            self.play(path, channel=channel, voice=voice)
            return

        steps = SOUNDS.get(name)
        if not steps:
            return

        idx = self._resolve_voice(voice, channel)
        self._stop_streaming(idx)
        packed = bytearray(len(steps) * 5)
        for i, (freq, dur, *rest) in enumerate(steps):
            w = rest[0] if rest else "sine"
            off = i * 5
            f = max(0, freq)
            packed[off] = f & 0xFF
            packed[off + 1] = (f >> 8) & 0xFF
            packed[off + 2] = dur & 0xFF
            packed[off + 3] = (dur >> 8) & 0xFF
            packed[off + 4] = _WAVE_MAP.get(w, 1)
        _audiomix.voice_sequence(idx, packed)

    def boop(self):
        """Quick UI feedback beep."""
        self.play_sound("boop")

    # -----------------------------------------------------------------------
    # Sustained tones + modulation layer (for expressive modes like Tone Lab)
    # -----------------------------------------------------------------------

    def tone_sustained(self, freq_hz, wave="sine", channel="sfx", voice=None):
        """Start a tone that plays until stopped.  Returns the voice index.

        Use set_freq() for phase-preserving pitch changes, and the
        set_vibrato/set_tremolo/set_bend/set_stutter helpers to layer effects.
        Harmony = call tone_sustained() a second time on a different voice.
        """
        idx = self._resolve_voice(voice, channel)
        self._stop_streaming(idx)
        wave_id = _WAVE_MAP.get(wave, 1)
        _audiomix.voice_tone_sustained(idx, freq_hz, wave_id)
        return idx

    def set_freq(self, voice, freq_hz):
        """Phase-preserving pitch change for a sustained tone."""
        _audiomix.voice_set_freq(voice, freq_hz)

    def set_vibrato(self, voice, rate_hz=5.0, depth_cents=30):
        """Pitch LFO.  rate_hz=0 disables.  depth_cents is ±."""
        _audiomix.voice_set_pitch_lfo(voice, int(rate_hz * 100), int(depth_cents))

    def set_tremolo(self, voice, rate_hz=5.0, depth_pct=40):
        """Amplitude LFO.  rate_hz=0 disables.  depth_pct is 0..100."""
        depth = max(0, min(100, int(depth_pct)))
        _audiomix.voice_set_amp_lfo(voice, int(rate_hz * 100), depth * 32767 // 100)

    def set_bend(self, voice, cents_per_s=0, limit_cents=0):
        """Pitch ramp: accumulates at cents_per_s, clamped to ±limit_cents.

        Positive cents_per_s slides up, negative slides down.
        cents_per_s=0 clears the current bend offset.
        """
        _audiomix.voice_set_bend(voice, int(cents_per_s), int(limit_cents))

    def set_stutter(self, voice, rate_hz=8.0, duty_pct=50):
        """Amp gate: samples are zeroed during the 'off' fraction of cycle."""
        duty = max(0, min(100, int(duty_pct)))
        _audiomix.voice_set_stutter(voice, int(rate_hz * 100), duty * 32767 // 100)

    def clear_mods(self, voice):
        """Disable all modulation effects on a voice."""
        _audiomix.voice_clear_mods(voice)

    def scope_peek(self, dst_buf):
        """Copy the most recent post-mix mono samples into dst_buf.

        dst_buf is a bytearray of int16 samples (length must be a multiple
        of 2).  Up to _audiomix.SCOPE_SAMPLES samples are available.
        """
        return _audiomix.scope_peek(dst_buf)

    def stop(self, channel=None, voice=None):
        """Stop playback. voice=N stops one voice, channel stops a pool, None stops all."""
        if voice is not None:
            self._stop_voice(voice)
            return

        if channel is None:
            for i in range(self._num_voices):
                _audiomix.voice_stop(i)
            for sv in self._streaming:
                sv.close()
            self._streaming.clear()
            self._buf_refs.clear()
        else:
            start, end = self._pool_range(channel)
            for i in range(start, end):
                _audiomix.voice_stop(i)
                self._stop_streaming(i)
                self._buf_refs.pop(i, None)

    # -----------------------------------------------------------------------
    # Ring buffer feeder
    # -----------------------------------------------------------------------

    def _fill_ringbuf(self, sv):
        """Fill a streaming voice's ring buffer as much as possible."""
        while True:
            space = _audiomix.ringbuf_space(sv.idx)
            if space < _MONO_BUF_SIZE:
                break
            n = sv.wav_reader.read_chunk(sv.feed_buf)
            if n > 0:
                _audiomix.voice_feed(sv.idx, sv.feed_buf, n)
            else:
                if sv.loop:
                    sv.wav_reader.seek_start()
                    _audiomix.voice_eof(sv.idx)
                else:
                    _audiomix.voice_eof(sv.idx)
                break

    # -----------------------------------------------------------------------
    # start() — main async loop (feeds ring buffers for streaming voices)
    # -----------------------------------------------------------------------

    async def start(self):
        """Start the audio engine."""
        print(
            "AudioEngine started (native, core 0, {} voices)".format(self._num_voices)
        )
        sleep_ms = asyncio.sleep_ms
        while True:
            if self._streaming:
                dead = []
                for sv in self._streaming:
                    if not _audiomix.voice_active(sv.idx):
                        dead.append(sv)
                        continue
                    self._fill_ringbuf(sv)
                for sv in dead:
                    sv.close()
                    try:
                        self._streaming.remove(sv)
                    except ValueError:
                        pass  # already removed by _stop_streaming
                    self._buf_refs.pop(sv.idx, None)
                await sleep_ms(16)
            else:
                await sleep_ms(100)
