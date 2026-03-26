# bodn/wav.py — WAV header parser and streaming chunk reader (pure logic)
#
# Accepts any file-like object with read() and seek().  Supports 8-bit
# and 16-bit PCM, mono and stereo (left channel extracted from stereo).
# Zero per-call allocations — reads directly into caller's buffer.

import struct


class WavError(Exception):
    pass


class WavReader:
    """Streaming WAV file reader.

    Usage::

        with open("/sd/sound.wav", "rb") as f:
            wav = WavReader(f)
            while wav.read_chunk(buf) > 0:
                i2s.write(buf)
    """

    def __init__(self, file_obj):
        self._f = file_obj
        self._data_start = 0
        self._data_size = 0
        self._bytes_left = 0
        self.sample_rate = 0
        self.bits_per_sample = 0
        self.channels = 0
        self.data_size = 0
        self._block_align = 0
        self._parse_header()

    def _parse_header(self):
        f = self._f

        # RIFF header
        riff = f.read(12)
        if len(riff) < 12:
            raise WavError("too short")
        if riff[0:4] != b"RIFF" or riff[8:12] != b"WAVE":
            raise WavError("not a WAV file")

        # Walk chunks to find 'fmt ' and 'data'
        found_fmt = False
        found_data = False

        while not (found_fmt and found_data):
            chunk_hdr = f.read(8)
            if len(chunk_hdr) < 8:
                break
            chunk_id = chunk_hdr[0:4]
            chunk_size = struct.unpack("<I", chunk_hdr[4:8])[0]

            if chunk_id == b"fmt ":
                if chunk_size < 16:
                    raise WavError("fmt chunk too small")
                fmt_data = f.read(16)
                if len(fmt_data) < 16:
                    raise WavError("truncated fmt")
                audio_fmt = struct.unpack("<H", fmt_data[0:2])[0]
                if audio_fmt != 1:
                    raise WavError("not PCM (format={})".format(audio_fmt))
                self.channels = struct.unpack("<H", fmt_data[2:4])[0]
                self.sample_rate = struct.unpack("<I", fmt_data[4:8])[0]
                self.bits_per_sample = struct.unpack("<H", fmt_data[14:16])[0]
                self._block_align = struct.unpack("<H", fmt_data[12:14])[0]
                if self.bits_per_sample not in (8, 16):
                    raise WavError("unsupported bits={}".format(self.bits_per_sample))
                # Skip any extra fmt bytes
                extra = chunk_size - 16
                if extra > 0:
                    f.read(extra)
                found_fmt = True

            elif chunk_id == b"data":
                self._data_start = f.tell() if hasattr(f, "tell") else 0
                self._data_size = chunk_size
                self.data_size = chunk_size
                self._bytes_left = chunk_size
                found_data = True

            else:
                # Skip unknown chunks
                f.read(chunk_size)

        if not found_fmt:
            raise WavError("no fmt chunk")
        if not found_data:
            raise WavError("no data chunk")

    def read_chunk(self, buf):
        """Read PCM data into *buf*.  Returns bytes written (0 = EOF).

        For stereo files, extracts the left channel into mono 16-bit output.
        For 8-bit files, converts to 16-bit LE in-place.
        """
        if self._bytes_left <= 0:
            return 0

        f = self._f
        mono_16 = self.channels == 1 and self.bits_per_sample == 16

        if mono_16:
            # Fast path: read directly into buffer (zero-alloc)
            to_read = min(len(buf), self._bytes_left)
            # Align to sample boundary
            to_read = (to_read // 2) * 2
            if to_read >= len(buf):
                # Common case: full buffer read, no slice needed
                n = f.readinto(buf)
            else:
                # Near EOF: read only remaining bytes
                n = f.readinto(memoryview(buf)[:to_read])
            if n is None:
                n = 0
            self._bytes_left -= n
            return n

        # Slow paths: stereo or 8-bit need conversion
        out_pos = 0
        out_limit = len(buf)
        block = self._block_align

        while out_pos + 2 <= out_limit and self._bytes_left >= block:
            raw = f.read(block)
            if len(raw) < block:
                break
            self._bytes_left -= block

            if self.bits_per_sample == 16:
                # Take left channel (first 2 bytes of block)
                val = struct.unpack("<h", raw[0:2])[0]
            else:
                # 8-bit unsigned → 16-bit signed
                val = (raw[0] - 128) * 256

            buf[out_pos] = val & 0xFF
            buf[out_pos + 1] = (val >> 8) & 0xFF
            out_pos += 2

        return out_pos

    def seek_start(self):
        """Seek back to the start of audio data (for looping)."""
        self._f.seek(self._data_start)
        self._bytes_left = self._data_size
