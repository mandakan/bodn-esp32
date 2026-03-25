"""Tests for bodn.audio — AudioEngine priority channels and playback."""

import io
import struct

import pytest

from bodn.audio import AudioEngine, ToneSource, CH_UI, CH_SFX, CH_MUSIC


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
        # Boop should use ui channel
        assert engine._channels[CH_UI].source is not None

    def test_channel_priority(self):
        engine, _ = self._make_engine()
        engine.tone(440, 500, channel="music")
        engine.tone(880, 500, channel="sfx")
        # SFX has higher priority
        assert engine._active_channel() == CH_SFX

    def test_ui_highest_priority(self):
        engine, _ = self._make_engine()
        engine.tone(440, 500, channel="music")
        engine.tone(880, 500, channel="sfx")
        engine.tone(1000, 500, channel="ui")
        assert engine._active_channel() == CH_UI

    def test_fallback_to_lower(self):
        engine, _ = self._make_engine()
        engine.tone(440, 500, channel="music")
        engine.tone(880, 500, channel="sfx")
        engine.stop("sfx")
        assert engine._active_channel() == CH_MUSIC


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
