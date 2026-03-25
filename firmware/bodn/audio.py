# bodn/audio.py — AudioEngine for Bodn ESP32
#
# Singleton created in main(), runs as an async background task.
# Manages 3 priority channels (ui > sfx > music) with no mixing.

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

# Channel priorities (higher number = higher priority)
CH_MUSIC = const(0)
CH_SFX = const(1)
CH_UI = const(2)
CHANNEL_NAMES = {"music": CH_MUSIC, "sfx": CH_SFX, "ui": CH_UI}

_BUF_SIZE = const(2048)  # bytes per stereo audio buffer (1024 mono → 2048 stereo)


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

    _apply_volume_fast = _apply_volume_viper
else:
    _apply_volume_fast = _apply_volume_py


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


class _Channel:
    """Internal channel state."""

    __slots__ = ("source", "loop", "file_obj")

    def __init__(self):
        self.source = None
        self.loop = False
        self.file_obj = None

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
    """Cooperative async audio engine with priority channels.

    Usage::

        audio = AudioEngine(i2s_out)
        # in asyncio.gather:
        await audio.start()

        audio.tone(440, 500)            # 440 Hz for 500 ms
        audio.play("/sounds/boop.wav")  # play a WAV file
        audio.boop()                    # quick UI feedback tone
    """

    def __init__(self, i2s, amp_enable=None):
        """Create the audio engine.

        amp_enable: optional callable to unmute the amplifier.
        Called once after the first silence write so the amp never
        hears noise from unconfigured I2S pins during boot.
        """
        self._i2s = i2s
        self._amp_enable = amp_enable
        self._channels = [_Channel() for _ in range(3)]
        # Mono sources write into _mono_buf; _buf holds stereo-expanded output
        self._mono_buf = bytearray(_BUF_SIZE // 2)
        self._buf = bytearray(_BUF_SIZE)
        self._buf_view = memoryview(self._buf)
        self._silence = bytes(_BUF_SIZE)
        self._volume = 80  # 0-100
        self._vol_mult = 52429  # pre-computed fixed-point multiplier (80%)

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, val):
        val = max(0, min(100, val))
        self._volume = val
        # Fixed-point 16.16 multiplier: (val / 100) * 65536
        self._vol_mult = val * 655

    @property
    def playing(self):
        """True if any channel is active."""
        return any(ch.source is not None for ch in self._channels)

    def play(self, path, loop=False, channel="sfx"):
        """Play a WAV file on the given channel."""
        ch_idx = CHANNEL_NAMES.get(channel, CH_SFX)
        ch = self._channels[ch_idx]
        ch.stop()
        try:
            f = open(path, "rb")
            ch.file_obj = f
            ch.source = WavReader(f)
            ch.loop = loop
        except Exception as e:
            print("audio.play error:", e)
            ch.stop()

    def tone(self, freq_hz, duration_ms=200, wave="square", channel="sfx"):
        """Play a procedural tone on the given channel."""
        ch_idx = CHANNEL_NAMES.get(channel, CH_SFX)
        ch = self._channels[ch_idx]
        ch.stop()
        ch.source = ToneSource(freq_hz, duration_ms, wave)
        ch.loop = False

    def boop(self):
        """Quick UI feedback beep."""
        self.tone(440, 150, "square", "ui")

    def stop(self, channel=None):
        """Stop playback on a channel, or all channels if None."""
        if channel is None:
            for ch in self._channels:
                ch.stop()
        else:
            ch_idx = CHANNEL_NAMES.get(channel, CH_SFX)
            self._channels[ch_idx].stop()

    def _apply_volume(self, buf, n_bytes):
        """Scale int16 samples in-place using fixed-point multiplication."""
        if self._volume >= 100:
            return
        _apply_volume_fast(buf, n_bytes, self._vol_mult)

    def _active_channel(self):
        """Return highest-priority active channel index, or -1."""
        for idx in range(CH_UI, CH_MUSIC - 1, -1):
            if self._channels[idx].source is not None:
                return idx
        return -1

    @staticmethod
    def _mono_to_stereo(mono, stereo, n_mono_bytes):
        """Duplicate each 16-bit mono sample into L+R stereo frames.

        Reads n_mono_bytes from mono, writes n_mono_bytes*2 to stereo.
        Iterates backwards so mono and stereo can overlap (mono at start of stereo).
        """
        # Each mono sample is 2 bytes; each stereo frame is 4 bytes (L+R)
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
        # Cache attributes as locals — avoids dict lookups each iteration
        mono_buf = self._mono_buf
        buf = self._buf
        buf_view = self._buf_view
        i2s = self._i2s
        channels = self._channels
        silence = self._silence
        sleep_ms = asyncio.sleep_ms
        mono_to_stereo = self._mono_to_stereo

        # Prime the I2S DMA with silence, then unmute the amp
        i2s.write(silence)
        if self._amp_enable:
            self._amp_enable()
            print("Amplifier enabled")

        while True:
            ch_idx = self._active_channel()

            if ch_idx < 0:
                # Nothing playing — write silence (MAX98357A auto-mutes)
                i2s.write(silence)
                await sleep_ms(20)
                continue

            ch = channels[ch_idx]
            n = 0
            try:
                n = ch.source.read_chunk(mono_buf)
            except Exception as e:
                print("audio read error:", e)
                ch.stop()
                continue

            if n == 0:
                if ch.loop:
                    ch.source.seek_start()
                    continue
                else:
                    ch.stop()
                    continue

            self._apply_volume(mono_buf, n)
            # Expand mono → stereo (duplicate each sample to L+R)
            mono_to_stereo(mono_buf, buf, n)
            stereo_n = n * 2
            try:
                i2s.write(buf_view[:stereo_n])
            except Exception as e:
                print("audio write error:", e)

            await sleep_ms(0)
