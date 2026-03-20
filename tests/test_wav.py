"""Tests for bodn.wav — WAV header parsing and streaming reader."""

import io
import struct

import pytest

from bodn.wav import WavReader, WavError


def _make_wav(
    sample_rate=16000,
    bits=16,
    channels=1,
    data=b"",
    audio_format=1,
    extra_chunks=b"",
):
    """Build a minimal WAV file in memory."""
    block_align = channels * (bits // 8)
    byte_rate = sample_rate * block_align

    fmt_chunk = struct.pack(
        "<4sIHHIIHH",
        b"fmt ",
        16,  # chunk size
        audio_format,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits,
    )
    data_chunk = struct.pack("<4sI", b"data", len(data)) + data

    body = fmt_chunk + extra_chunks + data_chunk
    riff_header = struct.pack("<4sI4s", b"RIFF", 4 + len(body), b"WAVE")
    return riff_header + body


class TestValidWav:
    def test_mono_16bit(self):
        pcm = struct.pack("<4h", 100, -200, 300, -400)
        f = io.BytesIO(_make_wav(data=pcm))
        wav = WavReader(f)
        assert wav.sample_rate == 16000
        assert wav.bits_per_sample == 16
        assert wav.channels == 1
        assert wav.data_size == len(pcm)

    def test_read_chunk(self):
        pcm = struct.pack("<4h", 100, -200, 300, -400)
        f = io.BytesIO(_make_wav(data=pcm))
        wav = WavReader(f)
        buf = bytearray(16)
        n = wav.read_chunk(buf)
        assert n == 8
        assert buf[:n] == pcm

    def test_eof(self):
        pcm = struct.pack("<2h", 100, -200)
        f = io.BytesIO(_make_wav(data=pcm))
        wav = WavReader(f)
        buf = bytearray(64)
        n1 = wav.read_chunk(buf)
        assert n1 == 4
        n2 = wav.read_chunk(buf)
        assert n2 == 0

    def test_seek_start(self):
        pcm = struct.pack("<2h", 1000, -1000)
        f = io.BytesIO(_make_wav(data=pcm))
        wav = WavReader(f)
        buf = bytearray(64)
        wav.read_chunk(buf)
        wav.read_chunk(buf)  # EOF
        wav.seek_start()
        n = wav.read_chunk(buf)
        assert n == 4
        vals = struct.unpack_from("<2h", buf)
        assert vals == (1000, -1000)

    def test_8bit_mono(self):
        """8-bit unsigned samples should be converted to 16-bit signed."""
        pcm_8 = bytes([128, 0, 255])  # silence, min, max
        f = io.BytesIO(_make_wav(bits=8, data=pcm_8))
        wav = WavReader(f)
        buf = bytearray(64)
        n = wav.read_chunk(buf)
        assert n == 6  # 3 samples × 2 bytes
        samples = [struct.unpack_from("<h", buf, i)[0] for i in range(0, n, 2)]
        assert samples[0] == 0  # 128 → silence
        assert samples[1] == -32768  # 0 → min
        assert samples[2] == 32512  # 255 → near max

    def test_stereo_extracts_left(self):
        """Stereo should extract left channel only."""
        # left=1000, right=2000, left=-500, right=-600
        pcm = struct.pack("<4h", 1000, 2000, -500, -600)
        f = io.BytesIO(_make_wav(channels=2, data=pcm))
        wav = WavReader(f)
        buf = bytearray(64)
        n = wav.read_chunk(buf)
        assert n == 4  # 2 mono samples
        samples = [struct.unpack_from("<h", buf, i)[0] for i in range(0, n, 2)]
        assert samples[0] == 1000
        assert samples[1] == -500


class TestUnknownChunks:
    def test_skips_unknown_chunks(self):
        """Unknown chunks between fmt and data should be skipped."""
        junk = struct.pack("<4sI", b"JUNK", 4) + b"\x00" * 4
        pcm = struct.pack("<2h", 100, 200)
        f = io.BytesIO(_make_wav(data=pcm, extra_chunks=junk))
        wav = WavReader(f)
        buf = bytearray(16)
        n = wav.read_chunk(buf)
        assert n == 4


class TestInvalidWav:
    def test_not_riff(self):
        with pytest.raises(WavError, match="not a WAV"):
            WavReader(io.BytesIO(b"NOT_RIFF_DATA_HERE"))

    def test_too_short(self):
        with pytest.raises(WavError, match="too short"):
            WavReader(io.BytesIO(b"RIFF"))

    def test_not_pcm(self):
        with pytest.raises(WavError, match="not PCM"):
            WavReader(io.BytesIO(_make_wav(audio_format=3)))

    def test_unsupported_bits(self):
        with pytest.raises(WavError, match="unsupported bits"):
            WavReader(io.BytesIO(_make_wav(bits=24)))

    def test_no_data_chunk(self):
        """WAV with fmt but no data chunk."""
        fmt_chunk = struct.pack("<4sIHHIIHH", b"fmt ", 16, 1, 1, 16000, 32000, 2, 16)
        riff = struct.pack("<4sI4s", b"RIFF", 4 + len(fmt_chunk), b"WAVE")
        with pytest.raises(WavError, match="no data"):
            WavReader(io.BytesIO(riff + fmt_chunk))


class TestSmallBuffer:
    def test_chunked_reading(self):
        """Reading in small chunks should still produce all data."""
        n_samples = 100
        pcm = struct.pack("<{}h".format(n_samples), *range(n_samples))
        f = io.BytesIO(_make_wav(data=pcm))
        wav = WavReader(f)

        collected = bytearray()
        buf = bytearray(16)  # small buffer — 8 samples at a time
        while True:
            n = wav.read_chunk(buf)
            if n == 0:
                break
            collected.extend(buf[:n])

        assert len(collected) == n_samples * 2
        result = struct.unpack("<{}h".format(n_samples), collected)
        assert result == tuple(range(n_samples))
