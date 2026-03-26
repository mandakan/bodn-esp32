# bodn/audio.py — AudioEngine for Bodn ESP32
#
# Singleton created in main(), runs as an async background task.
# Mixes up to 6 simultaneous voices: 1 music + 4 SFX pool + 1 UI.

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

try:
    import micropython
    from micropython import const

    _has_viper = hasattr(micropython, "viper")
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

_MONO_BUF_SIZE = const(1024)  # bytes per mono read buffer (512 samples at 16-bit)
_BUF_SIZE = const(2048)  # bytes per stereo output buffer

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
        # Read dst sample
        d_lo = dst[i]
        d_hi = dst[i + 1]
        d_val = d_lo | (d_hi << 8)
        if d_val >= 0x8000:
            d_val -= 0x10000
        # Read src sample
        s_lo = src[i]
        s_hi = src[i + 1]
        s_val = s_lo | (s_hi << 8)
        if s_val >= 0x8000:
            s_val -= 0x10000
        # Sum with saturation
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
            # Read dst int16 LE
            d_lo = int(d[i])
            d_hi = int(d[i + 1])
            d_val = d_lo | (d_hi << 8)
            if d_val >= 0x8000:
                d_val -= 0x10000
            # Read src int16 LE
            s_lo = int(s[i])
            s_hi = int(s[i + 1])
            s_val = s_lo | (s_hi << 8)
            if s_val >= 0x8000:
                s_val -= 0x10000
            # Sum in int32, saturate to int16
            total = d_val + s_val
            if total > 32767:
                total = 32767
            elif total < -32768:
                total = -32768
            total = total & 0xFFFF
            d[i] = total & 0xFF
            d[i + 1] = (total >> 8) & 0xFF
            i += 2

    _apply_volume_fast = _apply_volume_viper
    _mix_add_fast = _mix_add_viper
else:
    _apply_volume_fast = _apply_volume_py
    _mix_add_fast = _mix_add_py


class ToneSource:
    """Adapter that wraps tones.generate() with the same interface as WavReader."""

    def __init__(self, freq_hz, duration_ms, wave, sample_rate=16000):
        self.freq_hz = freq_hz
        self.wave = wave
        self.sample_rate = sample_rate
        self._total_bytes = (sample_rate * duration_ms // 1000) * 2  # 16-bit mono
        self._bytes_left = self._total_bytes

    def read_chunk(self, buf):
        if self._bytes_left <= 0:
            return 0
        to_fill = min(len(buf), self._bytes_left)
        # Align to sample boundary
        to_fill = (to_fill // 2) * 2
        n = tones.generate(buf, self.freq_hz, self.sample_rate, self.wave)
        n = min(n, to_fill)
        self._bytes_left -= n
        return n

    def seek_start(self):
        self._bytes_left = self._total_bytes


class SequenceSource:
    """Plays a list of (freq_hz, duration_ms, wave) steps in order.

    A freq_hz of 0 produces silence (a gap between notes).
    """

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
            # Silent gap — return zero bytes for the duration
            return ToneSource(1, dur, "square", self._sample_rate)
        return ToneSource(freq, dur, wave, self._sample_rate)

    def read_chunk(self, buf):
        while self._current is not None:
            n = self._current.read_chunk(buf)
            if n > 0:
                # Zero out silence gaps (freq=0 steps)
                if self._steps[self._idx][0] <= 0:
                    for i in range(n):
                        buf[i] = 0
                return n
            # Current step exhausted — advance to next
            self._idx += 1
            self._current = self._make_tone(self._idx)
        return 0

    def seek_start(self):
        self._idx = 0
        self._current = self._make_tone(0)


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
        self._start_seq = 0  # monotonic counter for oldest-voice stealing

    def stop(self):
        if self.file_obj:
            try:
                self.file_obj.close()
            except Exception:
                pass
        self.source = None
        self.loop = False
        self.file_obj = None


class AudioEngine:
    """Cooperative async audio engine with multi-voice mixing.

    6 simultaneous voices: 1 music + 4 SFX pool + 1 UI.
    All active voices are mixed together each audio cycle.

    Usage::

        audio = AudioEngine(i2s_out)
        # in asyncio.gather:
        await audio.start()

        audio.tone(440, 500)            # 440 Hz for 500 ms
        audio.play("/sounds/boop.wav")  # play a WAV file
        audio.boop()                    # quick UI feedback tone
    """

    def __init__(self, i2s, amp_enable=None):
        self._i2s = i2s
        self._amp_enable = amp_enable

        # Voice slots: [music, sfx0, sfx1, sfx2, sfx3, ui]
        self._voices = [
            _Voice(_GAIN_MUSIC, is_music=True),  # V_MUSIC = 0
            _Voice(_GAIN_SFX),  # SFX pool slot 0
            _Voice(_GAIN_SFX),  # SFX pool slot 1
            _Voice(_GAIN_SFX),  # SFX pool slot 2
            _Voice(_GAIN_SFX),  # SFX pool slot 3
            _Voice(_GAIN_UI),  # V_UI = 5
        ]
        self._seq_counter = 0  # monotonic counter for voice-steal ordering

        # Mix buffer (accumulated output) and stereo output buffer
        self._mix_buf = bytearray(_MONO_BUF_SIZE)
        self._buf = bytearray(_BUF_SIZE)
        self._buf_view = memoryview(self._buf)
        self._silence = bytes(_BUF_SIZE)
        self._silence_short = bytes(512)
        self._volume = 10  # 0-100, synced from settings in main.py
        self._vol_mult = 10 * 655  # pre-computed fixed-point multiplier

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, val):
        val = max(0, min(100, val))
        self._volume = val
        self._vol_mult = val * 655

    @property
    def playing(self):
        """True if any voice is active."""
        return any(v.source is not None for v in self._voices)

    def _allocate_sfx(self):
        """Find a free SFX pool voice, or steal the oldest."""
        # Prefer a free slot
        for i in range(V_SFX_BASE, V_SFX_END):
            if self._voices[i].source is None:
                return self._voices[i]
        # All full — steal the oldest (lowest _start_seq)
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
            # Unknown channel name mapped to SFX — use pool
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

    def tone(self, freq_hz, duration_ms=200, wave="square", channel="sfx"):
        """Play a procedural tone on the given channel."""
        v = self._assign_voice(channel)
        v.source = ToneSource(freq_hz, duration_ms, wave)
        v.loop = False
        self._stamp_voice(v)

    def play_sound(self, name, channel="ui"):
        """Play a named sound from the sound design system."""
        from bodn.sounds import SOUNDS

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
        """Duplicate each 16-bit mono sample into L+R stereo frames.

        Reads n_mono_bytes from mono, writes n_mono_bytes*2 to stereo.
        Iterates backwards so mono and stereo can overlap (mono at start of stereo).
        """
        i = n_mono_bytes - 2
        j = (n_mono_bytes - 2) * 2
        while i >= 0:
            lo = mono[i]
            hi = mono[i + 1]
            # Left channel
            stereo[j] = lo
            stereo[j + 1] = hi
            # Right channel (same sample)
            stereo[j + 2] = lo
            stereo[j + 3] = hi
            i -= 2
            j -= 4

    async def start(self):
        """Background audio loop — add to asyncio.gather()."""
        # Cache as locals
        mix_buf = self._mix_buf
        buf = self._buf
        buf_view = self._buf_view
        i2s = self._i2s
        voices = self._voices
        silence = self._silence
        sleep_ms = asyncio.sleep_ms
        mono_to_stereo = self._mono_to_stereo
        apply_vol = _apply_volume_fast
        mix_add = _mix_add_fast

        # Prime the I2S DMA with silence, then unmute the amp
        i2s.write(silence)
        if self._amp_enable:
            self._amp_enable()
            print("Amplifier enabled")

        silence_short = self._silence_short

        while True:
            # Collect active voices
            has_active = False
            for v in voices:
                if v.source is not None:
                    has_active = True
                    break

            if not has_active:
                i2s.write(silence_short)
                await sleep_ms(5)
                continue

            # Determine if non-music voices are active (for ducking)
            non_music_active = False
            for v in voices:
                if v.source is not None and not v.is_music:
                    non_music_active = True
                    break

            # Read all active voices and mix
            max_n = 0
            # Zero the mix buffer up front
            for i in range(_MONO_BUF_SIZE):
                mix_buf[i] = 0

            for v in voices:
                if v.source is None:
                    continue

                n = 0
                try:
                    n = v.source.read_chunk(v.mono_buf)
                except Exception as e:
                    print("audio read error:", e)
                    v.stop()
                    continue

                if n == 0:
                    if v.loop:
                        v.source.seek_start()
                        try:
                            n = v.source.read_chunk(v.mono_buf)
                        except Exception as e:
                            print("audio read error:", e)
                            v.stop()
                            continue
                        if n == 0:
                            v.stop()
                            continue
                    else:
                        v.stop()
                        continue

                # Apply per-voice gain
                if v.is_music and non_music_active:
                    gain = _GAIN_MUSIC_DUCKED
                else:
                    gain = v.gain_mult
                apply_vol(v.mono_buf, n, gain)

                # Accumulate into mix buffer
                mix_add(mix_buf, v.mono_buf, n)

                if n > max_n:
                    max_n = n

            if max_n == 0:
                await sleep_ms(0)
                continue

            # Master volume
            self._apply_volume(mix_buf, max_n)

            # Mono to stereo expansion
            mono_to_stereo(mix_buf, buf, max_n)
            stereo_n = max_n * 2
            try:
                i2s.write(buf_view[:stereo_n])
            except Exception as e:
                print("audio write error:", e)

            await sleep_ms(0)
