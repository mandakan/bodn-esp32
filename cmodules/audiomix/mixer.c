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
        if (v->tone_samples_left == 0) {
            v->source_type = SRC_NONE;
            break;
        }
        n = (v->tone_samples_left < max_samples)
            ? v->tone_samples_left : max_samples;
        uint32_t period = state->sample_rate / v->tone_freq;
        if (period < 1) period = 1;

        switch (v->tone_wave) {
        case AUDIOMIX_WAVE_SQUARE:
            v->tone_phase = tonegen_square(voice_buf, n, period, v->tone_phase);
            break;
        case AUDIOMIX_WAVE_SINE:
            v->tone_phase = tonegen_sine(voice_buf, n, period, v->tone_phase);
            break;
        case AUDIOMIX_WAVE_SAWTOOTH:
            v->tone_phase = tonegen_sawtooth(voice_buf, n, period, v->tone_phase);
            break;
        case AUDIOMIX_WAVE_NOISE:
            tonegen_noise(voice_buf, n, v->tone_freq, state->sample_rate);
            break;
        default:
            memset(voice_buf, 0, n * 2);
            break;
        }

        // Fade in/out at start/end of tone
        int is_last = (v->tone_samples_left <= n);
        if (v->fade_in || is_last) {
            tonegen_fade(voice_buf, n, v->fade_in, is_last,
                        AUDIOMIX_FADE_SAMPLES);
            v->fade_in = 0;
        }

        v->tone_samples_left -= n;
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
                uint32_t period = state->sample_rate / v->tone_freq;
                if (period < 1) period = 1;
                switch (v->tone_wave) {
                case AUDIOMIX_WAVE_SQUARE:
                    v->seq_phase = tonegen_square(voice_buf + n, want,
                                                   period, v->seq_phase);
                    break;
                case AUDIOMIX_WAVE_SINE:
                    v->seq_phase = tonegen_sine(voice_buf + n, want,
                                                 period, v->seq_phase);
                    break;
                case AUDIOMIX_WAVE_SAWTOOTH:
                    v->seq_phase = tonegen_sawtooth(voice_buf + n, want,
                                                     period, v->seq_phase);
                    break;
                default:
                    memset(voice_buf + n, 0, want * 2);
                    break;
                }
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
                v->source_type = SRC_NONE;
                v->stop_req = 0;
                ringbuf_reset(&v->ringbuf);
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
                        v->stop_req = 0;
                        v->source_type = SRC_BUFFER;
                    }
                }

                // Melody
                if (st->melody_freq > 0) {
                    int vi = clk->melody_voice;
                    if (vi < AUDIOMIX_NUM_VOICES && !state->voices[vi].writing) {
                        // Anti-double: check melody preview marker (index 5)
                        uint32_t since = clk->total_samples - clk->manual_trigger_sample[SEQ_MAX_PERC_TRACKS];
                        if (since >= threshold) {
                            audiomix_voice_t *v = &state->voices[vi];
                            v->source_type = SRC_NONE;
                            uint32_t dur_samples = (state->sample_rate * clk->melody_duration_ms) / 1000;
                            v->tone_freq = st->melody_freq;
                            v->tone_samples_left = dur_samples;
                            v->tone_phase = 0;
                            v->tone_wave = clk->melody_wave;
                            v->loop = 0;
                            v->fade_in = 1;
                            v->stop_req = 0;
                            v->source_type = SRC_TONE;
                        }
                    }
                }
            }
            // Clock is active — always process even if no voices were triggered
            has_active = true;
        }

        if (!has_active) {
            // No active voices and no clock — write full silence chunk
            // (must match max_samples so clock timing stays consistent)
            memset(stereo_buf, 0, max_samples * 4);
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
            if (v->source_type == SRC_NONE) continue;

            uint32_t n = voice_read(state, v, voice_buf, max_samples);
            if (n == 0) continue;

            // Per-voice gain
            apply_gain(voice_buf, n, v->gain);
            mix_add(mix_buf, voice_buf, n);

            if (n > max_n) max_n = n;
        }

        if (max_n == 0) {
            // No voice produced samples — output full silence chunk
            memset(stereo_buf, 0, max_samples * 4);
            size_t written;
            i2s_channel_write(s_i2s_handle, stereo_buf, max_samples * 4,
                             &written, portMAX_DELAY);
            continue;
        }

        // Master volume
        if (state->master_volume < 100) {
            apply_gain(mix_buf, max_n, state->vol_mult);
        }

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

    // Initialise per-voice state
    for (int i = 0; i < AUDIOMIX_NUM_VOICES; i++) {
        audiomix_voice_t *v = &state->voices[i];
        v->source_type = SRC_NONE;
        v->gain = AUDIOMIX_GAIN_DEFAULT;
        ringbuf_init(&v->ringbuf, AUDIOMIX_RINGBUF_SIZE);
    }

    // Configure I2S via ESP-IDF new driver
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(
        I2S_NUM_0, I2S_ROLE_MASTER);
    // DMA config: 8 descriptors × 256 frames = 2048 frames total
    // At 16kHz stereo 16-bit: 2048 frames × 4 bytes = 8192 bytes ≈ 128ms buffer
    // Each descriptor holds 256 frames = 16ms — matches our mix chunk size
    chan_cfg.dma_desc_num = 8;
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
