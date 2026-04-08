// tonegen.h — procedural tone generation (runs on core 1)

#ifndef AUDIOMIX_TONEGEN_H
#define AUDIOMIX_TONEGEN_H

#include <stdint.h>

// Generate square wave samples into `out`.
// Returns the new phase offset for seamless chaining.
uint32_t tonegen_square(int16_t *out, uint32_t n_samples,
                        uint32_t period, uint32_t phase);

// Generate sine wave samples using a 256-entry LUT.
uint32_t tonegen_sine(int16_t *out, uint32_t n_samples,
                      uint32_t period, uint32_t phase);

// Generate sawtooth wave samples.
uint32_t tonegen_sawtooth(int16_t *out, uint32_t n_samples,
                          uint32_t period, uint32_t phase);

// Generate noise with exponential decay.
// decay_rate controls how fast the noise fades (~4000 = sharp click).
void tonegen_noise(int16_t *out, uint32_t n_samples,
                   uint32_t decay_rate, uint32_t sample_rate);

// Apply linear fade-in and/or fade-out to a sample buffer.
void tonegen_fade(int16_t *buf, uint32_t n_samples,
                  int fade_in, int fade_out, uint32_t fade_len);

#endif // AUDIOMIX_TONEGEN_H
