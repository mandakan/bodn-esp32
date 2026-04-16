"""Tests for bodn.audio — AudioEngine multi-voice mixing."""

import struct
import sys

from bodn.audio import (
    AudioEngine,
    ToneSource,
    _GAIN_MUSIC,
    _GAIN_MUSIC_DUCKED,
    _GAIN_SFX,
    _mix_add_py,
    _apply_volume_py,
)

# Access the fake audiomix backend for test assertions
_audiomix = sys.modules["_audiomix"]


class TestToneSource:
    def test_read_chunk(self):
        src = ToneSource(440, 100, "square")
        buf = bytearray(1024)
        n = src.read_chunk(buf)
        assert n > 0
        assert n % 2 == 0

    def test_eof(self):
        src = ToneSource(440, 10, "square")  # very short
        buf = bytearray(4096)
        total = 0
        while True:
            n = src.read_chunk(buf)
            if n == 0:
                break
            total += n
        # 10ms at 16000 Hz = 160 samples = 320 bytes
        assert total == 320

    def test_seek_start(self):
        src = ToneSource(440, 10, "square")
        buf = bytearray(4096)
        src.read_chunk(buf)  # exhaust
        src.read_chunk(buf)  # EOF
        src.seek_start()
        n = src.read_chunk(buf)
        assert n > 0


class TestAudioEngine:
    def _make_engine(self):
        engine = AudioEngine()
        return engine

    def test_initial_state(self):
        engine = self._make_engine()
        assert not engine.playing
        assert engine.volume == 10

    def test_tone_activates(self):
        engine = self._make_engine()
        engine.tone(440, 100)
        assert engine.playing

    def test_stop_channel(self):
        engine = self._make_engine()
        engine.tone(440, 100, channel="sfx")
        engine.stop("sfx")
        assert not engine.playing

    def test_stop_all(self):
        engine = self._make_engine()
        engine.tone(440, 100, channel="sfx")
        engine.tone(880, 100, channel="ui")
        engine.stop()
        assert not engine.playing

    def test_boop(self):
        engine = self._make_engine()
        engine.boop()
        assert engine.playing

    def test_music_and_sfx_coexist(self):
        """Both music and SFX voices can be active simultaneously."""
        engine = self._make_engine()
        engine.tone(440, 500, channel="music")
        engine.tone(880, 500, channel="sfx")
        assert engine.channel_active("music")
        assert engine.channel_active("sfx")

    def test_all_voice_types_coexist(self):
        """Music, SFX, and UI can all be active at once."""
        engine = self._make_engine()
        engine.tone(440, 500, channel="music")
        engine.tone(880, 500, channel="sfx")
        engine.tone(1000, 500, channel="ui")
        assert engine.channel_active("music")
        assert engine.channel_active("sfx")
        assert engine.channel_active("ui")

    def test_stop_sfx_leaves_music(self):
        engine = self._make_engine()
        engine.tone(440, 500, channel="music")
        engine.tone(880, 500, channel="sfx")
        engine.stop("sfx")
        assert engine.channel_active("music")
        assert engine.playing


class TestSFXPool:
    def _make_engine(self):
        return AudioEngine()

    def test_multiple_sfx_voices(self):
        """Multiple SFX sounds can play simultaneously."""
        engine = self._make_engine()
        engine.tone(440, 500, channel="sfx")
        engine.tone(880, 500, channel="sfx")
        engine.tone(660, 500, channel="sfx")
        assert engine.sfx_active == 3

    def test_stop_sfx_clears_pool(self):
        """Stopping 'sfx' channel clears all pool voices."""
        engine = self._make_engine()
        engine.tone(440, 500, channel="sfx")
        engine.tone(880, 500, channel="sfx")
        engine.stop("sfx")
        assert engine.sfx_active == 0


class TestMixAdd:
    def test_simple_addition(self):
        """Two signals are summed sample-by-sample."""
        dst = bytearray(4)
        src = bytearray(4)
        # dst = [1000, 2000], src = [500, 1000]
        struct.pack_into("<hh", dst, 0, 1000, 2000)
        struct.pack_into("<hh", src, 0, 500, 1000)
        _mix_add_py(dst, src, 4)
        s0, s1 = struct.unpack_from("<hh", dst, 0)
        assert s0 == 1500
        assert s1 == 3000

    def test_positive_saturation(self):
        """Sum exceeding +32767 is clamped."""
        dst = bytearray(2)
        src = bytearray(2)
        struct.pack_into("<h", dst, 0, 30000)
        struct.pack_into("<h", src, 0, 10000)
        _mix_add_py(dst, src, 2)
        result = struct.unpack_from("<h", dst, 0)[0]
        assert result == 32767

    def test_negative_saturation(self):
        """Sum below -32768 is clamped."""
        dst = bytearray(2)
        src = bytearray(2)
        struct.pack_into("<h", dst, 0, -30000)
        struct.pack_into("<h", src, 0, -10000)
        _mix_add_py(dst, src, 2)
        result = struct.unpack_from("<h", dst, 0)[0]
        assert result == -32768

    def test_mixed_signs(self):
        """Positive + negative sums correctly."""
        dst = bytearray(2)
        src = bytearray(2)
        struct.pack_into("<h", dst, 0, 10000)
        struct.pack_into("<h", src, 0, -3000)
        _mix_add_py(dst, src, 2)
        result = struct.unpack_from("<h", dst, 0)[0]
        assert result == 7000

    def test_zero_src_is_noop(self):
        """Adding silence (zeros) leaves dst unchanged."""
        dst = bytearray(4)
        src = bytearray(4)  # zeros
        struct.pack_into("<hh", dst, 0, 5000, -5000)
        _mix_add_py(dst, src, 4)
        s0, s1 = struct.unpack_from("<hh", dst, 0)
        assert s0 == 5000
        assert s1 == -5000


class TestGainStaging:
    def test_gain_constants_are_reasonable(self):
        """Gain multipliers produce expected attenuation levels."""
        # 70% gain on a full-scale sample
        buf = bytearray(2)
        struct.pack_into("<h", buf, 0, 32767)
        _apply_volume_py(buf, 2, _GAIN_SFX)
        result = struct.unpack_from("<h", buf, 0)[0]
        # 32767 * 0.70 ≈ 22937
        assert 22000 < result < 24000

    def test_ducked_music_gain(self):
        """Ducked music at 25% is significantly quieter."""
        buf = bytearray(2)
        struct.pack_into("<h", buf, 0, 32767)
        _apply_volume_py(buf, 2, _GAIN_MUSIC_DUCKED)
        result = struct.unpack_from("<h", buf, 0)[0]
        # 32767 * 0.25 ≈ 8192
        assert 7500 < result < 9000

    def test_music_solo_vs_ducked(self):
        """Solo music is louder than ducked music."""
        buf_solo = bytearray(2)
        buf_duck = bytearray(2)
        struct.pack_into("<h", buf_solo, 0, 20000)
        struct.pack_into("<h", buf_duck, 0, 20000)
        _apply_volume_py(buf_solo, 2, _GAIN_MUSIC)
        _apply_volume_py(buf_duck, 2, _GAIN_MUSIC_DUCKED)
        solo = struct.unpack_from("<h", buf_solo, 0)[0]
        duck = struct.unpack_from("<h", buf_duck, 0)[0]
        assert solo > duck * 2  # solo is ~2.8x louder than ducked


class TestVolume:
    def test_set_volume(self):
        engine = AudioEngine()
        engine.volume = 50
        assert engine.volume == 50

    def test_clamp_volume(self):
        engine = AudioEngine()
        engine.volume = 150
        assert engine.volume == 100
        engine.volume = -10
        assert engine.volume == 0


class TestPlayWav:
    def _make_wav(self, n_samples=100):
        """Return bytes of a valid WAV file."""
        pcm = struct.pack("<{}h".format(n_samples), *range(n_samples))
        block_align = 2
        byte_rate = 16000 * block_align
        fmt_chunk = struct.pack(
            "<4sIHHIIHH", b"fmt ", 16, 1, 1, 16000, byte_rate, block_align, 16
        )
        data_chunk = struct.pack("<4sI", b"data", len(pcm)) + pcm
        body = fmt_chunk + data_chunk
        riff = struct.pack("<4sI4s", b"RIFF", 4 + len(body), b"WAVE")
        return riff + body

    def test_play_invalid_path(self):
        """Playing a non-existent file should not crash."""
        engine = AudioEngine()
        engine.play("/nonexistent/file.wav")
        assert not engine.playing
