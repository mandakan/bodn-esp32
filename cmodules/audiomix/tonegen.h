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
