"""Tests for bodn.tones — procedural tone generation."""

import struct

from bodn.tones import generate, _SINE_LUT


def _unpack_samples(buf, n_bytes):
    """Unpack int16 LE samples from buffer."""
    return [struct.unpack_from("<h", buf, i)[0] for i in range(0, n_bytes, 2)]


class TestSineLUT:
    def test_length(self):
        assert len(_SINE_LUT) == 256

    def test_range(self):
        for val in _SINE_LUT:
            assert -32768 <= val <= 32767

    def test_zero_crossing(self):
        """LUT should start near zero and cross zero at index 128."""
        assert abs(_SINE_LUT[0]) < 500  # near zero at start
        assert abs(_SINE_LUT[128]) < 500  # near zero at half cycle


class TestSquareWave:
    def test_output_size(self):
        buf = bytearray(200)
        n = generate(buf, 1000, sample_rate=16000, wave="square")
        assert n == 200  # fills entire buffer

    def test_amplitude(self):
        buf = bytearray(400)
        generate(buf, 1000, sample_rate=16000, wave="square")
        samples = _unpack_samples(buf, 400)
        for s in samples:
            assert s == 32767 or s == -32767

    def test_period(self):
        """At 1000 Hz / 16000 SR, period should be 16 samples."""
        buf = bytearray(64)  # 32 samples
        generate(buf, 1000, sample_rate=16000, wave="square")
        samples = _unpack_samples(buf, 64)
        # First half of period should be positive
        assert samples[0] == 32767
        # Second half should be negative (period=16, half=8)
        assert samples[8] == -32767
        # Next period starts positive again
        assert samples[16] == 32767

    def test_odd_buffer_byte_ignored(self):
        """Odd trailing byte should not be written."""
        buf = bytearray(5)
        n = generate(buf, 440, wave="square")
        assert n == 4  # only 2 samples = 4 bytes


class TestSineWave:
    def test_output_size(self):
        buf = bytearray(200)
        n = generate(buf, 440, wave="sine")
        assert n == 200

    def test_amplitude_range(self):
        buf = bytearray(400)
        generate(buf, 440, wave="sine")
        samples = _unpack_samples(buf, 400)
        for s in samples:
            assert -32768 <= s <= 32767


class TestSawtoothWave:
    def test_output_size(self):
        buf = bytearray(200)
        n = generate(buf, 440, wave="sawtooth")
        assert n == 200

    def test_ramp(self):
        """First period should ramp from negative to positive."""
        buf = bytearray(64)
        generate(buf, 1000, sample_rate=16000, wave="sawtooth")
        samples = _unpack_samples(buf, 64)
        # First sample should be near -32767
        assert samples[0] < -30000
        # Sample near end of first period should be positive and high
        assert samples[15] > 28000


class TestEdgeCases:
    def test_zero_freq(self):
        buf = bytearray(100)
        n = generate(buf, 0)
        assert n == 0

    def test_unknown_wave(self):
        buf = bytearray(100)
        n = generate(buf, 440, wave="triangle")
        assert n == 0

    def test_empty_buffer(self):
        buf = bytearray(0)
        n = generate(buf, 440)
        assert n == 0
