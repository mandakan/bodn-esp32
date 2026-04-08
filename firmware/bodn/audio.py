# bodn/audio.py — AudioEngine for Bodn ESP32
#
# DMA-driven audio: the I2S peripheral fires an IRQ callback via
# micropython.schedule() whenever it needs more data.  The callback
# mixes one chunk from active voices and feeds it back — a self-
# sustaining chain driven by hardware timing, not software scheduling.
#
# This decouples audio from the uasyncio event loop: even while the
# main thread blocks on a 47 ms SPI display write, the DMA keeps
# playing buffered audio.  The callback fires at the next VM opcode
# boundary after the SPI write returns, immediately refilling the buffer.
#
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
    """Build a closure-based IRQ callback with cached locals.

    Closure locals are the fastest variable access in MicroPython —
    no dict lookups, no attribute access in the hot path.
    """
    # Cache everything the callback needs as closure variables.
    # These are captured once and reused for every DMA callback.
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
        # Check for active voices — determine ducking
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

        # Mix all active voices into mix_buf
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

            # Per-voice gain
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

        # Master volume
        vol = engine._volume
        if vol < 100:
            _apply_volume_fast(mix_buf, max_n, engine._vol_mult)

        # Mono to stereo expansion
        if m2s_viper:
            m2s_viper(mix_buf, buf, max_n)
        else:
            mono_to_stereo_py(mix_buf, buf, max_n)

        # Non-blocking write — returns immediately, DMA handles the rest
        i2s_obj.write(buf_view[: max_n * 2])

    return callback


class AudioEngine:
    """DMA-driven audio engine with multi-voice mixing.

    The I2S peripheral fires an IRQ callback whenever it needs data.
    The callback mixes one chunk from active voices and feeds it back,
    creating a self-sustaining chain driven by hardware timing.

    Usage::

        audio = AudioEngine(i2s_out)
        # in asyncio.gather:
        await audio.start()

        audio.tone(440, 500)
        audio.play("/sounds/boop.wav")
        audio.boop()
    """

    __slots__ = (
        "_i2s",
        "_amp_enable",
        "_voices",
        "_seq_counter",
        "_mix_buf",
        "_zero",
        "_buf",
        "_buf_view",
        "_silence",
        "_silence_short",
        "_volume",
        "_vol_mult",
        "_burst_max",
        "_irq_cb",
    )

    def __init__(self, i2s, amp_enable=None):
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
        self._seq_counter = 0

        self._mix_buf = bytearray(_MONO_BUF_SIZE)
        self._zero = bytes(_MONO_BUF_SIZE)
        self._buf = bytearray(_BUF_SIZE)
        self._buf_view = memoryview(self._buf)
        self._silence = bytes(_BUF_SIZE)
        self._silence_short = bytes(64)
        self._volume = 10
        self._vol_mult = 10 * 655
        self._burst_max = 0
        self._irq_cb = None

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, val):
        val = max(0, min(100, val))
        self._volume = val
        self._vol_mult = val * 655

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
        return any(v.source is not None for v in self._voices)

    def channel_active(self, channel):
        """True if the given named channel has an active voice."""
        if channel == "sfx":
            return self.sfx_active > 0
        idx = CHANNEL_NAMES.get(channel, -1)
        if 0 <= idx < _NUM_VOICES:
            return self._voices[idx].source is not None
        return False

    @property
    def sfx_active(self):
        """Number of SFX pool voices currently playing."""
        count = 0
        for i in range(V_SFX_BASE, V_SFX_END):
            if self._voices[i].source is not None:
                count += 1
        return count

    def _allocate_sfx(self):
        """Find a free SFX pool voice, or steal the oldest."""
        for i in range(V_SFX_BASE, V_SFX_END):
            if self._voices[i].source is None:
                return self._voices[i]
        oldest = self._voices[V_SFX_BASE]
        for i in range(V_SFX_BASE + 1, V_SFX_END):
            if self._voices[i]._start_seq < oldest._start_seq:
                oldest = self._voices[i]
        oldest.stop()
        return oldest

    def _assign_voice(self, channel):
        """Get the voice slot for a channel name, stopping any existing source."""
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

    def play(self, path, loop=False, channel="sfx"):
        """Play a WAV file on the given channel."""
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
        v = self._assign_voice(channel)
        v.source = MemorySource(data)
        v.loop = loop
        self._stamp_voice(v)

    def tone(self, freq_hz, duration_ms=200, wave="square", channel="sfx"):
        """Play a procedural tone on the given channel."""
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
        v = self._assign_voice(channel)
        v.source = SequenceSource(steps)
        v.loop = False
        self._stamp_voice(v)

    def boop(self):
        """Quick UI feedback beep."""
        self.play_sound("boop")

    def stop(self, channel=None):
        """Stop playback on a channel, or all voices if None."""
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

    async def start(self):
        """Start the DMA-driven audio callback chain.

        The I2S IRQ callback handles all mixing and writing.  This
        coroutine just primes the chain and then idles, running
        periodic GC to keep the heap clean.
        """
        import gc

        # Prime DMA + enable amp
        self._i2s.write(self._silence)
        if self._amp_enable:
            self._amp_enable()
        print("Amplifier enabled, viper:", _has_viper)

        # Build closure-based callback (fastest access pattern)
        self._irq_cb = _make_irq_callback(self)

        # Register callback — switches I2S to non-blocking mode.
        # Every i2s.write() now returns immediately; the callback
        # fires when the DMA has consumed data and needs more.
        self._i2s.irq(self._irq_cb)

        # Kick off the chain — first write triggers first callback
        self._i2s.write(self._silence_short)

        print("Audio IRQ callback chain started")

        # Idle loop: the callback chain is self-sustaining.
        # We just do periodic GC here.
        gc_collect = gc.collect
        sleep_ms = asyncio.sleep_ms
        while True:
            gc_collect()
            await sleep_ms(1000)
