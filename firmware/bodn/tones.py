# bodn/tones.py — procedural tone generation (pure logic, no hardware)
#
# Fills a pre-allocated bytearray with PCM 16-bit LE mono samples.
# All integer math in the sample loop for ESP32 performance.

import math

# 256-entry sine lookup table (int16 range)
_SINE_LUT = [int(32767 * math.sin(2 * math.pi * i / 256)) for i in range(256)]


def generate(buf, freq_hz, sample_rate=16000, wave="square", phase_offset=0):
    """Fill *buf* with PCM 16-bit LE mono samples at *freq_hz*.

    Supported waveforms: 'square', 'sine', 'sawtooth', 'noise'.
    For 'noise', freq_hz controls the decay rate: higher = faster decay.
    *phase_offset* is the sample index to start from (for phase continuity
    across multiple calls). Returns (bytes_written, next_phase_offset).
    """
    if sample_rate <= 0:
        return 0, phase_offset

    n_samples = len(buf) // 2  # 2 bytes per sample

    if wave == "noise":
        return _generate_noise(buf, n_samples, freq_hz, sample_rate), phase_offset

    if freq_hz <= 0:
        return 0, phase_offset

    period = sample_rate // freq_hz if freq_hz <= sample_rate else 1
    if period < 1:
        period = 1

    if wave == "square":
        half = period // 2
        for i in range(n_samples):
            phase = (i + phase_offset) % period
            val = 32767 if phase < half else -32767
            buf[i * 2] = val & 0xFF
            buf[i * 2 + 1] = (val >> 8) & 0xFF

    elif wave == "sine":
        for i in range(n_samples):
            # Map sample position to 0-255 LUT index
            idx = ((i + phase_offset) * 256 // period) % 256
            val = _SINE_LUT[idx]
            buf[i * 2] = val & 0xFF
            buf[i * 2 + 1] = (val >> 8) & 0xFF

    elif wave == "sawtooth":
        for i in range(n_samples):
            phase = (i + phase_offset) % period
            # Linear ramp from -32767 to 32767
            val = (phase * 65534 // period) - 32767
            buf[i * 2] = val & 0xFF
            buf[i * 2 + 1] = (val >> 8) & 0xFF

    else:
        return 0, phase_offset

    return n_samples * 2, phase_offset + n_samples


def _generate_noise(buf, n_samples, decay_rate, sample_rate):
    """Generate noise with exponential decay — sounds like a click or tick.

    decay_rate: higher = faster decay. ~4000 gives a sharp 2-3ms click,
    ~1000 gives a softer 8-10ms tick.

    Uses a fixed LFSR seed so every click sounds identical.
    """
    lfsr = 0xACE1  # fixed seed — deterministic output

    # Exponential decay via fixed-point: amplitude *= (1 - decay_rate/sample_rate)
    # Pre-compute as a 16-bit multiplier applied each sample.
    # decay_mult = int(65536 * (1 - decay_rate / sample_rate))
    decay_mult = max(0, 65536 - (decay_rate * 65536 // sample_rate))
    amp = 32767  # start at full scale

    for i in range(n_samples):
        # 16-bit Galois LFSR (taps: 16, 15, 13, 4)
        bit = lfsr & 1
        lfsr >>= 1
        if bit:
            lfsr ^= 0xB400
        # Map LFSR to signed int16 and scale by decaying amplitude
        raw = (lfsr & 0xFFFF) - 32768
        val = (raw * amp) >> 15
        buf[i * 2] = val & 0xFF
        buf[i * 2 + 1] = (val >> 8) & 0xFF
        # Decay amplitude
        amp = (amp * decay_mult) >> 16

    return n_samples * 2
