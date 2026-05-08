// mixer.c — core 1 FreeRTOS task: mix loop + I2S output
//
// The task runs a tight loop: for each active voice, read/generate
// samples into a working buffer, apply gain, mix with saturation,
// then write stereo output to I2S.  The blocking i2s_channel_write()
// naturally paces the loop to the DMA/sample rate.

#include <string.h>
#include <stdlib.h>

#include "mixer.h"
#include "ringbuf.h"
#include "tonegen.h"

#include "py/mpprint.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/idf_additions.h"
#include "driver/i2s_std.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"

static const char *TAG = "audiomix";

#define MIX_TASK_STACK  4096
#define MIX_TASK_PRIO   (configMAX_PRIORITIES - 2)

// I2S channel handle (module-level, set by mixer_init)
static i2s_chan_handle_t s_i2s_handle = NULL;

// ---------------------------------------------------------------------------
// DSP helpers
// ---------------------------------------------------------------------------

static inline int16_t saturate_add(int32_t a, int32_t b) {
    int32_t sum = a + b;
    if (sum > 32767) return 32767;
    if (sum < -32768) return -32768;
    return (int16_t)sum;
}

static void apply_gain(int16_t *buf, uint32_t n_samples, uint32_t gain) {
    for (uint32_t i = 0; i < n_samples; i++) {
        int32_t val = buf[i];
        val = (val * (int32_t)gain) >> 16;
        buf[i] = (int16_t)val;
    }
}

static void mix_add(int16_t *dst, const int16_t *src, uint32_t n_samples) {
    for (uint32_t i = 0; i < n_samples; i++) {
        dst[i] = saturate_add(dst[i], src[i]);
    }
}

static void mono_to_stereo(const int16_t *mono, int16_t *stereo,
                            uint32_t n_samples) {
    // Fill backwards to allow in-place expansion if buffers overlap
    for (int32_t i = (int32_t)n_samples - 1; i >= 0; i--) {
        stereo[i * 2]     = mono[i];
        stereo[i * 2 + 1] = mono[i];
    }
}

// Append a chunk of post-mix samples to the scope ring buffer.
static void scope_write(audiomix_state_t *state,
                         const int16_t *samples, uint32_t n) {
    uint32_t wr = state->scope_wr % AUDIOMIX_SCOPE_SAMPLES;
    uint32_t first = AUDIOMIX_SCOPE_SAMPLES - wr;
    if (first > n) first = n;
    if (samples) {
        memcpy(&state->scope_buf[wr], samples, first * sizeof(int16_t));
        if (first < n) {
            memcpy(&state->scope_buf[0], samples + first,
                   (n - first) * sizeof(int16_t));
        }
    } else {
        memset(&state->scope_buf[wr], 0, first * sizeof(int16_t));
        if (first < n) {
            memset(&state->scope_buf[0], 0,
                   (n - first) * sizeof(int16_t));
        }
    }
    state->scope_wr += n;
}

// Per-sample amplitude modulation: tremolo (amp LFO) + stutter gate.
// Applied after tone generation so it stacks on top of envelopes / fades.
static void apply_amp_modulation(int16_t *buf, uint32_t n,
                                  audiomix_voice_t *v, uint32_t sample_rate) {
    // Pre-compute per-sample phase increments in Q16.
    // inc = 65536 * rate_cHz / (sample_rate * 100)
    uint32_t amp_inc = 0, stut_inc = 0;
    if (v->mod_lfo_amp_rate_cHz) {
        amp_inc = (uint32_t)(((uint64_t)65536 * v->mod_lfo_amp_rate_cHz)
                             / ((uint64_t)sample_rate * 100));
    }
    if (v->mod_stutter_rate_cHz) {
        stut_inc = (uint32_t)(((uint64_t)65536 * v->mod_stutter_rate_cHz)
                              / ((uint64_t)sample_rate * 100));
    }
    uint32_t amp_phase = v->mod_lfo_amp_phase;
    uint32_t stut_phase = v->mod_stutter_phase;
    uint32_t amp_depth = v->mod_lfo_amp_depth_q15;  // 0..32767
    uint32_t stut_duty = v->mod_stutter_duty_q15;    // 0..32767
    // Slew-limited stutter gate: the raw 0/32767 target is low-passed so the
    // gate edges aren't sharp clicks.  Per-sample step gives a linear ramp
    // across AUDIOMIX_STUTTER_RAMP_SAMPLES samples.
    uint32_t stut_gate = v->mod_stutter_gate_q15;
    const int32_t stut_step = 32767 / AUDIOMIX_STUTTER_RAMP_SAMPLES;
    int stut_active = (stut_inc && stut_duty) ? 1 : 0;

    for (uint32_t i = 0; i < n; i++) {
        // Amp LFO: gain in Q15, centred on unity minus half depth so it wobbles
        // around a consistent perceived loudness (0 = unity, −depth = quietest).
        uint32_t gain_q15 = 32767;
        if (amp_inc && amp_depth) {
            int16_t s = tonegen_lfo_sine(amp_phase);           // ±32767
            // Map s from ±32767 to 0..depth, then subtract from unity.
            int32_t dip = ((int32_t)amp_depth * (32767 - s)) >> 16;  // 0..depth
            gain_q15 = 32767 - (uint32_t)dip;
            amp_phase += amp_inc;
        }
        // Stutter: slew-limit a binary on/off target toward the current sample.
        if (stut_active) {
            uint32_t target = ((stut_phase & 0xFFFF) < stut_duty) ? 0 : 32767;
            int32_t delta = (int32_t)target - (int32_t)stut_gate;
            if (delta >  stut_step) delta =  stut_step;
            if (delta < -stut_step) delta = -stut_step;
            stut_gate = (uint32_t)((int32_t)stut_gate + delta);
            gain_q15 = (gain_q15 * stut_gate) >> 15;
            stut_phase += stut_inc;
        } else if (stut_gate != 32767) {
            // Effect just turned off — coast the gate back up to unity.
            int32_t delta = 32767 - (int32_t)stut_gate;
            if (delta >  stut_step) delta =  stut_step;
            stut_gate = (uint32_t)((int32_t)stut_gate + delta);
            gain_q15 = (gain_q15 * stut_gate) >> 15;
        }
        int32_t val = buf[i];
        val = (val * (int32_t)gain_q15) >> 15;
        buf[i] = (int16_t)val;
    }
    v->mod_lfo_amp_phase = amp_phase;
    v->mod_stutter_phase = stut_phase;
    v->mod_stutter_gate_q15 = (uint16_t)stut_gate;
}

// Compute Q16 phase increment from a frequency in Hz.  Rounded to nearest.
static inline uint32_t phase_inc_q16(uint32_t freq_hz, uint32_t sample_rate) {
    if (freq_hz == 0 || sample_rate == 0) return 0;
    return (uint32_t)(((uint64_t)freq_hz * 65536 + sample_rate / 2)
                      / sample_rate);
}

// Generate one chunk of a single waveform into `out` and return the new Q16
// phase.  Noise (decaying) has no phase so we pass through unchanged.
// `lfsr` may be NULL for callers that never render AUDIOMIX_WAVE_NOISE_PITCHED.
static uint32_t render_wave_chunk(int16_t *out, uint32_t n, uint8_t wave,
                                   uint32_t inc_q16, uint32_t phase_q16,
                                   uint32_t freq_hz, uint32_t sample_rate,
                                   uint16_t *lfsr) {
    switch (wave) {
    case AUDIOMIX_WAVE_SQUARE:
        return tonegen_square(out, n, inc_q16, phase_q16);
    case AUDIOMIX_WAVE_SINE:
        return tonegen_sine(out, n, inc_q16, phase_q16);
    case AUDIOMIX_WAVE_SAWTOOTH:
        return tonegen_sawtooth(out, n, inc_q16, phase_q16);
    case AUDIOMIX_WAVE_NOISE:
        tonegen_noise(out, n, freq_hz, sample_rate);
        return phase_q16;
    case AUDIOMIX_WAVE_TRIANGLE:
        return tonegen_triangle(out, n, inc_q16, phase_q16);
    case AUDIOMIX_WAVE_NOISE_PITCHED: {
        uint16_t local = lfsr ? *lfsr : 0xACE1;
        uint32_t new_phase = tonegen_noise_pitched(out, n, inc_q16, phase_q16,
                                                    &local);
        if (lfsr) *lfsr = local;
        return new_phase;
    }
    default:
        memset(out, 0, n * sizeof(int16_t));
        return phase_q16;
    }
}

// ---------------------------------------------------------------------------
// Per-voice sample generation
// ---------------------------------------------------------------------------

// Read samples from a voice source into voice_buf (int16_t).
// Returns number of samples produced (0 = voice finished or starved).
static uint32_t voice_read(audiomix_state_t *state, audiomix_voice_t *v,
                           int16_t *voice_buf, uint32_t max_samples) {
    uint32_t n = 0;
    uint32_t max_bytes = max_samples * 2;

    switch (v->source_type) {
    case SRC_RINGBUF: {
        n = ringbuf_read(&v->ringbuf, (uint8_t *)voice_buf, max_bytes);
        n /= 2;  // bytes → samples
        if (n == 0) {
            if (v->eof) {
                if (v->loop) {
                    // Signal Python to refill: clear eof, reset ringbuf
                    v->eof = 0;
                    ringbuf_reset(&v->ringbuf);
                } else {
                    v->source_type = SRC_NONE;
                }
            } else {
                // Underrun — Python hasn't fed data yet
                state->underruns++;
            }
        }
        break;
    }

    case SRC_BUFFER: {
        if (v->buf_ptr == NULL || v->buf_len == 0) {
            v->source_type = SRC_NONE;
            break;
        }
        uint32_t remaining = v->buf_len - v->buf_pos;
        uint32_t to_copy = (remaining < max_bytes) ? remaining : max_bytes;
        to_copy = (to_copy / 2) * 2;  // align to sample boundary
        if (to_copy > 0) {
            memcpy(voice_buf, v->buf_ptr + v->buf_pos, to_copy);
            v->buf_pos += to_copy;
            n = to_copy / 2;
        }
        if (v->buf_pos >= v->buf_len) {
            if (v->loop) {
                v->buf_pos = 0;
            } else {
                v->source_type = SRC_NONE;
            }
        }
        break;
    }

    case SRC_TONE: {
        if (v->tone_freq == 0) {
            v->source_type = SRC_NONE;
            break;
        }
        if (!v->tone_sustain && v->tone_samples_left == 0) {
            v->source_type = SRC_NONE;
            break;
        }

        n = v->tone_sustain
            ? max_samples
            : ((v->tone_samples_left < max_samples)
               ? v->tone_samples_left : max_samples);

        // --- Pitch modulation ---------------------------------------------
        // Advance bend accumulator by this chunk's duration.
        if (v->mod_bend_cents_per_s) {
            int32_t delta = (v->mod_bend_cents_per_s * (int32_t)n)
                            / (int32_t)state->sample_rate;
            v->mod_bend_current_cents += delta;
            int32_t lim = v->mod_bend_limit_cents;
            if (lim > 0) {
                if (v->mod_bend_current_cents >  lim) v->mod_bend_current_cents =  lim;
                if (v->mod_bend_current_cents < -lim) v->mod_bend_current_cents = -lim;
            }
        }

        // Combine bend + pitch LFO (sampled at chunk midpoint — 16 ms steps
        // at 16 kHz are well below the ~5 Hz LFO rate, so quantisation is
        // imperceptible even with square waves).
        int32_t pitch_cents = v->mod_bend_current_cents;
        if (v->mod_lfo_pitch_rate_cHz && v->mod_lfo_pitch_depth_cents) {
            uint32_t inc = (uint32_t)(((uint64_t)65536
                * v->mod_lfo_pitch_rate_cHz)
                / ((uint64_t)state->sample_rate * 100));
            uint32_t mid = v->mod_lfo_pitch_phase + inc * (n / 2);
            int16_t s = tonegen_lfo_sine(mid);
            pitch_cents += (int32_t)v->mod_lfo_pitch_depth_cents * s / 32767;
            v->mod_lfo_pitch_phase += inc * n;
        }

        uint32_t eff_freq = v->tone_freq;
        if (pitch_cents) {
            uint32_t mult = tonegen_cents_mult_q16(pitch_cents);
            eff_freq = (uint32_t)(((uint64_t)v->tone_freq * mult) >> 16);
            if (eff_freq == 0) eff_freq = 1;
        }
        uint32_t inc = phase_inc_q16(eff_freq, state->sample_rate);

        // Waveform crossfade: if Python requested a wave change, render the
        // new wave for the whole chunk, then blend the old wave over the first
        // xfade_left samples.  Phase is shared so both oscillators step in
        // lockstep — no double-pitch artefacts — and samples past the fade
        // continue with the new wave cleanly.
        if (v->tone_wave_xfade_left > 0
                && v->tone_wave_pending != v->tone_wave) {
            uint32_t xfade_n = v->tone_wave_xfade_left;
            if (xfade_n > n) xfade_n = n;

            uint32_t new_phase = render_wave_chunk(
                voice_buf, n, v->tone_wave_pending, inc, v->tone_phase,
                eff_freq, state->sample_rate, &v->tone_lfsr);

            // Scratch path uses a local LFSR copy so the fade-out tail doesn't
            // double-advance the voice's persistent noise state.
            uint16_t scratch_lfsr = v->tone_lfsr;
            int16_t scratch[AUDIOMIX_WAVE_XFADE_SAMPLES];
            render_wave_chunk(scratch, xfade_n, v->tone_wave,
                              inc, v->tone_phase,
                              eff_freq, state->sample_rate, &scratch_lfsr);

            const uint32_t total = AUDIOMIX_WAVE_XFADE_SAMPLES;
            uint32_t done = total - v->tone_wave_xfade_left;
            for (uint32_t i = 0; i < xfade_n; i++) {
                uint32_t t = ((done + i) << 15) / (total > 0 ? total : 1);
                if (t > 32767) t = 32767;
                int32_t a = (int32_t)scratch[i]   * (int32_t)(32767 - t);
                int32_t b = (int32_t)voice_buf[i] * (int32_t)t;
                voice_buf[i] = (int16_t)((a + b) >> 15);
            }

            v->tone_phase = new_phase;
            v->tone_wave_xfade_left -= xfade_n;
            if (v->tone_wave_xfade_left == 0) {
                v->tone_wave = v->tone_wave_pending;
            }
        } else {
            v->tone_phase = render_wave_chunk(
                voice_buf, n, v->tone_wave, inc, v->tone_phase,
                eff_freq, state->sample_rate, &v->tone_lfsr);
        }

        // Apply envelope or legacy fade
        if (v->env_total_samples > 0) {
            // Clock-driven envelope (attack/release + velocity)
            tonegen_envelope(voice_buf, n, v->env_pos, v->env_total_samples,
                            v->env_attack_samples, v->env_release_samples,
                            v->env_velocity);
            v->env_pos += n;
        } else if (!v->tone_sustain) {
            // Legacy fade for Python-triggered one-shot tones
            int is_last = (v->tone_samples_left <= n);
            if (v->fade_in || is_last) {
                tonegen_fade(voice_buf, n, v->fade_in, is_last,
                            AUDIOMIX_FADE_SAMPLES);
                v->fade_in = 0;
            }
        } else if (v->fade_in) {
            // Sustained voice: fade in the very first chunk to avoid a click.
            tonegen_fade(voice_buf, n, 1, 0, AUDIOMIX_FADE_SAMPLES);
            v->fade_in = 0;
        }

        // --- Amplitude modulation -----------------------------------------
        if (v->mod_lfo_amp_rate_cHz || v->mod_stutter_rate_cHz) {
            apply_amp_modulation(voice_buf, n, v, state->sample_rate);
        }

        if (!v->tone_sustain) {
            v->tone_samples_left -= n;
        }
        break;
    }

    case SRC_SEQUENCE: {
        // Step through the sequence, generating one tone at a time
        while (n < max_samples && v->seq_current < v->seq_n_steps) {
            // Decode current step if starting fresh
            if (v->seq_samples_left == 0) {
                uint32_t off = v->seq_current * AUDIOMIX_SEQ_STEP_SIZE;
                uint16_t freq = v->seq_buf[off] | (v->seq_buf[off + 1] << 8);
                uint16_t dur  = v->seq_buf[off + 2] | (v->seq_buf[off + 3] << 8);
                v->tone_wave  = v->seq_buf[off + 4];
                v->tone_freq  = freq;
                v->seq_samples_left = (state->sample_rate * dur) / 1000;
                v->seq_phase  = 0;
            }

            uint32_t want = max_samples - n;
            if (want > v->seq_samples_left) want = v->seq_samples_left;

            if (v->tone_freq > 0) {
                uint32_t inc = phase_inc_q16(v->tone_freq, state->sample_rate);
                v->seq_phase = render_wave_chunk(
                    voice_buf + n, want, v->tone_wave, inc, v->seq_phase,
                    v->tone_freq, state->sample_rate, &v->tone_lfsr);
            } else {
                // freq == 0 means silence (rest)
                memset(voice_buf + n, 0, want * 2);
            }

            n += want;
            v->seq_samples_left -= want;
            if (v->seq_samples_left == 0) {
                v->seq_current++;
            }
        }
        if (v->seq_current >= v->seq_n_steps) {
            v->source_type = SRC_NONE;
        }
        break;
    }

    default:
        break;
    }

    return n;
}

// ---------------------------------------------------------------------------
// Mix task (pinned to core 1)
// ---------------------------------------------------------------------------

static void mix_task(void *arg) {
    audiomix_state_t *state = (audiomix_state_t *)arg;

    // Working buffers (on stack — within 4KB budget)
    int16_t mix_buf[AUDIOMIX_MONO_BUF_SIZE / 2];     // 256 samples
    int16_t voice_buf[AUDIOMIX_MONO_BUF_SIZE / 2];   // 256 samples
    int16_t stereo_buf[AUDIOMIX_MONO_BUF_SIZE];       // 512 samples (256 stereo frames)
    const uint32_t max_samples = AUDIOMIX_MONO_BUF_SIZE / 2;

    mp_printf(&mp_plat_print, "audiomix: mix task running on core %d\n",
              xPortGetCoreID());

    while (state->running) {
        int64_t t0 = esp_timer_get_time();

        // Handle stop requests
        bool has_active = false;
        uint32_t n_active = 0;

        for (int i = 0; i < AUDIOMIX_NUM_VOICES; i++) {
            audiomix_voice_t *v = &state->voices[i];
            if (v->stop_req) {
                v->stop_req = 0;
                if (v->source_type != SRC_NONE) {
                    v->fade_out = 1;  // graceful fade-out next chunk
                } else {
                    ringbuf_reset(&v->ringbuf);
                }
            }
            if (v->source_type != SRC_NONE) {
                has_active = true;
                n_active++;
            }
        }

        // --- Step sequencer clock ---
        // Advance by one chunk (256 mono samples = 16ms at 16kHz).
        // The clock must advance at a consistent rate tied to the DMA output.
        // We always output max_samples worth of audio per cycle (silence or mixed).
        seq_clock_t *clk = &state->clock;
        if (clk->playing && clk->samples_per_step > 0) {
            clk->sample_count += max_samples;
            clk->total_samples += max_samples;

            while (clk->sample_count >= clk->samples_per_step) {
                clk->sample_count -= clk->samples_per_step;
                uint8_t next = (clk->current_step + 1) % clk->n_steps;
                clk->current_step = next;

                // Trigger voices for this step
                seq_step_t *st = &clk->steps[next];

                // Percussion tracks
                uint32_t threshold = (state->sample_rate * SEQ_ANTI_REPEAT_MS) / 1000;
                for (int t = 0; t < SEQ_MAX_PERC_TRACKS; t++) {
                    if (!(st->perc_mask & (1 << t))) continue;
                    int vi = clk->perc_voice[t];
                    if (vi >= AUDIOMIX_NUM_VOICES) continue;
                    if (state->voices[vi].writing) continue;
                    // Anti-double: check per-track preview marker
                    uint32_t since = clk->total_samples - clk->manual_trigger_sample[t];
                    if (since < threshold) continue;

                    seq_perc_track_t *pt = &clk->perc_tracks[t];
                    if (pt->buf_ptr && pt->buf_len > 0) {
                        audiomix_voice_t *v = &state->voices[vi];
                        v->source_type = SRC_NONE;
                        v->buf_ptr = pt->buf_ptr;
                        v->buf_len = pt->buf_len;
                        v->buf_pos = 0;
                        v->loop = 0;
                        v->fade_in = 0;
                        v->fade_out = 0;
                        v->stop_req = 0;
                        v->source_type = SRC_BUFFER;
                    }
                }

                // Melody (DEPRECATED — kept for backward compat)
                if (st->melody_freq > 0) {
                    int vi = clk->melody_voice;
                    if (vi < AUDIOMIX_NUM_VOICES && !state->voices[vi].writing) {
                        uint32_t since = clk->total_samples - clk->manual_trigger_sample[SEQ_MAX_PERC_TRACKS];
                        if (since >= threshold) {
                            audiomix_voice_t *v = &state->voices[vi];
                            v->source_type = SRC_NONE;
                            uint32_t dur_samples = (state->sample_rate * clk->melody_duration_ms) / 1000;
                            v->tone_freq = st->melody_freq;
                            v->tone_samples_left = dur_samples;
                            v->tone_phase = 0;
                            v->tone_lfsr = 0xACE1;
                            v->tone_wave = clk->melody_wave;
                            v->tone_wave_pending = clk->melody_wave;
                            v->tone_wave_xfade_left = 0;
                            v->loop = 0;
                            v->fade_in = 1;
                            v->fade_out = 0;
                            v->stop_req = 0;
                            v->env_total_samples = 0;  // legacy path
                            v->mod_stutter_gate_q15 = 32767;
                            v->source_type = SRC_TONE;
                        }
                    }
                }

                // Tone tracks (sample-accurate synth notes)
                for (int tt = 0; tt < SEQ_MAX_TONE_TRACKS; tt++) {
                    seq_tone_track_t *trk = &clk->tone_tracks[tt];
                    if (!(trk->step_mask & (1 << next))) continue;

                    int vi = trk->voice_idx;
                    if (vi >= AUDIOMIX_NUM_VOICES) continue;
                    if (state->voices[vi].writing) continue;

                    // Anti-double-trigger
                    uint32_t since = clk->total_samples
                        - clk->manual_trigger_sample[SEQ_MAX_PERC_TRACKS + tt];
                    if (since < threshold) continue;

                    seq_tone_step_t *ts = &trk->steps[next];
                    if (ts->freq == 0) continue;  // rest step

                    audiomix_voice_t *v = &state->voices[vi];
                    v->source_type = SRC_NONE;

                    uint32_t dur_samples = (state->sample_rate * ts->duration_ms) / 1000;
                    v->tone_freq = ts->freq;
                    v->tone_samples_left = dur_samples;
                    v->tone_phase = 0;
                    v->tone_lfsr = 0xACE1;
                    v->tone_wave = ts->wave;
                    v->tone_wave_pending = ts->wave;
                    v->tone_wave_xfade_left = 0;
                    v->loop = 0;
                    v->fade_in = 0;   // envelope handles attack
                    v->fade_out = 0;
                    v->stop_req = 0;

                    // Envelope parameters
                    v->env_attack_samples = (state->sample_rate * ts->attack_ms) / 1000;
                    v->env_release_samples = (state->sample_rate * ts->release_ms) / 1000;
                    v->env_total_samples = dur_samples;
                    v->env_pos = 0;
                    v->env_velocity = ts->velocity;
                    v->mod_stutter_gate_q15 = 32767;

                    v->source_type = SRC_TONE;
                }
            }
            // Clock is active — always process even if no voices were triggered
            has_active = true;
        }

        if (!has_active) {
            // No active voices and no clock — write full silence chunk
            // (must match max_samples so clock timing stays consistent)
            memset(stereo_buf, 0, max_samples * 4);
            scope_write(state, NULL, max_samples);
            size_t written;
            i2s_channel_write(s_i2s_handle, stereo_buf, max_samples * 4,
                             &written, portMAX_DELAY);
            continue;
        }

        // Zero mix buffer
        memset(mix_buf, 0, sizeof(mix_buf));
        uint32_t max_n = 0;

        // Mix all active voices
        for (int i = 0; i < AUDIOMIX_NUM_VOICES; i++) {
            audiomix_voice_t *v = &state->voices[i];
            if (v->source_type == SRC_NONE || v->writing) continue;

            uint32_t n;
            if (v->xfade_samples_left > 0 && v->pending_source == SRC_BUFFER
                    && v->source_type == SRC_BUFFER) {
                // BUFFER → BUFFER equal-power crossfade. Read xfade_n samples
                // from the active source and the pending source in parallel,
                // mix them with cos²/sin² weights so total power stays flat
                // through the transition. When xfade_samples_left hits zero,
                // promote pending → active in place.
                uint32_t xfade_n = v->xfade_samples_left;
                if (xfade_n > max_samples) xfade_n = max_samples;

                int16_t scratch_b[AUDIOMIX_XFADE_SAMPLES];
                uint32_t na = voice_read(state, v, voice_buf, xfade_n);

                uint32_t nb = 0;
                if (v->pending_buf_ptr != NULL && v->pending_buf_len > 0) {
                    uint32_t max_bytes = xfade_n * 2;
                    uint32_t remaining = v->pending_buf_len - v->pending_buf_pos;
                    uint32_t to_copy = (remaining < max_bytes) ? remaining : max_bytes;
                    to_copy = (to_copy / 2) * 2;
                    if (to_copy > 0) {
                        memcpy(scratch_b, v->pending_buf_ptr + v->pending_buf_pos, to_copy);
                        v->pending_buf_pos += to_copy;
                        nb = to_copy / 2;
                    }
                    if (v->pending_buf_pos >= v->pending_buf_len && v->pending_loop) {
                        v->pending_buf_pos = 0;
                    }
                }

                uint32_t produced = (na > nb) ? na : nb;
                uint32_t total = v->xfade_samples_total;
                if (total == 0) total = 1;
                uint32_t done = total - v->xfade_samples_left;
                for (uint32_t i = 0; i < produced; i++) {
                    // Quarter-cycle phase: t_phase = (done+i) / total * 16384
                    // (Q16 phase units; full cycle = 65536, quarter = 16384).
                    uint32_t t_phase = ((done + i) * 16384u) / total;
                    if (t_phase > 16384u) t_phase = 16384u;
                    int16_t a = (i < na) ? voice_buf[i] : 0;
                    int16_t b = (i < nb) ? scratch_b[i] : 0;
                    int16_t wb = tonegen_lfo_sine(t_phase);             // sin(t·π/2)
                    int16_t wa = tonegen_lfo_sine(t_phase + 16384u);    // cos(t·π/2)
                    int32_t mix = ((int32_t)a * wa + (int32_t)b * wb) >> 15;
                    // Equal-power weights can sum to ~1.414× when sources are
                    // correlated (e.g. same loop crossfading to itself).
                    // Saturate to int16 to avoid wraparound on the cast.
                    if (mix > 32767) mix = 32767;
                    else if (mix < -32768) mix = -32768;
                    voice_buf[i] = (int16_t)mix;
                }
                n = produced;
                v->xfade_samples_left -= produced;

                if (v->xfade_samples_left == 0) {
                    // Promote pending to active. The new buf_pos continues from
                    // where the crossfade left it so the new source is sample-
                    // accurate (no skip when the splice ends).
                    v->buf_ptr = v->pending_buf_ptr;
                    v->buf_len = v->pending_buf_len;
                    v->buf_pos = v->pending_buf_pos;
                    v->loop = v->pending_loop;
                    v->fade_in = 0;        // already at full amplitude
                    v->fade_out = 0;
                    state->seq_counter++;
                    v->start_seq = state->seq_counter;
                    // source_type stays SRC_BUFFER throughout

                    // If Python queued another retarget while this crossfade
                    // was in flight, activate it now as the new pending and
                    // start a fresh crossfade. Chains cleanly through any
                    // number of rapid zone changes without ever clicking.
                    if (v->next_pending_set) {
                        v->pending_buf_ptr = v->next_pending_buf_ptr;
                        v->pending_buf_len = v->next_pending_buf_len;
                        v->pending_buf_pos = 0;
                        v->pending_loop = v->next_pending_loop;
                        v->next_pending_set = 0;
                        v->xfade_samples_total = AUDIOMIX_XFADE_SAMPLES;
                        v->xfade_samples_left = AUDIOMIX_XFADE_SAMPLES;
                        // pending_source stays SRC_BUFFER
                    } else {
                        v->pending_source = SRC_NONE;
                    }
                }
            } else if (v->fade_out) {
                // Read just enough for a fade-out ramp, then kill voice or
                // activate the pending source if one was queued by Python
                // via voice_play_buffer/voice_tone(..., fade=True).
                n = voice_read(state, v, voice_buf, AUDIOMIX_FADE_SAMPLES);
                if (n > 0) {
                    tonegen_fade(voice_buf, n, 0, 1, AUDIOMIX_FADE_SAMPLES);
                }
                v->fade_out = 0;
                if (v->pending_source == SRC_BUFFER) {
                    v->buf_ptr = v->pending_buf_ptr;
                    v->buf_len = v->pending_buf_len;
                    v->buf_pos = v->pending_buf_pos;
                    v->loop = v->pending_loop;
                    v->fade_in = 1;
                    state->seq_counter++;
                    v->start_seq = state->seq_counter;
                    v->pending_source = SRC_NONE;
                    v->source_type = SRC_BUFFER;
                } else if (v->pending_source == SRC_TONE) {
                    v->tone_freq = v->pending_tone_freq;
                    v->tone_samples_left = v->pending_tone_samples;
                    v->tone_phase = 0;
                    v->tone_lfsr = 0xACE1;
                    v->tone_wave = v->pending_tone_wave;
                    v->tone_wave_pending = v->pending_tone_wave;
                    v->tone_wave_xfade_left = 0;
                    v->tone_sustain = 0;
                    v->env_total_samples = 0;
                    v->loop = 0;
                    v->fade_in = 1;
                    // Reset modulation so a fresh tone starts clean.
                    v->mod_lfo_pitch_rate_cHz = 0;
                    v->mod_lfo_pitch_depth_cents = 0;
                    v->mod_lfo_pitch_phase = 0;
                    v->mod_lfo_amp_rate_cHz = 0;
                    v->mod_lfo_amp_depth_q15 = 0;
                    v->mod_lfo_amp_phase = 0;
                    v->mod_bend_cents_per_s = 0;
                    v->mod_bend_current_cents = 0;
                    v->mod_bend_limit_cents = 0;
                    v->mod_stutter_rate_cHz = 0;
                    v->mod_stutter_duty_q15 = 0;
                    v->mod_stutter_phase = 0;
                    v->mod_stutter_gate_q15 = 32767;
                    state->seq_counter++;
                    v->start_seq = state->seq_counter;
                    v->pending_source = SRC_NONE;
                    v->source_type = SRC_TONE;
                } else {
                    v->source_type = SRC_NONE;
                    ringbuf_reset(&v->ringbuf);
                }
            } else {
                n = voice_read(state, v, voice_buf, max_samples);
            }
            if (n == 0) continue;

            // Per-voice gain
            apply_gain(voice_buf, n, v->gain);
            mix_add(mix_buf, voice_buf, n);

            if (n > max_n) max_n = n;
        }

        if (max_n == 0) {
            // No voice produced samples — output full silence chunk
            memset(stereo_buf, 0, max_samples * 4);
            scope_write(state, NULL, max_samples);
            size_t written;
            i2s_channel_write(s_i2s_handle, stereo_buf, max_samples * 4,
                             &written, portMAX_DELAY);
            continue;
        }

        // Master volume
        if (state->master_volume < 100) {
            apply_gain(mix_buf, max_n, state->vol_mult);
        }

        // Scope tap — post-master-volume mono samples for visualisation.
        scope_write(state, mix_buf, max_n);

        // Mono → stereo
        mono_to_stereo(mix_buf, stereo_buf, max_n);

        // Measure mix computation time (excludes DMA wait)
        uint32_t mix_elapsed = (uint32_t)(esp_timer_get_time() - t0);

        // Write to I2S (blocking — paces loop to DMA timing)
        int64_t t_dma = esp_timer_get_time();
        size_t written;
        i2s_channel_write(s_i2s_handle, stereo_buf, max_n * 4,
                         &written, portMAX_DELAY);
        state->dma_wait_us = (uint32_t)(esp_timer_get_time() - t_dma);

        // Update diagnostics (mix time only, not DMA wait)
        state->mix_calls++;
        state->mix_us_last = mix_elapsed;
        if (mix_elapsed > state->mix_us_max) state->mix_us_max = mix_elapsed;
        state->mix_us_sum += mix_elapsed;
        state->mix_avg_count++;
        state->active_voices = n_active;

        // Update stack high water mark periodically
        if ((state->mix_calls & 0xFF) == 0) {
            state->task_stack_hwm = uxTaskGetStackHighWaterMark(NULL) * 4;
        }
    }

    mp_printf(&mp_plat_print, "audiomix: mix task stopped\n");
    vTaskDelete(NULL);
}

// ---------------------------------------------------------------------------
// Init / deinit
// ---------------------------------------------------------------------------

static TaskHandle_t s_mix_task = NULL;

const char *mixer_init(const mixer_config_t *cfg, audiomix_state_t **state_out) {
    *state_out = NULL;

    // Allocate state in PSRAM
    audiomix_state_t *state = heap_caps_calloc(1, sizeof(audiomix_state_t),
                                                MALLOC_CAP_SPIRAM);
    if (state == NULL) {
        return "PSRAM alloc failed";
    }

    state->sample_rate = cfg->rate;
    state->master_volume = 10;  // match Python default
    state->vol_mult = 10 * 655;
    state->running = 1;

    // Initialise step clock defaults
    state->clock.playing = 0;
    state->clock.n_steps = 8;
    state->clock.melody_duration_ms = 150;
    state->clock.melody_wave = AUDIOMIX_WAVE_SINE;
    // Default voice mapping: perc tracks → voices 0-4, melody → voice 5
    for (int i = 0; i < SEQ_MAX_PERC_TRACKS; i++) {
        state->clock.perc_voice[i] = i;
    }
    state->clock.melody_voice = 5;

    // Tone track defaults: all disabled (voice_idx=255, step_mask=0)
    for (int i = 0; i < SEQ_MAX_TONE_TRACKS; i++) {
        state->clock.tone_tracks[i].voice_idx = 255;
        state->clock.tone_tracks[i].step_mask = 0;
    }

    // Initialise per-voice state
    for (int i = 0; i < AUDIOMIX_NUM_VOICES; i++) {
        audiomix_voice_t *v = &state->voices[i];
        v->source_type = SRC_NONE;
        v->gain = AUDIOMIX_GAIN_DEFAULT;
        v->mod_stutter_gate_q15 = 32767;
        ringbuf_init(&v->ringbuf, AUDIOMIX_RINGBUF_SIZE);
    }

    // Configure I2S via ESP-IDF new driver
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(
        I2S_NUM_0, I2S_ROLE_MASTER);
    // DMA config: 6 descriptors × 256 frames = 1536 frames total
    // At 16kHz stereo 16-bit: 1536 frames × 4 bytes = 6144 bytes ≈ 96ms buffer
    // Each descriptor holds 256 frames = 16ms — matches our mix chunk size.
    //
    // History: started at 8 (~128ms), dropped to 3 (~48ms) for Tone Lab
    // input-to-tone responsiveness, then bumped back to 6 (~96ms) after
    // crackling appeared in Spaceship and Mystery — those modes stream
    // looped WAVs (drone, alarm, narration) concurrently with SD reads
    // and framebuffer DMA, and 48ms wasn't enough slack to ride out the
    // contention. 96ms still feels snappy for Tone Lab's musical play
    // (well under the ~100ms perceptual threshold) while restoring
    // ~50% more underrun headroom.
    chan_cfg.dma_desc_num = 6;
    chan_cfg.dma_frame_num = 256;

    esp_err_t err = i2s_new_channel(&chan_cfg, &s_i2s_handle, NULL);
    if (err != ESP_OK) {
        heap_caps_free(state);
        return "i2s_new_channel failed (I2S_NUM_0 busy?)";
    }

    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(cfg->rate),
        .slot_cfg = I2S_STD_MSB_SLOT_DEFAULT_CONFIG(
            I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {
            .mclk = I2S_GPIO_UNUSED,
            .bclk = (gpio_num_t)cfg->pin_bck,
            .ws   = (gpio_num_t)cfg->pin_ws,
            .dout = (gpio_num_t)cfg->pin_din,
            .din  = I2S_GPIO_UNUSED,
            .invert_flags = { false, false, false },
        },
    };

    err = i2s_channel_init_std_mode(s_i2s_handle, &std_cfg);
    if (err != ESP_OK) {
        i2s_del_channel(s_i2s_handle);
        s_i2s_handle = NULL;
        heap_caps_free(state);
        return "i2s_channel_init_std_mode failed (bad pins?)";
    }

    err = i2s_channel_enable(s_i2s_handle);
    if (err != ESP_OK) {
        i2s_del_channel(s_i2s_handle);
        s_i2s_handle = NULL;
        heap_caps_free(state);
        return "i2s_channel_enable failed";
    }

    // Enable amplifier
    gpio_reset_pin((gpio_num_t)cfg->pin_amp);
    gpio_set_direction((gpio_num_t)cfg->pin_amp, GPIO_MODE_OUTPUT);
    gpio_set_level((gpio_num_t)cfg->pin_amp, 1);

    // Start mix task on core 0.
    // MicroPython runs on core 1 (MP_TASK_COREID).  Core 0 runs ESP-IDF
    // system tasks (WiFi, timers) which are lightweight and cooperative,
    // so the mixer gets reliable scheduling without competing with the VM.
    BaseType_t ret = xTaskCreatePinnedToCore(
        mix_task, "audiomix", MIX_TASK_STACK,
        state, MIX_TASK_PRIO, &s_mix_task, 0);
    if (ret != pdPASS) {
        i2s_channel_disable(s_i2s_handle);
        i2s_del_channel(s_i2s_handle);
        s_i2s_handle = NULL;
        for (int i = 0; i < AUDIOMIX_NUM_VOICES; i++) {
            ringbuf_deinit(&state->voices[i].ringbuf);
        }
        heap_caps_free(state);
        return "xTaskCreatePinnedToCore failed (no memory?)";
    }

    *state_out = state;
    return NULL;  // success
}

void mixer_deinit(audiomix_state_t *state) {
    if (state == NULL) return;

    // Signal task to stop and wait
    state->running = 0;
    if (s_mix_task) {
        // Give the task time to exit its loop
        vTaskDelay(pdMS_TO_TICKS(100));
        s_mix_task = NULL;
    }

    // Disable amplifier (we don't track the pin, so skip for now)

    // Release I2S
    if (s_i2s_handle) {
        i2s_channel_disable(s_i2s_handle);
        i2s_del_channel(s_i2s_handle);
        s_i2s_handle = NULL;
    }

    // Free ring buffers
    for (int i = 0; i < AUDIOMIX_NUM_VOICES; i++) {
        ringbuf_deinit(&state->voices[i].ringbuf);
    }

    heap_caps_free(state);
    ESP_LOGI(TAG, "deinitialised");
}
