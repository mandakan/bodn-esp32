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

int16_t tonegen_lfo_sine(uint32_t phase_q16) {
    return sine_lut[(phase_q16 >> 8) & 0xFF];
}

// Phase is a 16-bit cycle counter (0..65535 = one full cycle).  Each sample
// advances by inc_q16; the accumulator wraps naturally in 32-bit math and is
// masked to 16 bits on return.  Because the wrap point doesn't depend on the
// frequency, freq changes mid-stream are phase-continuous → no click.

uint32_t tonegen_square(int16_t *out, uint32_t n_samples,
                        uint32_t inc_q16, uint32_t phase_q16) {
    uint32_t phase = phase_q16 & 0xFFFF;
    uint32_t inc = inc_q16 & 0xFFFF;
    for (uint32_t i = 0; i < n_samples; i++) {
        out[i] = (phase < 0x8000) ? 32767 : -32767;
        phase = (phase + inc) & 0xFFFF;
    }
    return phase;
}

uint32_t tonegen_sine(int16_t *out, uint32_t n_samples,
                      uint32_t inc_q16, uint32_t phase_q16) {
    uint32_t phase = phase_q16 & 0xFFFF;
    uint32_t inc = inc_q16 & 0xFFFF;
    for (uint32_t i = 0; i < n_samples; i++) {
        out[i] = sine_lut[phase >> 8];
        phase = (phase + inc) & 0xFFFF;
    }
    return phase;
}

uint32_t tonegen_sawtooth(int16_t *out, uint32_t n_samples,
                          uint32_t inc_q16, uint32_t phase_q16) {
    uint32_t phase = phase_q16 & 0xFFFF;
    uint32_t inc = inc_q16 & 0xFFFF;
    for (uint32_t i = 0; i < n_samples; i++) {
        // phase 0x0000 → -32768 (min), 0x8000 → 0, 0xFFFF → +32767.
        out[i] = (int16_t)((int32_t)phase - 0x8000);
        phase = (phase + inc) & 0xFFFF;
    }
    return phase;
}

uint32_t tonegen_triangle(int16_t *out, uint32_t n_samples,
                          uint32_t inc_q16, uint32_t phase_q16) {
    uint32_t phase = phase_q16 & 0xFFFF;
    uint32_t inc = inc_q16 & 0xFFFF;
    for (uint32_t i = 0; i < n_samples; i++) {
        // Fold the phase into a triangle:
        //   0x0000 →       0
        //   0x4000 →  +32767  (peak)
        //   0x8000 →       0
        //   0xC000 →  -32768  (trough)
        // Two linear ramps of amplitude 65534 over half a cycle each.
        int32_t p = (int32_t)phase;
        int32_t tri;
        if (p < 0x8000) {
            // rising half: 0 → +32767 → 0, with peak at 0x4000
            tri = (p < 0x4000) ? (p * 2) : (0xFFFE - p * 2);
        } else {
            // falling half: 0 → -32768 → 0, with trough at 0xC000
            int32_t q = p - 0x8000;
            tri = (q < 0x4000) ? -(q * 2) : -(0xFFFE - q * 2);
        }
        if (tri > 32767) tri = 32767;
        if (tri < -32768) tri = -32768;
        out[i] = (int16_t)tri;
        phase = (phase + inc) & 0xFFFF;
    }
    return phase;
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

uint32_t tonegen_noise_pitched(int16_t *out, uint32_t n_samples,
                               uint32_t inc_q16, uint32_t phase_q16,
                               uint16_t *lfsr) {
    // Sample-and-hold LFSR with a triangular decay envelope per period:
    // every time the phase accumulator wraps (at freq_hz), we clock the
    // LFSR and latch a new amplitude.  Instead of holding it flat until
    // the next wrap — which gives pitched noise but with a weak, heavily
    // smeared fundamental — we decay each latched value linearly back to
    // zero across the hold period.  The result is a sequence of sharp
    // "pops" at freq_hz whose fundamental is clearly audible to the ear
    // while the per-pop amplitude (from the LFSR) keeps the noisy
    // character.  Low freq → fewer, slower pops = gritty growl; high
    // freq → more pops/sec = bright crackle.
    uint32_t phase = phase_q16 & 0xFFFF;
    uint32_t inc = inc_q16 & 0xFFFF;
    uint16_t state = *lfsr;
    if (state == 0) state = 0xACE1;  // LFSR must be non-zero

    int16_t held = (int16_t)((int32_t)state - 32768);

    for (uint32_t i = 0; i < n_samples; i++) {
        // Decay envelope: 0x10000 just after a tick → 1 just before the
        // next.  (held * env) >> 16 lands back in int16 range; held is
        // already signed so the envelope preserves sign through the decay.
        uint32_t env = 0x10000 - phase;
        int32_t val = ((int32_t)held * (int32_t)env) >> 16;
        out[i] = (int16_t)val;
        uint32_t next = phase + inc;
        if (next >> 16) {
            // Phase wrapped → tick the LFSR (Galois, taps 16/15/13/4).
            uint32_t bit = state & 1;
            state >>= 1;
            if (bit) state ^= 0xB400;
            held = (int16_t)((int32_t)state - 32768);
        }
        phase = next & 0xFFFF;
    }
    *lfsr = state;
    return phase;
}

// 2^(n/12) in Q16.16 for n = 0..24 semitones (0..2 octaves).
// Covers ±2 octaves of bend; beyond that we saturate.
static const uint32_t semitone_mult_q16[25] = {
     65536,  69433,  73562,  77936,  82570,  87480,  92682,  98193,
    104032, 110218, 116772, 123715, 131072, 138866, 147125, 155872,
    165140, 174960, 185364, 196386, 208064, 220436, 233544, 247431,
    262144,
};

uint32_t tonegen_cents_mult_q16(int32_t cents) {
    // Clamp to ±2 octaves (24 semitones = 2400 cents).
    if (cents > 2400) cents = 2400;
    if (cents < -2400) cents = -2400;

    // Split into whole semitones + remainder.
    int32_t semis = cents / 100;     // -24..24
    int32_t rem   = cents - semis * 100;  // -99..99
    // Normalise so rem is always 0..99 (borrow from semis if negative).
    if (rem < 0) { rem += 100; semis -= 1; }

    // Index into the positive-semitone LUT.  For negative semitones we
    // reciprocate: 2^(-n/12) = 1 / 2^(n/12), done as a Q16 divide.
    uint32_t base, next;
    if (semis >= 0) {
        base = semitone_mult_q16[semis];
        next = semitone_mult_q16[semis + 1];
    } else {
        // semis in -24..-1; mirror via division.
        uint32_t up  = semitone_mult_q16[-semis];
        uint32_t nup = semitone_mult_q16[-semis - 1];
        // base = 1 / up (Q16.16): (1 << 32) / up
        base = (uint32_t)(((uint64_t)1 << 32) / up);
        next = (uint32_t)(((uint64_t)1 << 32) / nup);
    }

    // Linear interp between base and next across the 100-cent gap.
    int32_t diff = (int32_t)next - (int32_t)base;
    return (uint32_t)((int32_t)base + diff * rem / 100);
}

void tonegen_envelope(int16_t *buf, uint32_t n_samples,
                      uint32_t pos, uint32_t total,
                      uint32_t attack, uint32_t release,
                      uint8_t velocity) {
    // Velocity gain: 0-127 mapped to 0-256 (fixed-point 8.8 style, >>7)
    // 127 → 256 (unity), 64 → ~128 (half), 0 → 0 (silent)
    uint32_t vel_gain = (velocity < 127) ? (velocity * 2) : 256;
    uint32_t release_start = (total > release) ? (total - release) : 0;

    for (uint32_t i = 0; i < n_samples; i++) {
        uint32_t abs_pos = pos + i;
        uint32_t gain = 256;  // full amplitude (8-bit fixed point)

        if (attack > 0 && abs_pos < attack) {
            // Attack ramp: linear 0 → 256
            gain = (abs_pos * 256) / attack;
        } else if (release > 0 && abs_pos >= release_start) {
            // Release ramp: linear 256 → 0
            uint32_t rel_pos = abs_pos - release_start;
            gain = ((release - rel_pos) * 256) / release;
        }

        // Combine envelope gain with velocity
        gain = (gain * vel_gain) >> 8;

        int32_t val = buf[i];
        val = (val * (int32_t)gain) >> 8;
        buf[i] = (int16_t)val;
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
