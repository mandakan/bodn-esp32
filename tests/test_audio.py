"""Tests for bodn.audio — AudioEngine multi-voice mixing."""

import struct

import pytest

from bodn.audio import (
    AudioEngine,
    ToneSource,
    CH_UI,
    CH_SFX,
    CH_MUSIC,
    V_MUSIC,
    V_SFX_BASE,
    V_SFX_END,
    V_UI,
    _GAIN_MUSIC,
    _GAIN_MUSIC_DUCKED,
    _GAIN_SFX,
    _GAIN_UI,
    _mix_add_py,
    _apply_volume_py,
)


class FakeI2S:
    """I2S stub that records all writes."""

    RX = 0
    TX = 1
    MONO = 0

    def __init__(self):
        self.writes = []

    def write(self, buf):
        self.writes.append(bytes(buf))
        return len(buf)


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
        i2s = FakeI2S()
        engine = AudioEngine(i2s)
        return engine, i2s

    def test_initial_state(self):
        engine, _ = self._make_engine()
        assert not engine.playing
        assert engine.volume == 10

    def test_tone_activates(self):
        engine, _ = self._make_engine()
        engine.tone(440, 100)
        assert engine.playing

    def test_stop_channel(self):
        engine, _ = self._make_engine()
        engine.tone(440, 100, channel="sfx")
        engine.stop("sfx")
        assert not engine.playing

    def test_stop_all(self):
        engine, _ = self._make_engine()
        engine.tone(440, 100, channel="sfx")
        engine.tone(880, 100, channel="ui")
        engine.stop()
        assert not engine.playing

    def test_boop(self):
        engine, _ = self._make_engine()
        engine.boop()
        assert engine.playing
        # Boop should use ui voice
        assert engine._voices[V_UI].source is not None

    def test_music_and_sfx_coexist(self):
        """Both music and SFX voices can be active simultaneously."""
        engine, _ = self._make_engine()
        engine.tone(440, 500, channel="music")
        engine.tone(880, 500, channel="sfx")
        assert engine._voices[V_MUSIC].source is not None
        assert engine._voices[V_SFX_BASE].source is not None

    def test_all_voice_types_coexist(self):
        """Music, SFX, and UI can all be active at once."""
        engine, _ = self._make_engine()
        engine.tone(440, 500, channel="music")
        engine.tone(880, 500, channel="sfx")
        engine.tone(1000, 500, channel="ui")
        assert engine._voices[V_MUSIC].source is not None
        assert engine._voices[V_SFX_BASE].source is not None
        assert engine._voices[V_UI].source is not None

    def test_stop_sfx_leaves_music(self):
        engine, _ = self._make_engine()
        engine.tone(440, 500, channel="music")
        engine.tone(880, 500, channel="sfx")
        engine.stop("sfx")
        assert engine._voices[V_MUSIC].source is not None
        assert engine.playing


class TestSFXPool:
    def _make_engine(self):
        i2s = FakeI2S()
        return AudioEngine(i2s)

    def test_multiple_sfx_voices(self):
        """Multiple SFX sounds can play simultaneously."""
        engine = self._make_engine()
        engine.tone(440, 500, channel="sfx")
        engine.tone(880, 500, channel="sfx")
        engine.tone(660, 500, channel="sfx")
        # Should have 3 different SFX slots active
        active_sfx = sum(
            1
            for i in range(V_SFX_BASE, V_SFX_END)
            if engine._voices[i].source is not None
        )
        assert active_sfx == 3

    def test_pool_fills_four(self):
        """SFX pool holds 4 voices."""
        engine = self._make_engine()
        for freq in [440, 880, 660, 550]:
            engine.tone(freq, 500, channel="sfx")
        active_sfx = sum(
            1
            for i in range(V_SFX_BASE, V_SFX_END)
            if engine._voices[i].source is not None
        )
        assert active_sfx == 4

    def test_oldest_voice_stealing(self):
        """When SFX pool is full, the oldest voice is stolen."""
        engine = self._make_engine()
        # Fill all 4 SFX slots
        for freq in [440, 880, 660, 550]:
            engine.tone(freq, 500, channel="sfx")
        # Record which voice was started first (lowest _start_seq)
        oldest_seq = min(
            engine._voices[i]._start_seq for i in range(V_SFX_BASE, V_SFX_END)
        )
        # Play one more — should steal the oldest
        engine.tone(1000, 500, channel="sfx")
        # The oldest seq should no longer be present
        current_seqs = [
            engine._voices[i]._start_seq for i in range(V_SFX_BASE, V_SFX_END)
        ]
        assert oldest_seq not in current_seqs
        # Still 4 active
        active_sfx = sum(
            1
            for i in range(V_SFX_BASE, V_SFX_END)
            if engine._voices[i].source is not None
        )
        assert active_sfx == 4

    def test_stop_sfx_clears_pool(self):
        """Stopping 'sfx' channel clears all pool voices."""
        engine = self._make_engine()
        engine.tone(440, 500, channel="sfx")
        engine.tone(880, 500, channel="sfx")
        engine.stop("sfx")
        active_sfx = sum(
            1
            for i in range(V_SFX_BASE, V_SFX_END)
            if engine._voices[i].source is not None
        )
        assert active_sfx == 0


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

    def test_ui_gain_highest(self):
        """UI gain is higher than SFX gain."""
        assert _GAIN_UI > _GAIN_SFX

    def test_voice_gain_assignment(self):
        """Voices are created with correct gain multipliers."""
        engine = AudioEngine(FakeI2S())
        assert engine._voices[V_MUSIC].gain_mult == _GAIN_MUSIC
        assert engine._voices[V_MUSIC].is_music is True
        for i in range(V_SFX_BASE, V_SFX_END):
            assert engine._voices[i].gain_mult == _GAIN_SFX
            assert engine._voices[i].is_music is False
        assert engine._voices[V_UI].gain_mult == _GAIN_UI
        assert engine._voices[V_UI].is_music is False


class TestVolume:
    def test_set_volume(self):
        engine, _ = TestAudioEngine()._make_engine()
        engine.volume = 50
        assert engine.volume == 50

    def test_clamp_volume(self):
        engine, _ = TestAudioEngine()._make_engine()
        engine.volume = 150
        assert engine.volume == 100
        engine.volume = -10
        assert engine.volume == 0

    def test_volume_scaling(self):
        engine, _ = TestAudioEngine()._make_engine()
        engine.volume = 50

        # Create a buffer with known samples
        buf = bytearray(4)
        struct.pack_into("<h", buf, 0, 10000)
        struct.pack_into("<h", buf, 2, -10000)

        engine._apply_volume(buf, 4)

        s0 = struct.unpack_from("<h", buf, 0)[0]
        s1 = struct.unpack_from("<h", buf, 2)[0]
        # At 50% volume, samples should be roughly halved
        assert 4000 < s0 < 6000
        assert -6000 < s1 < -4000

    def test_full_volume_no_change(self):
        engine, _ = TestAudioEngine()._make_engine()
        engine.volume = 100

        buf = bytearray(4)
        struct.pack_into("<h", buf, 0, 20000)
        original = bytes(buf)

        engine._apply_volume(buf, 4)
        assert buf[:4] == original[:4]


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
        engine, _ = TestAudioEngine()._make_engine()
        engine.play("/nonexistent/file.wav")
        assert not engine.playing
