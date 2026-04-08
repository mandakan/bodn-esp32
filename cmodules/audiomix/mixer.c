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

// ESP-IDF headers — only available when building for ESP32
#if defined(ESP_PLATFORM)

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/i2s_std.h"
#include "driver/gpio.h"
#include "esp_log.h"

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
        int is_first = (v->tone_samples_left ==
                        ((state->sample_rate * v->tone_freq) ?
                         v->tone_samples_left : v->tone_samples_left));
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

    // Silence buffer for idle periods
    static const uint8_t silence[64] = {0};

    ESP_LOGI(TAG, "mix task started on core %d", xPortGetCoreID());

    while (state->running) {
        // Handle stop requests
        bool has_active = false;
        bool non_music_active = false;

        for (int i = 0; i < AUDIOMIX_NUM_VOICES; i++) {
            audiomix_voice_t *v = &state->voices[i];
            if (v->stop_req) {
                v->source_type = SRC_NONE;
                v->stop_req = 0;
                ringbuf_reset(&v->ringbuf);
            }
            if (v->source_type != SRC_NONE) {
                has_active = true;
                if (!v->is_music) non_music_active = true;
            }
        }

        if (!has_active) {
            // No active voices — write silence, yield
            size_t written;
            i2s_channel_write(s_i2s_handle, silence, sizeof(silence),
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

            // Per-voice gain with ducking
            uint32_t gain;
            if (v->is_music && non_music_active) {
                gain = AUDIOMIX_GAIN_MUSIC_DUCKED;
            } else {
                gain = v->gain;
            }
            apply_gain(voice_buf, n, gain);
            mix_add(mix_buf, voice_buf, n);

            if (n > max_n) max_n = n;
        }

        if (max_n == 0) {
            size_t written;
            i2s_channel_write(s_i2s_handle, silence, sizeof(silence),
                             &written, portMAX_DELAY);
            continue;
        }

        // Master volume
        if (state->master_volume < 100) {
            apply_gain(mix_buf, max_n, state->vol_mult);
        }

        // Mono → stereo
        mono_to_stereo(mix_buf, stereo_buf, max_n);

        // Write to I2S (blocking — paces loop to DMA timing)
        size_t written;
        i2s_channel_write(s_i2s_handle, stereo_buf, max_n * 4,
                         &written, portMAX_DELAY);
    }

    ESP_LOGI(TAG, "mix task stopped");
    vTaskDelete(NULL);
}

// ---------------------------------------------------------------------------
// Init / deinit
// ---------------------------------------------------------------------------

static TaskHandle_t s_mix_task = NULL;

audiomix_state_t *mixer_init(const mixer_config_t *cfg) {
    // Allocate state in PSRAM
    audiomix_state_t *state = heap_caps_calloc(1, sizeof(audiomix_state_t),
                                                MALLOC_CAP_SPIRAM);
    if (state == NULL) {
        ESP_LOGE(TAG, "failed to allocate state");
        return NULL;
    }

    state->sample_rate = cfg->rate;
    state->master_volume = 10;  // match Python default
    state->vol_mult = 10 * 655;
    state->running = 1;

    // Initialise per-voice state
    for (int i = 0; i < AUDIOMIX_NUM_VOICES; i++) {
        audiomix_voice_t *v = &state->voices[i];
        v->source_type = SRC_NONE;
        v->is_music = (i == AUDIOMIX_V_MUSIC) ? 1 : 0;

        // Set default gains
        if (i == AUDIOMIX_V_MUSIC) {
            v->gain = AUDIOMIX_GAIN_MUSIC;
        } else if (i == AUDIOMIX_V_UI) {
            v->gain = AUDIOMIX_GAIN_UI;
        } else {
            v->gain = AUDIOMIX_GAIN_SFX;
        }

        // Allocate ring buffer
        ringbuf_init(&v->ringbuf, AUDIOMIX_RINGBUF_SIZE);
    }

    // Configure I2S via ESP-IDF new driver
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(
        I2S_NUM_0, I2S_ROLE_MASTER);
    chan_cfg.dma_desc_num = 4;
    chan_cfg.dma_frame_num = cfg->ibuf / 4;  // frames per DMA descriptor

    esp_err_t err = i2s_new_channel(&chan_cfg, &s_i2s_handle, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2s_new_channel failed: %s", esp_err_to_name(err));
        goto fail;
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
        ESP_LOGE(TAG, "i2s_channel_init_std_mode failed: %s",
                 esp_err_to_name(err));
        goto fail;
    }

    err = i2s_channel_enable(s_i2s_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2s_channel_enable failed: %s", esp_err_to_name(err));
        goto fail;
    }

    // Enable amplifier
    gpio_reset_pin((gpio_num_t)cfg->pin_amp);
    gpio_set_direction((gpio_num_t)cfg->pin_amp, GPIO_MODE_OUTPUT);
    gpio_set_level((gpio_num_t)cfg->pin_amp, 1);
    ESP_LOGI(TAG, "amplifier enabled (GPIO %d)", cfg->pin_amp);

    // Start mix task on core 1
    BaseType_t ret = xTaskCreatePinnedToCore(
        mix_task, "audiomix", MIX_TASK_STACK,
        state, MIX_TASK_PRIO, &s_mix_task, 1);
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "failed to create mix task");
        goto fail;
    }

    ESP_LOGI(TAG, "initialised: rate=%d, I2S on bck=%d ws=%d din=%d",
             cfg->rate, cfg->pin_bck, cfg->pin_ws, cfg->pin_din);
    return state;

fail:
    if (s_i2s_handle) {
        i2s_del_channel(s_i2s_handle);
        s_i2s_handle = NULL;
    }
    for (int i = 0; i < AUDIOMIX_NUM_VOICES; i++) {
        ringbuf_deinit(&state->voices[i].ringbuf);
    }
    heap_caps_free(state);
    return NULL;
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

#else
// Host stub for compilation/testing without ESP-IDF
audiomix_state_t *mixer_init(const mixer_config_t *cfg) {
    (void)cfg;
    return NULL;
}
void mixer_deinit(audiomix_state_t *state) {
    (void)state;
}
#endif // ESP_PLATFORM
