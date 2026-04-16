// engine.c — NeoPixel pattern engine (FreeRTOS task + persistent RMT)
//
// The task runs on core 0 at ~40 Hz.  Each frame it:
//   1. Checks for session-level override (highest priority)
//   2. Computes zone patterns into the pixel buffer
//   3. Composites per-pixel overrides on top
//   4. Transmits via RMT (persistent channel, no alloc/free per frame)

#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/idf_additions.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "esp_rom_gpio.h"
#include "soc/gpio_sig_map.h"

#include "engine.h"
#include "patterns.h"

static const char *TAG = "neopixel";

// Task parameters
#define NP_TASK_STACK       3072
#define NP_TASK_PRIO        (configMAX_PRIORITIES - 4)
#define NP_FRAME_DELAY_MS   25      // ~40 Hz

// RMT configuration (40 MHz clock, WS2812B 800 kHz timing)
#define NP_RMT_RESOLUTION   40000000
// At 40 MHz: 400ns = 16 ticks, 850ns = 34 ticks
//            800ns = 32 ticks, 450ns = 18 ticks
#define NP_T0H_TICKS        16
#define NP_T0L_TICKS        34
#define NP_T1H_TICKS        32
#define NP_T1L_TICKS        18

static TaskHandle_t s_task_handle = NULL;

// ---------------------------------------------------------------------------
// Session override rendering
// ---------------------------------------------------------------------------

static void apply_session_override(np_state_t *state) {
    uint8_t *buf = state->pixel_buf;
    uint8_t mode = state->override_mode;
    uint8_t r = state->override_r;
    uint8_t g = state->override_g;
    uint8_t b = state->override_b;

    if (mode == NP_OVERRIDE_BLACK) {
        memset(buf, 0, NP_PIXEL_BYTES);
        return;
    }

    uint8_t v;  // brightness multiplier

    if (mode == NP_OVERRIDE_SOLID) {
        // Static solid colour
        for (int i = 0; i < NP_NUM_LEDS; i++) {
            int off = i * 3;
            buf[off + 0] = g;  // GRB order
            buf[off + 1] = r;
            buf[off + 2] = b;
        }
        return;
    }

    if (mode == NP_OVERRIDE_PULSE) {
        // Triangle-wave pulsing
        uint8_t phase = (state->frame * 3) & 0xFF;
        v = phase < 128 ? phase : 255 - phase;
    } else if (mode == NP_OVERRIDE_FADE) {
        // Slow fade to dim
        uint8_t phase = (state->frame * 1) & 0xFF;
        v = phase < 128 ? phase : 255 - phase;
        v = v >> 1;  // half brightness for fade
    } else {
        v = 255;
    }

    uint8_t gr = (g * v) >> 8;
    uint8_t rr = (r * v) >> 8;
    uint8_t br = (b * v) >> 8;
    for (int i = 0; i < NP_NUM_LEDS; i++) {
        int off = i * 3;
        buf[off + 0] = gr;
        buf[off + 1] = rr;
        buf[off + 2] = br;
    }
}

// ---------------------------------------------------------------------------
// Per-pixel override compositing
// ---------------------------------------------------------------------------

static void apply_pixel_overrides(np_state_t *state) {
    np_overrides_t *ov = &state->overrides;
    uint8_t *buf = state->pixel_buf;
    for (int byte_idx = 0; byte_idx < NP_OVERRIDE_BITMAP_SIZE; byte_idx++) {
        uint8_t mask = ov->mask[byte_idx];
        if (mask == 0) continue;
        for (int bit = 0; bit < 8; bit++) {
            if (mask & (1 << bit)) {
                int led = byte_idx * 8 + bit;
                if (led >= NP_NUM_LEDS) return;
                int off = led * 3;
                buf[off + 0] = ov->rgb[off + 0];  // already GRB
                buf[off + 1] = ov->rgb[off + 1];
                buf[off + 2] = ov->rgb[off + 2];
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Engine task
// ---------------------------------------------------------------------------

static void engine_task(void *arg) {
    np_state_t *state = (np_state_t *)arg;

    rmt_transmit_config_t tx_config = {
        .loop_count = 0,
        .flags.eot_level = 0,
    };

    while (state->running) {
        vTaskDelay(pdMS_TO_TICKS(NP_FRAME_DELAY_MS));

        if (state->paused) continue;

        uint32_t t0 = (uint32_t)(esp_timer_get_time() / 1000);
        state->frame++;

        // 1. Session override (highest priority)
        if (state->override_mode != NP_OVERRIDE_NONE) {
            apply_session_override(state);
        } else {
            // 2. Compute zone patterns
            for (int z = 0; z < NP_NUM_ZONES; z++) {
                np_zone_t *zone = &state->zones[z];
                uint8_t pat = zone->pattern;
                if (pat < NP_PAT_COUNT && np_pattern_funcs[pat] != NULL) {
                    np_pattern_funcs[pat](
                        state->pixel_buf + zone->start * 3,
                        zone->count, zone->speed, zone->brightness,
                        zone->r, zone->g, zone->b,
                        zone->hue_offset, state->frame);
                }
            }

            // 3. Per-pixel overrides
            apply_pixel_overrides(state);
        }

        // 4. RMT transmit
        rmt_encoder_reset(state->rmt_encoder);
        esp_err_t err = rmt_transmit(state->rmt_chan, state->rmt_encoder,
                                      state->pixel_buf, NP_PIXEL_BYTES,
                                      &tx_config);
        if (err == ESP_OK) {
            rmt_tx_wait_all_done(state->rmt_chan, 100);
            state->write_count++;
        }

        uint32_t t1 = (uint32_t)(esp_timer_get_time() / 1000);
        state->last_frame_us = (t1 - t0) * 1000;

        // Periodic stack watermark check
        if ((state->write_count & 0x3F) == 0) {
            state->task_stack_hwm = uxTaskGetStackHighWaterMark(NULL);
        }
    }

    // Task ending — turn off all LEDs
    memset(state->pixel_buf, 0, NP_PIXEL_BYTES);
    rmt_encoder_reset(state->rmt_encoder);
    rmt_transmit(state->rmt_chan, state->rmt_encoder,
                 state->pixel_buf, NP_PIXEL_BYTES,
                 &(rmt_transmit_config_t){ .loop_count = 0 });
    rmt_tx_wait_all_done(state->rmt_chan, 100);

    vTaskDelete(NULL);
}

// ---------------------------------------------------------------------------
// Init / Deinit
// ---------------------------------------------------------------------------

const char *engine_init(const np_engine_config_t *cfg, np_state_t **state_out) {
    // Allocate state struct
    np_state_t *state = heap_caps_calloc(1, sizeof(np_state_t),
                                          MALLOC_CAP_INTERNAL);
    if (state == NULL) return "alloc state failed";

    // Allocate pixel buffer (DMA-capable internal SRAM)
    state->pixel_buf = heap_caps_calloc(1, NP_PIXEL_BYTES,
                                         MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    if (state->pixel_buf == NULL) {
        heap_caps_free(state);
        return "alloc pixel_buf failed";
    }

    state->gpio_pin = cfg->gpio_pin;

    // Initialise zone layout
    state->zones[NP_ZONE_STICK_A].start = NP_STICK_A_START;
    state->zones[NP_ZONE_STICK_A].count = NP_STICK_A_COUNT;
    state->zones[NP_ZONE_STICK_B].start = NP_STICK_B_START;
    state->zones[NP_ZONE_STICK_B].count = NP_STICK_B_COUNT;
    state->zones[NP_ZONE_LID_RING].start = NP_LID_RING_START;
    state->zones[NP_ZONE_LID_RING].count = NP_LID_RING_COUNT;

    // All zones start OFF
    for (int z = 0; z < NP_NUM_ZONES; z++) {
        state->zones[z].pattern = NP_PAT_OFF;
        state->zones[z].speed = 3;
        state->zones[z].brightness = 64;
    }

    // Create persistent RMT TX channel
    rmt_tx_channel_config_t tx_cfg = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .gpio_num = cfg->gpio_pin,
        .mem_block_symbols = SOC_RMT_MEM_WORDS_PER_CHANNEL,
        .resolution_hz = NP_RMT_RESOLUTION,
        .trans_queue_depth = 1,
    };
    esp_err_t err = rmt_new_tx_channel(&tx_cfg, &state->rmt_chan);
    if (err != ESP_OK) {
        heap_caps_free(state->pixel_buf);
        heap_caps_free(state);
        return "rmt_new_tx_channel failed";
    }

    err = rmt_enable(state->rmt_chan);
    if (err != ESP_OK) {
        rmt_del_channel(state->rmt_chan);
        heap_caps_free(state->pixel_buf);
        heap_caps_free(state);
        return "rmt_enable failed";
    }

    // Create persistent bytes encoder (WS2812B timing)
    rmt_bytes_encoder_config_t enc_cfg = {
        .bit0 = {
            .level0 = 1, .duration0 = NP_T0H_TICKS,
            .level1 = 0, .duration1 = NP_T0L_TICKS,
        },
        .bit1 = {
            .level0 = 1, .duration0 = NP_T1H_TICKS,
            .level1 = 0, .duration1 = NP_T1L_TICKS,
        },
        .flags.msb_first = 1,
    };
    err = rmt_new_bytes_encoder(&enc_cfg, &state->rmt_encoder);
    if (err != ESP_OK) {
        rmt_disable(state->rmt_chan);
        rmt_del_channel(state->rmt_chan);
        heap_caps_free(state->pixel_buf);
        heap_caps_free(state);
        return "rmt_new_bytes_encoder failed";
    }

    // Start engine task on core 0
    state->running = 1;
    BaseType_t ret = xTaskCreatePinnedToCore(
        engine_task, "neopixel", NP_TASK_STACK,
        state, NP_TASK_PRIO, &s_task_handle, 0);
    if (ret != pdPASS) {
        rmt_del_encoder(state->rmt_encoder);
        rmt_disable(state->rmt_chan);
        rmt_del_channel(state->rmt_chan);
        heap_caps_free(state->pixel_buf);
        heap_caps_free(state);
        return "xTaskCreatePinnedToCore failed";
    }

    ESP_LOGI(TAG, "init OK — GPIO %d, %d LEDs, %d zones",
             cfg->gpio_pin, NP_NUM_LEDS, NP_NUM_ZONES);

    *state_out = state;
    return NULL;
}

void engine_deinit(np_state_t *state) {
    if (state == NULL) return;

    // Signal task to stop and wait for it to exit
    state->running = 0;
    vTaskDelay(pdMS_TO_TICKS(100));
    s_task_handle = NULL;

    // Release RMT resources
    if (state->rmt_encoder) {
        rmt_del_encoder(state->rmt_encoder);
        state->rmt_encoder = NULL;
    }
    if (state->rmt_chan) {
        rmt_disable(state->rmt_chan);
        rmt_del_channel(state->rmt_chan);
        state->rmt_chan = NULL;
    }

    // Cancel RMT output to GPIO pin
    esp_rom_gpio_connect_out_signal(state->gpio_pin, SIG_GPIO_OUT_IDX,
                                    false, false);

    // Free memory
    if (state->pixel_buf) {
        heap_caps_free(state->pixel_buf);
    }
    heap_caps_free(state);

    ESP_LOGI(TAG, "deinit OK");
}
