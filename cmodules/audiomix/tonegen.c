// tonegen.c — procedural tone generation
//
// Direct port of firmware/bodn/tones.py with identical integer math.
// Runs on core 1 — no Python objects, no allocations.

#include "tonegen.h"
#include "audiomix.h"

// 256-entry sine lookup table (int16 range, matches Python _SINE_LUT)
static const int16_t sine_lut[256] = {
        0,    804,   1608,   2410,   3212,   4011,   4808,   5602,
     6393,   7179,   7962,   8739,   9512,  10278,  11039,  11793,
    12539,  13279,  14010,  14732,  15446,  16151,  16846,  17530,
    18204,  18868,  19519,  20159,  20787,  21403,  22005,  22594,
    23170,  23731,  24279,  24811,  25329,  25832,  26319,  26790,
    27245,  27683,  28105,  28510,  28898,  29268,  29621,  29956,
    30273,  30571,  30852,  31113,  31356,  31580,  31785,  31971,
    32137,  32285,  32412,  32521,  32609,  32678,  32728,  32757,
    32767,  32757,  32728,  32678,  32609,  32521,  32412,  32285,
    32137,  31971,  31785,  31580,  31356,  31113,  30852,  30571,
    30273,  29956,  29621,  29268,  28898,  28510,  28105,  27683,
    27245,  26790,  26319,  25832,  25329,  24811,  24279,  23731,
    23170,  22594,  22005,  21403,  20787,  20159,  19519,  18868,
    18204,  17530,  16846,  16151,  15446,  14732,  14010,  13279,
    12539,  11793,  11039,  10278,   9512,   8739,   7962,   7179,
     6393,   5602,   4808,   4011,   3212,   2410,   1608,    804,
        0,   -804,  -1608,  -2410,  -3212,  -4011,  -4808,  -5602,
    -6393,  -7179,  -7962,  -8739,  -9512, -10278, -11039, -11793,
   -12539, -13279, -14010, -14732, -15446, -16151, -16846, -17530,
   -18204, -18868, -19519, -20159, -20787, -21403, -22005, -22594,
   -23170, -23731, -24279, -24811, -25329, -25832, -26319, -26790,
   -27245, -27683, -28105, -28510, -28898, -29268, -29621, -29956,
   -30273, -30571, -30852, -31113, -31356, -31580, -31785, -31971,
   -32137, -32285, -32412, -32521, -32609, -32678, -32728, -32757,
   -32767, -32757, -32728, -32678, -32609, -32521, -32412, -32285,
   -32137, -31971, -31785, -31580, -31356, -31113, -30852, -30571,
   -30273, -29956, -29621, -29268, -28898, -28510, -28105, -27683,
   -27245, -26790, -26319, -25832, -25329, -24811, -24279, -23731,
   -23170, -22594, -22005, -21403, -20787, -20159, -19519, -18868,
   -18204, -17530, -16846, -16151, -15446, -14732, -14010, -13279,
   -12539, -11793, -11039, -10278,  -9512,  -8739,  -7962,  -7179,
    -6393,  -5602,  -4808,  -4011,  -3212,  -2410,  -1608,   -804,
};

uint32_t tonegen_square(int16_t *out, uint32_t n_samples,
                        uint32_t period, uint32_t phase) {
    if (period < 1) period = 1;
    uint32_t half = period / 2;
    for (uint32_t i = 0; i < n_samples; i++) {
        uint32_t p = (i + phase) % period;
        out[i] = (p < half) ? 32767 : -32767;
    }
    return phase + n_samples;
}

uint32_t tonegen_sine(int16_t *out, uint32_t n_samples,
                      uint32_t period, uint32_t phase) {
    if (period < 1) period = 1;
    for (uint32_t i = 0; i < n_samples; i++) {
        uint32_t idx = ((i + phase) * 256 / period) % 256;
        out[i] = sine_lut[idx];
    }
    return phase + n_samples;
}

uint32_t tonegen_sawtooth(int16_t *out, uint32_t n_samples,
                          uint32_t period, uint32_t phase) {
    if (period < 1) period = 1;
    for (uint32_t i = 0; i < n_samples; i++) {
        uint32_t p = (i + phase) % period;
        out[i] = (int16_t)((p * 65534 / period) - 32767);
    }
    return phase + n_samples;
}

void tonegen_noise(int16_t *out, uint32_t n_samples,
                   uint32_t decay_rate, uint32_t sample_rate) {
    // Matches Python: fixed seed, Galois LFSR, exponential decay
    uint32_t lfsr = 0xACE1;
    int32_t decay_mult = 65536 - (decay_rate * 65536 / sample_rate);
    if (decay_mult < 0) decay_mult = 0;
    int32_t amp = 32767;

    for (uint32_t i = 0; i < n_samples; i++) {
        // 16-bit Galois LFSR (taps: 16, 15, 13, 4)
        uint32_t bit = lfsr & 1;
        lfsr >>= 1;
        if (bit) lfsr ^= 0xB400;
        // Map to signed and scale by amplitude
        int32_t raw = (int32_t)(lfsr & 0xFFFF) - 32768;
        int32_t val = (raw * amp) >> 15;
        // Clamp to int16
        if (val > 32767) val = 32767;
        if (val < -32768) val = -32768;
        out[i] = (int16_t)val;
        // Decay
        amp = (amp * decay_mult) >> 16;
    }
}

void tonegen_fade(int16_t *buf, uint32_t n_samples,
                  int fade_in, int fade_out, uint32_t fade_len) {
    if (fade_in) {
        uint32_t fin = (fade_len < n_samples) ? fade_len : n_samples;
        for (uint32_t i = 0; i < fin; i++) {
            int32_t val = buf[i];
            val = (fin > 1) ? (val * (int32_t)i / (int32_t)(fin - 1)) : 0;
            buf[i] = (int16_t)val;
        }
    }
    if (fade_out) {
        uint32_t fout = (fade_len < n_samples) ? fade_len : n_samples;
        uint32_t start = n_samples - fout;
        for (uint32_t i = 0; i < fout; i++) {
            int32_t val = buf[start + i];
            val = (fout > 1)
                ? (val * (int32_t)(fout - 1 - i) / (int32_t)(fout - 1))
                : 0;
            buf[start + i] = (int16_t)val;
        }
    }
}
