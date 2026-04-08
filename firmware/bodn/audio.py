# bodn/audio.py — AudioEngine for Bodn ESP32
#
# Two backends:
#
# 1. Native (_audiomix C module): mixing runs on core 1 in a FreeRTOS task,
#    completely independent of the Python VM.  WAV data is fed through
#    per-voice ring buffers; tones and pre-loaded buffers are handled
#    entirely in C.
#
# 2. Fallback (viper/pure-Python): DMA-driven via micropython.schedule()
#    IRQ callbacks on core 0.  Used on stock firmware or host tests.
#
# The public API is identical regardless of backend.
# Mixes up to 6 simultaneous voices: 1 music + 4 SFX pool + 1 UI.

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

try:
    import micropython
    from micropython import const

    try:

        @micropython.viper
        def _viper_probe():
            pass

        _has_viper = True
    except (AttributeError, NotImplementedError):
        _has_viper = False
except ImportError:
    micropython = None
    _has_viper = False

    def const(x):
        return x


# Try to import the native C mixer
try:
    import _audiomix

    _has_native = True
except ImportError:
    _audiomix = None
    _has_native = False

from bodn import tones
from bodn.wav import WavReader

# Voice routing tags (used as indices into _voices)
V_MUSIC = const(0)
V_SFX_BASE = const(1)  # SFX pool: indices 1..4
V_SFX_END = const(5)  # exclusive
V_UI = const(5)
_NUM_VOICES = const(6)

# Channel name → routing tag (for API compatibility)
CHANNEL_NAMES = {"music": V_MUSIC, "sfx": V_SFX_BASE, "ui": V_UI}

# Legacy aliases for tests and callers that reference CH_* constants
CH_MUSIC = V_MUSIC
CH_SFX = V_SFX_BASE
CH_UI = V_UI

_MONO_BUF_SIZE = const(
    512
)  # bytes per mono read buffer (256 samples at 16-bit = 16 ms)
_BUF_SIZE = const(1024)  # bytes per stereo output buffer

# Per-voice gain staging (fixed-point 16.16 multipliers)
# These keep the mix within int16 range under normal conditions.
_GAIN_MUSIC = const(45875)  # 70% — solo music
_GAIN_MUSIC_DUCKED = const(16384)  # 25% — music when other voices active
_GAIN_SFX = const(45875)  # 70%
_GAIN_UI = const(52428)  # 80%

# Wave name → C enum mapping for native backend
_WAVE_MAP = {"square": 0, "sine": 1, "sawtooth": 2, "noise": 3}


# ---------------------------------------------------------------------------
# Pure-Python / viper DSP helpers (fallback backend only)
# ---------------------------------------------------------------------------


def _apply_volume_py(buf, n_bytes, mult):
    """Pure-Python fallback for volume scaling (host tests)."""
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
    """Pure-Python fallback: add int16 samples from src into dst with saturation."""
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


if _has_viper:

    @micropython.viper
    def _apply_volume_viper(buf_ptr, n_bytes: int, mult: int):
        """Scale int16 samples in-place — viper-emitted for ~10-20x speedup."""
        p = ptr8(buf_ptr)  # noqa: F821 — viper builtin
        i = 0
        while i < n_bytes:
            lo = int(p[i])
            hi = int(p[i + 1])
            val = lo | (hi << 8)
            if val >= 0x8000:
                val -= 0x10000
            val = (val * mult) >> 16
            val = val & 0xFFFF
            p[i] = val & 0xFF
            p[i + 1] = (val >> 8) & 0xFF
            i += 2

    @micropython.viper
    def _mix_add_viper(dst_ptr, src_ptr, n_bytes: int):
        """Add int16 samples from src into dst with saturation — viper."""
        d = ptr8(dst_ptr)  # noqa: F821
        s = ptr8(src_ptr)  # noqa: F821
        i = 0
        while i < n_bytes:
            d_lo = int(d[i])
            d_hi = int(d[i + 1])
            d_val = d_lo | (d_hi << 8)
            if d_val >= 0x8000:
                d_val -= 0x10000
            s_lo = int(s[i])
            s_hi = int(s[i + 1])
            s_val = s_lo | (s_hi << 8)
            if s_val >= 0x8000:
                s_val -= 0x10000
            total = d_val + s_val
            if total > 32767:
                total = 32767
            elif total < -32768:
                total = -32768
            total = total & 0xFFFF
            d[i] = total & 0xFF
            d[i + 1] = (total >> 8) & 0xFF
            i += 2

    @micropython.viper
    def _mono_to_stereo_viper(mono_ptr, stereo_ptr, n_mono_bytes: int):
        """Duplicate mono int16 samples into stereo L+R — viper."""
        m = ptr8(mono_ptr)  # noqa: F821
        s = ptr8(stereo_ptr)  # noqa: F821
        i = n_mono_bytes - 2
        j = (n_mono_bytes - 2) * 2
        while i >= 0:
            lo = int(m[i])
            hi = int(m[i + 1])
            s[j] = lo
            s[j + 1] = hi
            s[j + 2] = lo
            s[j + 3] = hi
            i -= 2
            j -= 4

    _apply_volume_fast = _apply_volume_viper
    _mix_add_fast = _mix_add_viper
    _mono_to_stereo_fast = _mono_to_stereo_viper
else:
    _apply_volume_fast = _apply_volume_py
    _mix_add_fast = _mix_add_py
    _mono_to_stereo_fast = None  # use Python method fallback


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
# Source classes (used by fallback backend; WAV streaming also used by native)
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
# Fallback backend: _Voice + IRQ callback (core 0, viper/pure-Python)
# ---------------------------------------------------------------------------


class _Voice:
    """Internal voice state with its own read buffer."""

    __slots__ = (
        "source",
        "loop",
        "file_obj",
        "mono_buf",
        "gain_mult",
        "is_music",
        "_start_seq",
    )

    def __init__(self, gain_mult, is_music=False):
        self.source = None
        self.loop = False
        self.file_obj = None
        self.mono_buf = bytearray(_MONO_BUF_SIZE)
        self.gain_mult = gain_mult
        self.is_music = is_music
        self._start_seq = 0

    def stop(self):
        if self.file_obj:
            try:
                self.file_obj.close()
            except Exception:
                pass
        self.source = None
        self.loop = False
        self.file_obj = None


def _make_irq_callback(engine):
    """Build a closure-based IRQ callback with cached locals."""
    mix_buf = engine._mix_buf
    zero = engine._zero
    buf = engine._buf
    buf_view = engine._buf_view
    voices = engine._voices
    silence_short = engine._silence_short
    m2s_viper = _mono_to_stereo_fast
    mono_to_stereo_py = AudioEngine._mono_to_stereo
    apply_vol = _apply_volume_fast
    mix_add = _mix_add_fast

    def callback(i2s_obj):
        """Mix one chunk and write to I2S.  Fired by DMA via micropython.schedule()."""
        non_music_active = False
        has_active = False
        for v in voices:
            if v.source is not None:
                has_active = True
                if not v.is_music:
                    non_music_active = True

        if not has_active:
            i2s_obj.write(silence_short)
            return

        max_n = 0
        mix_buf[:] = zero

        for v in voices:
            if v.source is None:
                continue

            n = 0
            try:
                n = v.source.read_chunk(v.mono_buf)
            except Exception:
                v.stop()
                continue

            if n == 0:
                if v.loop:
                    v.source.seek_start()
                    try:
                        n = v.source.read_chunk(v.mono_buf)
                    except Exception:
                        v.stop()
                        continue
                    if n == 0:
                        v.stop()
                        continue
                else:
                    v.stop()
                    continue

            if v.is_music and non_music_active:
                gain = _GAIN_MUSIC_DUCKED
            else:
                gain = v.gain_mult
            apply_vol(v.mono_buf, n, gain)

            mix_add(mix_buf, v.mono_buf, n)

            if n > max_n:
                max_n = n

        if max_n == 0:
            i2s_obj.write(silence_short)
            return

        vol = engine._volume
        if vol < 100:
            _apply_volume_fast(mix_buf, max_n, engine._vol_mult)

        if m2s_viper:
            m2s_viper(mix_buf, buf, max_n)
        else:
            mono_to_stereo_py(mix_buf, buf, max_n)

        i2s_obj.write(buf_view[: max_n * 2])

    return callback


# ---------------------------------------------------------------------------
# Native backend: streaming voice state (Python-side bookkeeping)
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
# AudioEngine — unified public API
# ---------------------------------------------------------------------------


class AudioEngine:
    """Multi-voice audio engine with native (core 1) and fallback backends.

    Usage::

        # Native backend (custom firmware with _audiomix):
        audio = AudioEngine(native=True, bck=13, ws=45, din=7, amp=3)

        # Fallback backend (stock firmware):
        audio = AudioEngine(i2s=i2s_obj, amp_enable=callback)

        # In asyncio.gather:
        await audio.start()

        audio.tone(440, 500)
        audio.play("/sounds/boop.wav")
        audio.boop()
    """

    def __init__(self, i2s=None, amp_enable=None, native=False, **kwargs):
        self._native = native and _has_native

        if self._native:
            # Native backend — C module handles I2S + mixing on core 1
            bck = kwargs.get("bck", 13)
            ws = kwargs.get("ws", 45)
            din = kwargs.get("din", 7)
            amp = kwargs.get("amp", 3)
            rate = kwargs.get("rate", 16000)
            ibuf = kwargs.get("ibuf", 16384)
            _audiomix.init(bck=bck, ws=ws, din=din, amp=amp, rate=rate, ibuf=ibuf)
            self._streaming = []  # active _StreamingVoice instances
            self._buf_refs = {}  # voice_idx → bytearray ref (prevent GC)
            self._feed_buf = bytearray(_MONO_BUF_SIZE)
            # Fallback fields not used in native mode
            self._i2s = None
            self._amp_enable = None
            self._voices = None
            self._mix_buf = None
            self._zero = None
            self._buf = None
            self._buf_view = None
            self._silence = None
            self._silence_short = None
            self._irq_cb = None
        else:
            # Fallback backend — viper/pure-Python on core 0
            self._i2s = i2s
            self._amp_enable = amp_enable
            self._voices = [
                _Voice(_GAIN_MUSIC, is_music=True),
                _Voice(_GAIN_SFX),
                _Voice(_GAIN_SFX),
                _Voice(_GAIN_SFX),
                _Voice(_GAIN_SFX),
                _Voice(_GAIN_UI),
            ]
            self._mix_buf = bytearray(_MONO_BUF_SIZE)
            self._zero = bytes(_MONO_BUF_SIZE)
            self._buf = bytearray(_BUF_SIZE)
            self._buf_view = memoryview(self._buf)
            self._silence = bytes(_BUF_SIZE)
            self._silence_short = bytes(64)
            self._irq_cb = None
            self._streaming = None
            self._buf_refs = None
            self._feed_buf = None

        self._seq_counter = 0
        self._volume = 10
        self._vol_mult = 10 * 655
        self._burst_max = 0

    @property
    def volume(self):
        if self._native:
            return _audiomix.get_volume()
        return self._volume

    @volume.setter
    def volume(self, val):
        val = max(0, min(100, val))
        self._volume = val
        self._vol_mult = val * 655
        if self._native:
            _audiomix.set_volume(val)

    @property
    def burst(self):
        """Max chunks written per yield (1–6).  0 = auto-scale by voice count."""
        return self._burst_max

    @burst.setter
    def burst(self, val):
        self._burst_max = max(0, min(6, val))

    @property
    def playing(self):
        """True if any voice is active."""
        if self._native:
            for i in range(_NUM_VOICES):
                if _audiomix.voice_active(i):
                    return True
            return False
        return any(v.source is not None for v in self._voices)

    def channel_active(self, channel):
        """True if the given named channel has an active voice."""
        if channel == "sfx":
            return self.sfx_active > 0
        idx = CHANNEL_NAMES.get(channel, -1)
        if 0 <= idx < _NUM_VOICES:
            if self._native:
                return _audiomix.voice_active(idx)
            return self._voices[idx].source is not None
        return False

    @property
    def sfx_active(self):
        """Number of SFX pool voices currently playing."""
        count = 0
        for i in range(V_SFX_BASE, V_SFX_END):
            if self._native:
                if _audiomix.voice_active(i):
                    count += 1
            elif self._voices[i].source is not None:
                count += 1
        return count

    # -----------------------------------------------------------------------
    # Voice allocation (shared logic)
    # -----------------------------------------------------------------------

    def _allocate_sfx_idx(self):
        """Find a free SFX pool voice index, or steal the oldest."""
        if self._native:
            for i in range(V_SFX_BASE, V_SFX_END):
                if not _audiomix.voice_active(i):
                    return i
            # All busy — stop the first (simple steal for native)
            _audiomix.voice_stop(V_SFX_BASE)
            return V_SFX_BASE
        # Fallback: delegate to _Voice-based allocation
        return None

    def _allocate_sfx(self):
        """Find a free SFX pool voice, or steal the oldest (fallback only)."""
        for i in range(V_SFX_BASE, V_SFX_END):
            if self._voices[i].source is None:
                return self._voices[i]
        oldest = self._voices[V_SFX_BASE]
        for i in range(V_SFX_BASE + 1, V_SFX_END):
            if self._voices[i]._start_seq < oldest._start_seq:
                oldest = self._voices[i]
        oldest.stop()
        return oldest

    def _assign_voice_idx(self, channel):
        """Get voice index for a channel (native backend)."""
        if channel == "sfx":
            return self._allocate_sfx_idx()
        idx = CHANNEL_NAMES.get(channel, V_SFX_BASE)
        if idx == V_SFX_BASE and channel != "sfx":
            return self._allocate_sfx_idx()
        _audiomix.voice_stop(idx)
        return idx

    def _assign_voice(self, channel):
        """Get the voice slot for a channel name (fallback backend)."""
        if channel == "sfx":
            return self._allocate_sfx()
        idx = CHANNEL_NAMES.get(channel, V_SFX_BASE)
        if idx == V_SFX_BASE and channel != "sfx":
            return self._allocate_sfx()
        v = self._voices[idx]
        v.stop()
        return v

    def _stamp_voice(self, voice):
        """Mark a voice with the current sequence number for age tracking."""
        self._seq_counter += 1
        voice._start_seq = self._seq_counter

    def _stop_streaming(self, idx):
        """Remove any active streaming voice for the given index."""
        self._streaming = [s for s in self._streaming if s.idx != idx]
        self._buf_refs.pop(idx, None)

    # -----------------------------------------------------------------------
    # Public API: play, tone, stop, etc.
    # -----------------------------------------------------------------------

    def play(self, path, loop=False, channel="sfx"):
        """Play a WAV file on the given channel."""
        if self._native:
            idx = self._assign_voice_idx(channel)
            self._stop_streaming(idx)
            try:
                f = open(path, "rb")
                wav = WavReader(f)
                _audiomix.voice_start_stream(idx, loop)
                sv = _StreamingVoice(idx, wav, f, self._feed_buf, loop)
                # Initial fill
                self._fill_ringbuf(sv)
                self._streaming.append(sv)
            except Exception as e:
                print("audio.play error:", e)
                _audiomix.voice_stop(idx)
            return

        v = self._assign_voice(channel)
        try:
            f = open(path, "rb")
            v.file_obj = f
            v.source = WavReader(f)
            v.loop = loop
            self._stamp_voice(v)
        except Exception as e:
            print("audio.play error:", e)
            v.stop()

    def play_buffer(self, data, loop=False, channel="sfx"):
        """Play pre-loaded PCM data (bytearray) on the given channel."""
        if self._native:
            idx = self._assign_voice_idx(channel)
            self._stop_streaming(idx)
            self._buf_refs[idx] = data  # prevent GC
            _audiomix.voice_play_buffer(idx, data, len(data), loop)
            return

        v = self._assign_voice(channel)
        v.source = MemorySource(data)
        v.loop = loop
        self._stamp_voice(v)

    def tone(self, freq_hz, duration_ms=200, wave="square", channel="sfx"):
        """Play a procedural tone on the given channel."""
        if self._native:
            idx = self._assign_voice_idx(channel)
            self._stop_streaming(idx)
            wave_id = _WAVE_MAP.get(wave, 0)
            _audiomix.voice_tone(idx, freq_hz, duration_ms, wave_id)
            return

        v = self._assign_voice(channel)
        v.source = ToneSource(freq_hz, duration_ms, wave)
        v.loop = False
        self._stamp_voice(v)

    def play_sound(self, name, channel="ui"):
        """Play a named sound from the sound design system."""
        from bodn.sounds import WAV, SOUNDS

        path = WAV.get("sfx", {}).get(name)
        if path:
            self.play(path, channel=channel)
            return

        steps = SOUNDS.get(name)
        if not steps:
            return

        if self._native:
            idx = self._assign_voice_idx(channel)
            self._stop_streaming(idx)
            # Pack steps into bytes: (freq_u16_le, dur_u16_le, wave_u8) × N
            packed = bytearray(len(steps) * 5)
            for i, (freq, dur, wave) in enumerate(steps):
                off = i * 5
                f = max(0, freq)
                packed[off] = f & 0xFF
                packed[off + 1] = (f >> 8) & 0xFF
                packed[off + 2] = dur & 0xFF
                packed[off + 3] = (dur >> 8) & 0xFF
                packed[off + 4] = _WAVE_MAP.get(wave, 0)
            _audiomix.voice_sequence(idx, packed)
            return

        v = self._assign_voice(channel)
        v.source = SequenceSource(steps)
        v.loop = False
        self._stamp_voice(v)

    def boop(self):
        """Quick UI feedback beep."""
        self.play_sound("boop")

    def stop(self, channel=None):
        """Stop playback on a channel, or all voices if None."""
        if self._native:
            if channel is None:
                for i in range(_NUM_VOICES):
                    _audiomix.voice_stop(i)
                for sv in self._streaming:
                    sv.close()
                self._streaming.clear()
                self._buf_refs.clear()
            elif channel == "sfx":
                for i in range(V_SFX_BASE, V_SFX_END):
                    _audiomix.voice_stop(i)
                    self._stop_streaming(i)
            else:
                idx = CHANNEL_NAMES.get(channel, -1)
                if 0 <= idx < _NUM_VOICES:
                    _audiomix.voice_stop(idx)
                    self._stop_streaming(idx)
            return

        if channel is None:
            for v in self._voices:
                v.stop()
        elif channel == "sfx":
            for i in range(V_SFX_BASE, V_SFX_END):
                self._voices[i].stop()
        else:
            idx = CHANNEL_NAMES.get(channel, -1)
            if 0 <= idx < _NUM_VOICES:
                self._voices[idx].stop()

    def _apply_volume(self, buf, n_bytes):
        """Scale int16 samples in-place using fixed-point multiplication."""
        if self._volume >= 100:
            return
        _apply_volume_fast(buf, n_bytes, self._vol_mult)

    @staticmethod
    def _mono_to_stereo(mono, stereo, n_mono_bytes):
        """Duplicate each 16-bit mono sample into L+R stereo frames."""
        i = n_mono_bytes - 2
        j = (n_mono_bytes - 2) * 2
        while i >= 0:
            lo = mono[i]
            hi = mono[i + 1]
            stereo[j] = lo
            stereo[j + 1] = hi
            stereo[j + 2] = lo
            stereo[j + 3] = hi
            i -= 2
            j -= 4

    # -----------------------------------------------------------------------
    # Ring buffer feeder (native backend)
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
    # start() — main async loop
    # -----------------------------------------------------------------------

    async def start(self):
        """Start the audio engine.

        Native: runs a feeder loop that tops up ring buffers for streaming
        voices.  The C task on core 1 handles all mixing independently.

        Fallback: primes the I2S DMA chain and registers the IRQ callback.
        """
        import gc

        if self._native:
            print("AudioEngine started (native, core 1)")
            gc_collect = gc.collect
            sleep_ms = asyncio.sleep_ms
            while True:
                # Only do work if there are active streams to feed
                if self._streaming:
                    dead = []
                    for sv in self._streaming:
                        if not _audiomix.voice_active(sv.idx):
                            dead.append(sv)
                            continue
                        self._fill_ringbuf(sv)
                    for sv in dead:
                        sv.close()
                        self._streaming.remove(sv)
                        self._buf_refs.pop(sv.idx, None)
                    await sleep_ms(16)
                else:
                    # No streams — idle at low frequency
                    gc_collect()
                    await sleep_ms(100)
            return

        # Fallback: IRQ callback chain
        self._i2s.write(self._silence)
        if self._amp_enable:
            self._amp_enable()
        print("Amplifier enabled, viper:", _has_viper)

        self._irq_cb = _make_irq_callback(self)
        self._i2s.irq(self._irq_cb)
        self._i2s.write(self._silence_short)

        print("Audio IRQ callback chain started")

        gc_collect = gc.collect
        sleep_ms = asyncio.sleep_ms
        while True:
            gc_collect()
            await sleep_ms(1000)
