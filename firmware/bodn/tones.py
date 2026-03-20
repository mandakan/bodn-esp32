# bodn/tones.py — procedural tone generation (pure logic, no hardware)
#
# Fills a pre-allocated bytearray with PCM 16-bit LE mono samples.
# All integer math in the sample loop for ESP32 performance.

import math

# 256-entry sine lookup table (int16 range)
_SINE_LUT = [int(32767 * math.sin(2 * math.pi * i / 256)) for i in range(256)]


def generate(buf, freq_hz, sample_rate=16000, wave="square"):
    """Fill *buf* with PCM 16-bit LE mono samples at *freq_hz*.

    Supported waveforms: 'square', 'sine', 'sawtooth'.
    Returns number of bytes written (always even).
    """
    if freq_hz <= 0 or sample_rate <= 0:
        return 0

    n_samples = len(buf) // 2  # 2 bytes per sample
    period = sample_rate // freq_hz if freq_hz <= sample_rate else 1
    if period < 1:
        period = 1

    if wave == "square":
        half = period // 2
        for i in range(n_samples):
            phase = i % period
            val = 32767 if phase < half else -32767
            buf[i * 2] = val & 0xFF
            buf[i * 2 + 1] = (val >> 8) & 0xFF

    elif wave == "sine":
        for i in range(n_samples):
            # Map sample position to 0-255 LUT index
            idx = (i * 256 // period) % 256
            val = _SINE_LUT[idx]
            buf[i * 2] = val & 0xFF
            buf[i * 2 + 1] = (val >> 8) & 0xFF

    elif wave == "sawtooth":
        for i in range(n_samples):
            phase = i % period
            # Linear ramp from -32767 to 32767
            val = (phase * 65534 // period) - 32767
            buf[i * 2] = val & 0xFF
            buf[i * 2 + 1] = (val >> 8) & 0xFF

    else:
        return 0

    return n_samples * 2
