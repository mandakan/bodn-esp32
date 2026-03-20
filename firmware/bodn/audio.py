# bodn/audio.py — AudioEngine for Bodn ESP32
#
# Singleton created in main(), runs as an async background task.
# Manages 3 priority channels (ui > sfx > music) with no mixing.

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

try:
    from micropython import const
except ImportError:

    def const(x):
        return x


from bodn import tones
from bodn.wav import WavReader


# Channel priorities (higher number = higher priority)
CH_MUSIC = const(0)
CH_SFX = const(1)
CH_UI = const(2)
CHANNEL_NAMES = {"music": CH_MUSIC, "sfx": CH_SFX, "ui": CH_UI}

_BUF_SIZE = const(1024)  # bytes per audio buffer


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

    def __init__(self, i2s):
        self._i2s = i2s
        self._channels = [_Channel() for _ in range(3)]
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
        self.tone(440, 80, "square", "ui")

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
        mult = self._vol_mult
        for i in range(0, n_bytes, 2):
            # Unpack int16 LE
            lo = buf[i]
            hi = buf[i + 1]
            val = lo | (hi << 8)
            if val >= 0x8000:
                val -= 0x10000
            # Scale and repack
            val = (val * mult) >> 16
            val = val & 0xFFFF
            buf[i] = val & 0xFF
            buf[i + 1] = (val >> 8) & 0xFF

    def _active_channel(self):
        """Return highest-priority active channel index, or -1."""
        for idx in range(CH_UI, CH_MUSIC - 1, -1):
            if self._channels[idx].source is not None:
                return idx
        return -1

    async def start(self):
        """Background audio loop — add to asyncio.gather()."""
        # Cache attributes as locals — avoids dict lookups each iteration
        buf = self._buf
        buf_view = self._buf_view
        i2s = self._i2s
        channels = self._channels
        silence = self._silence
        sleep_ms = asyncio.sleep_ms

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
                n = ch.source.read_chunk(buf)
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

            self._apply_volume(buf, n)
            try:
                # memoryview slice avoids allocating a new bytes object
                i2s.write(buf_view[:n])
            except Exception as e:
                print("audio write error:", e)

            await sleep_ms(0)
