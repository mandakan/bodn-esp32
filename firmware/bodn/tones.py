# bodn/tones.py — procedural tone generation (pure logic, no hardware)
#
# Fills a pre-allocated bytearray with PCM 16-bit LE mono samples.
# All integer math in the sample loop for ESP32 performance.
# Viper-accelerated inner loops when available (~10-20x speedup).

import math

try:
    import micropython

    try:

        @micropython.viper
        def _viper_probe():
            pass

        _has_viper = True
    except (AttributeError, NotImplementedError):
        _has_viper = False
except ImportError:
    micropython = None
    _has_viper = False

# 256-entry sine lookup table (int16 range)
_SINE_LUT = [int(32767 * math.sin(2 * math.pi * i / 256)) for i in range(256)]

# Packed LUT as bytearray for viper (512 bytes: 256 × 2-byte LE int16).
# Viper can't index Python lists, so we pre-pack the LUT into a flat
# byte buffer and read it with ptr8.
_SINE_LUT_BUF = bytearray(512)
for _i, _v in enumerate(_SINE_LUT):
    _uv = _v & 0xFFFF
    _SINE_LUT_BUF[_i * 2] = _uv & 0xFF
    _SINE_LUT_BUF[_i * 2 + 1] = (_uv >> 8) & 0xFF
del _i, _uv


# ---------------------------------------------------------------------------
# Pure-Python fallback implementations
# ---------------------------------------------------------------------------


def _generate_square_py(buf, n_samples, period, half, phase_offset):
    for i in range(n_samples):
        phase = (i + phase_offset) % period
        val = 32767 if phase < half else -32767
        buf[i * 2] = val & 0xFF
        buf[i * 2 + 1] = (val >> 8) & 0xFF


def _generate_sine_py(buf, n_samples, period, phase_offset):
    lut = _SINE_LUT
    for i in range(n_samples):
        idx = ((i + phase_offset) * 256 // period) % 256
        val = lut[idx]
        buf[i * 2] = val & 0xFF
        buf[i * 2 + 1] = (val >> 8) & 0xFF


def _generate_sawtooth_py(buf, n_samples, period, phase_offset):
    for i in range(n_samples):
        phase = (i + phase_offset) % period
        val = (phase * 65534 // period) - 32767
        buf[i * 2] = val & 0xFF
        buf[i * 2 + 1] = (val >> 8) & 0xFF


# ---------------------------------------------------------------------------
# Viper-accelerated implementations (~10-20x faster)
# ---------------------------------------------------------------------------

if _has_viper:

    @micropython.viper
    def _generate_square_viper(
        buf_ptr, n_samples: int, period: int, half: int, phase_offset: int
    ):
        p = ptr8(buf_ptr)  # noqa: F821
        i = 0
        while i < n_samples:
            phase = int((i + phase_offset) % period)
            if phase < half:
                val = 32767
            else:
                val = -32767
            off = i * 2
            p[off] = val & 0xFF
            p[off + 1] = (val >> 8) & 0xFF
            i += 1

    @micropython.viper
    def _generate_sine_viper(
        buf_ptr, n_samples: int, period: int, phase_offset: int, lut_ptr
    ):
        p = ptr8(buf_ptr)  # noqa: F821
        lut = ptr8(lut_ptr)  # noqa: F821
        i = 0
        while i < n_samples:
            idx = int(((i + phase_offset) * 256 // period) % 256)
            # Read LE int16 from packed LUT
            lut_off = idx * 2
            lo = int(lut[lut_off])
            hi = int(lut[lut_off + 1])
            off = i * 2
            p[off] = lo
            p[off + 1] = hi
            i += 1

    @micropython.viper
    def _generate_sawtooth_viper(
        buf_ptr, n_samples: int, period: int, phase_offset: int
    ):
        p = ptr8(buf_ptr)  # noqa: F821
        i = 0
        while i < n_samples:
            phase = int((i + phase_offset) % period)
            val = int((phase * 65534 // period) - 32767)
            off = i * 2
            p[off] = val & 0xFF
            p[off + 1] = (val >> 8) & 0xFF
            i += 1

    _gen_square = _generate_square_viper
    _gen_sine = _generate_sine_viper
    _gen_sawtooth = _generate_sawtooth_viper
else:
    _gen_square = _generate_square_py
    _gen_sine = _generate_sine_py
    _gen_sawtooth = _generate_sawtooth_py


def generate(buf, freq_hz, sample_rate=16000, wave="square", phase_offset=0):
    """Fill *buf* with PCM 16-bit LE mono samples at *freq_hz*.

    Supported waveforms: 'square', 'sine', 'sawtooth', 'triangle',
    'noise' (decaying), 'noise_pitched' (sample-and-hold at freq_hz).
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
        _gen_square(buf, n_samples, period, half, phase_offset)

    elif wave == "sine":
        if _has_viper:
            _gen_sine(buf, n_samples, period, phase_offset, _SINE_LUT_BUF)
        else:
            _gen_sine(buf, n_samples, period, phase_offset)

    elif wave == "sawtooth":
        _gen_sawtooth(buf, n_samples, period, phase_offset)

    elif wave == "triangle":
        _generate_triangle_py(buf, n_samples, period, phase_offset)

    elif wave == "noise_pitched":
        return (
            _generate_noise_pitched(buf, n_samples, period, phase_offset),
            phase_offset + n_samples,
        )

    else:
        return 0, phase_offset

    return n_samples * 2, phase_offset + n_samples


def _generate_triangle_py(buf, n_samples, period, phase_offset):
    """Triangle wave — symmetric rise/fall over one period."""
    if period < 1:
        period = 1
    half = period // 2
    if half < 1:
        half = 1
    for i in range(n_samples):
        pos = (phase_offset + i) % period
        if pos < half:
            # rising: -32768 → +32767 across first half
            val = -32768 + (pos * 65535) // half
        else:
            # falling: +32767 → -32768 across second half
            q = pos - half
            denom = period - half
            if denom < 1:
                denom = 1
            val = 32767 - (q * 65535) // denom
        if val > 32767:
            val = 32767
        if val < -32768:
            val = -32768
        lo = val & 0xFF
        hi = (val >> 8) & 0xFF
        buf[2 * i] = lo
        buf[2 * i + 1] = hi


def _generate_noise_pitched(buf, n_samples, period, phase_offset):
    """Sample-and-hold LFSR with triangular decay per period.

    Each LFSR tick latches a fresh amplitude; the held value then decays
    linearly back to zero across the period, so the perceived fundamental
    at freq_hz is clearly audible instead of smeared into white noise.
    """
    if period < 1:
        period = 1
    lfsr = 0xACE1
    wraps = phase_offset // period
    for _ in range(wraps):
        bit = lfsr & 1
        lfsr >>= 1
        if bit:
            lfsr ^= 0xB400
    pos = phase_offset % period
    held = (lfsr & 0xFFFF) - 32768
    for i in range(n_samples):
        # Decay envelope: 1.0 at pos=0 → ~0 as pos approaches period.
        env_num = period - pos
        val = (held * env_num) // period
        if val > 32767:
            val = 32767
        if val < -32768:
            val = -32768
        lo = val & 0xFF
        hi = (val >> 8) & 0xFF
        buf[2 * i] = lo
        buf[2 * i + 1] = hi
        pos += 1
        if pos >= period:
            pos = 0
            bit = lfsr & 1
            lfsr >>= 1
            if bit:
                lfsr ^= 0xB400
            held = (lfsr & 0xFFFF) - 32768
    return n_samples * 2


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
