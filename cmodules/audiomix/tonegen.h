// tonegen.h — procedural tone generation (runs on core 1)

#ifndef AUDIOMIX_TONEGEN_H
#define AUDIOMIX_TONEGEN_H

#include <stdint.h>

// Square/sine/sawtooth take a Q16 phase accumulator: 65536 = one full cycle.
// Callers compute inc_q16 = round(freq_hz * 65536 / sample_rate).  Phase is
// continuous across chunks and across frequency changes — only the rate of
// advance changes, so pitch sweeps are click-free.  Returns the new phase
// (wrapped into 0..65535).

uint32_t tonegen_square(int16_t *out, uint32_t n_samples,
                        uint32_t inc_q16, uint32_t phase_q16);

uint32_t tonegen_sine(int16_t *out, uint32_t n_samples,
                      uint32_t inc_q16, uint32_t phase_q16);

uint32_t tonegen_sawtooth(int16_t *out, uint32_t n_samples,
                          uint32_t inc_q16, uint32_t phase_q16);

uint32_t tonegen_triangle(int16_t *out, uint32_t n_samples,
                          uint32_t inc_q16, uint32_t phase_q16);

// Noise has no notion of phase — it's an exponentially-decaying LFSR burst.
// decay_rate controls how fast the noise fades (~4000 = sharp click).
void tonegen_noise(int16_t *out, uint32_t n_samples,
                   uint32_t decay_rate, uint32_t sample_rate);

// Sustained pitched noise — sample-and-hold on a 16-bit LFSR clocked at
// the given frequency (via inc_q16).  The phase accumulator ticks the
// LFSR every time it wraps; between wraps the held sample is repeated.
// Both phase and LFSR state persist across chunks for click-free output.
// *lfsr is read/written (seed with non-zero at voice start).
uint32_t tonegen_noise_pitched(int16_t *out, uint32_t n_samples,
                               uint32_t inc_q16, uint32_t phase_q16,
                               uint16_t *lfsr);

// Sample the shared sine LUT at a Q16 phase (0..65535 = one full cycle).
// Used by the mixer's modulation layer for LFOs without duplicating the LUT.
int16_t tonegen_lfo_sine(uint32_t phase_q16);

// Convert a pitch offset in cents to a frequency multiplier in Q16.16.
// Result × base_freq gives the modulated frequency.  Accurate to ~0.1%
// for |cents| ≤ 2400 via a 49-entry LUT with linear interpolation
// between 100-cent (1 semitone) steps.
uint32_t tonegen_cents_mult_q16(int32_t cents);

// Apply linear fade-in and/or fade-out to a sample buffer.
// Used for WAV buffer click suppression (SRC_RINGBUF, SRC_BUFFER).
void tonegen_fade(int16_t *buf, uint32_t n_samples,
                  int fade_in, int fade_out, uint32_t fade_len);

// Apply attack/release envelope with velocity scaling to a tone buffer.
// Used for clock-driven tone tracks (SRC_TONE with env_total_samples > 0).
//   pos:      current sample position within the overall note
//   total:    total note duration in samples
//   attack:   attack ramp length in samples (0 = instant onset)
//   release:  release ramp length in samples (0 = hard stop)
//   velocity: volume 0-127 (127 = full amplitude)
void tonegen_envelope(int16_t *buf, uint32_t n_samples,
                      uint32_t pos, uint32_t total,
                      uint32_t attack, uint32_t release,
                      uint8_t velocity);

#endif // AUDIOMIX_TONEGEN_H
