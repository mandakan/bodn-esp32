// scanner.c — FreeRTOS task: MCP23017 polling + debounce + event queue
//
// Polls one MCP23017 at ~500 Hz from a dedicated task on core 0.
// Debounces all 16 pins and pushes press/release events to a lock-free
// ring buffer that Python drains with get_events().
//
// The task also owns the I2C bus and exposes mutex-protected transfer
// functions so Python can access other I2C devices (PCA9685, MCP2).

#include <string.h>

#include "scanner.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/idf_additions.h"
#include "driver/i2c_master.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"

static const char *TAG = "mcpinput";

#define SCAN_TASK_STACK     3072
#define SCAN_TASK_PRIO      (configMAX_PRIORITIES - 3)  // below audiomix
#define POLL_INTERVAL_MS    2       // 500 Hz polling
#define I2C_TIMEOUT_MS      50

// Task handle for cleanup
static TaskHandle_t s_scan_task = NULL;

// ---------------------------------------------------------------------------
// Event buffer helpers (SPSC ring buffer of struct slots)
// ---------------------------------------------------------------------------

static inline uint32_t eventbuf_count(const mcpinput_eventbuf_t *eb) {
    return (eb->wr - eb->rd) & (MCPINPUT_EVENT_BUF_SIZE - 1);
}

static inline bool eventbuf_full(const mcpinput_eventbuf_t *eb) {
    return eventbuf_count(eb) >= (MCPINPUT_EVENT_BUF_SIZE - 1);
}

static void eventbuf_push(mcpinput_eventbuf_t *eb, uint8_t type,
                           uint8_t pin, uint32_t time_ms) {
    if (eventbuf_full(eb)) return;  // drop oldest-style: just don't push

    uint32_t idx = eb->wr & (MCPINPUT_EVENT_BUF_SIZE - 1);
    eb->events[idx].type = type;
    eb->events[idx].pin = pin;
    eb->events[idx]._pad = 0;
    eb->events[idx].time_ms = time_ms;
    eb->wr++;
}

// ---------------------------------------------------------------------------
// Debounce
// ---------------------------------------------------------------------------

static void debounce_init(mcpinput_debounce_t *d) {
    d->raw = 1;        // unpressed (active-low)
    d->state = 0;      // not pressed
    d->last_change_ms = 0;
}

// Returns: 0 = no change, 1 = pressed, 2 = released
static uint8_t debounce_update(mcpinput_debounce_t *d, uint8_t raw_bit,
                                uint32_t now_ms, uint32_t debounce_ms) {
    if (raw_bit != d->raw) {
        d->raw = raw_bit;
        d->last_change_ms = now_ms;
    }

    if ((now_ms - d->last_change_ms) >= debounce_ms) {
        // Active-low: raw=0 means pressed
        uint8_t new_state = (raw_bit == 0) ? 1 : 0;
        if (new_state != d->state) {
            d->state = new_state;
            return new_state ? MCPINPUT_PRESS : MCPINPUT_RELEASE;
        }
    }
    return 0;
}

// ---------------------------------------------------------------------------
// I2C helpers (internal, must hold mutex or be in scan task)
// ---------------------------------------------------------------------------

static esp_err_t mcp_read_ports(mcpinput_state_t *s, uint8_t *buf2) {
    uint8_t reg = MCP_GPIOA;
    return i2c_master_transmit_receive(s->mcp_dev, &reg, 1, buf2, 2,
                                        I2C_TIMEOUT_MS);
}

static esp_err_t mcp_write_reg(mcpinput_state_t *s, uint8_t reg, uint8_t val) {
    uint8_t buf[2] = { reg, val };
    return i2c_master_transmit(s->mcp_dev, buf, 2, I2C_TIMEOUT_MS);
}

// ---------------------------------------------------------------------------
// PCA9685 LED engine — general-purpose animation for arcade buttons
// ---------------------------------------------------------------------------

// PCA9685 registers
#define PCA_MODE1       0x00
#define PCA_MODE2       0x04
#define PCA_LED0_ON_L   0x06
#define PCA_ALL_LED_ON_L 0xFA
#define PCA_PRE_SCALE   0xFE

#define PCA_MODE1_SLEEP   0x10
#define PCA_MODE1_AI      0x20  // auto-increment
#define PCA_MODE1_RESTART 0x80

// Wave animation: phase offset per channel (creates ripple effect)
#define WAVE_SPACING    32

// Batch-write up to 5 channels of PCA9685 duty values in one I2C transaction.
// Caller must NOT hold i2c_mutex — this function acquires it.
static void pca_write_batch(mcpinput_state_t *s,
                             const uint16_t *duties, int n) {
    if (s->pca_dev == NULL || n <= 0 || n > MCPINPUT_LED_MAX_CH) return;

    uint8_t buf[1 + MCPINPUT_LED_MAX_CH * 4];
    buf[0] = PCA_LED0_ON_L + 4 * s->pca_start_ch;
    for (int i = 0; i < n; i++) {
        int off = 1 + i * 4;
        uint16_t d = duties[i];
        if (d == 0) {
            buf[off] = 0; buf[off+1] = 0; buf[off+2] = 0; buf[off+3] = 0x10;
        } else if (d >= 4095) {
            buf[off] = 0; buf[off+1] = 0x10; buf[off+2] = 0; buf[off+3] = 0;
        } else {
            buf[off] = 0; buf[off+1] = 0; buf[off+2] = d & 0xFF; buf[off+3] = d >> 8;
        }
    }

    xSemaphoreTake(s->i2c_mutex, portMAX_DELAY);
    i2c_master_transmit(s->pca_dev, buf, 1 + n * 4, I2C_TIMEOUT_MS);
    xSemaphoreGive(s->i2c_mutex);
}

// --- Animation duty helpers (pure math, no I/O) ---

static inline uint16_t pulse_duty(uint32_t now_ms, uint8_t speed) {
    if (speed == 0) speed = 2;
    uint8_t phase = (uint8_t)((now_ms * speed) >> 2) & 0xFF;
    uint16_t v = phase < 128 ? phase : 255 - phase;
    return MCPINPUT_LED_DUTY_GLOW
         + ((v * (MCPINPUT_LED_DUTY_ON - MCPINPUT_LED_DUTY_GLOW)) >> 7);
}

static inline uint16_t blink_duty(uint32_t now_ms, uint8_t speed) {
    if (speed == 0) speed = 4;
    return ((now_ms * speed) >> 7) & 1 ? MCPINPUT_LED_DUTY_ON
                                        : MCPINPUT_LED_DUTY_OFF;
}

static inline uint16_t flash_duty(const led_channel_t *ch) {
    if (ch->flash_ttl == 0 || ch->flash_start == 0) return 0;
    return (uint16_t)ch->flash_ttl * MCPINPUT_LED_DUTY_ON / ch->flash_start;
}

static inline uint16_t wave_duty(uint32_t now_ms, int channel, uint8_t speed) {
    if (speed == 0) speed = 2;
    // Stagger phase per channel for ripple effect
    uint32_t offset_ms = (uint32_t)channel * WAVE_SPACING * 4 / (speed ? speed : 1);
    uint8_t phase = (uint8_t)(((now_ms - offset_ms) * speed) >> 2) & 0xFF;
    uint16_t v = phase < 128 ? phase : 255 - phase;
    return MCPINPUT_LED_DUTY_GLOW
         + ((v * (MCPINPUT_LED_DUTY_ON - MCPINPUT_LED_DUTY_GLOW)) >> 7);
}

// Compute duties from per-channel animation state and write PCA9685.
// Called every scan cycle when led_mode != PYTHON.
static void led_engine_tick(mcpinput_state_t *s, uint32_t now_ms) {
    int n = s->pca_n_ch;
    uint16_t duties[MCPINPUT_LED_MAX_CH];
    bool changed = false;

    for (int i = 0; i < n; i++) {
        led_channel_t *ch = &s->led_ch[i];
        uint16_t d;
        switch (ch->mode) {
            case LED_ANIM_ON:    d = MCPINPUT_LED_DUTY_ON;    break;
            case LED_ANIM_GLOW:  d = MCPINPUT_LED_DUTY_GLOW;  break;
            case LED_ANIM_PULSE: d = pulse_duty(now_ms, ch->speed); break;
            case LED_ANIM_BLINK: d = blink_duty(now_ms, ch->speed); break;
            case LED_ANIM_FLASH: d = flash_duty(ch);           break;
            case LED_ANIM_WAVE:  d = wave_duty(now_ms, i, ch->speed); break;
            default:             d = MCPINPUT_LED_DUTY_OFF;    break;
        }
        duties[i] = d;
        if (d != s->led_duty[i]) changed = true;
    }

    if (changed) {
        pca_write_batch(s, duties, n);
        for (int i = 0; i < n; i++) s->led_duty[i] = duties[i];
    }
}

// --- Beat-sync: set channel modes from audiomix clock, then engine tick ---

#include "audiomix.h"

static void led_beat_sync_update(mcpinput_state_t *s) {
    if (audiomix_state == NULL) return;

    seq_clock_t *clk = &audiomix_state->clock;
    uint8_t playing = clk->playing;
    uint8_t step = clk->current_step;

    if (playing && step != s->led_last_step) {
        s->led_last_step = step;
        uint8_t perc_mask = clk->steps[step].perc_mask;
        uint8_t active = s->led_track_active;

        for (int i = 0; i < s->pca_n_ch; i++) {
            if (perc_mask & (1 << i))       s->led_ch[i].mode = LED_ANIM_ON;
            else if (active & (1 << i))     s->led_ch[i].mode = LED_ANIM_GLOW;
            else                            s->led_ch[i].mode = LED_ANIM_OFF;
        }
    } else if (!playing && s->led_last_step != 0xFF) {
        s->led_last_step = 0xFF;
        uint8_t active = s->led_track_active;
        for (int i = 0; i < s->pca_n_ch; i++) {
            s->led_ch[i].mode = (active & (1 << i)) ? LED_ANIM_GLOW
                                                       : LED_ANIM_OFF;
        }
    }
    // Engine tick computes duties and writes PCA9685
}

// --- Whack: hit/timeout detection, then set channel modes for engine tick ---

static void led_whack_update(mcpinput_state_t *s, uint32_t now_ms) {
    uint8_t target = s->whack_target;
    if (target >= s->pca_n_ch) return;

    // Hit detection
    uint8_t pin = s->whack_pins[target];
    if (s->port_state & (1 << pin)) {
        s->whack_hit = 1;
        s->whack_target = 0xFF;
        for (int i = 0; i < s->pca_n_ch; i++)
            s->led_ch[i].mode = (i == target) ? LED_ANIM_ON : LED_ANIM_OFF;
        return;
    }

    // Timeout detection
    if (now_ms >= s->whack_deadline_ms) {
        s->whack_miss = 1;
        s->whack_target = 0xFF;
        for (int i = 0; i < s->pca_n_ch; i++)
            s->led_ch[i].mode = LED_ANIM_OFF;
        return;
    }

    // Active target: pulse it, others off
    for (int i = 0; i < s->pca_n_ch; i++) {
        if (i == target) {
            s->led_ch[i].mode = LED_ANIM_PULSE;
            s->led_ch[i].speed = s->led_ch[target].speed;
        } else {
            s->led_ch[i].mode = LED_ANIM_OFF;
        }
    }
}

// ---------------------------------------------------------------------------
// Scan task (core 0)
// ---------------------------------------------------------------------------

static void scan_task(void *arg) {
    mcpinput_state_t *s = (mcpinput_state_t *)arg;
    uint8_t port_buf[2];
    esp_err_t err;

    ESP_LOGI(TAG, "scan task started (poll %d ms, debounce %lu ms)",
             POLL_INTERVAL_MS, (unsigned long)s->debounce_ms);

    while (s->running) {
        vTaskDelay(pdMS_TO_TICKS(POLL_INTERVAL_MS));

        // Read both MCP ports under mutex
        xSemaphoreTake(s->i2c_mutex, portMAX_DELAY);
        err = mcp_read_ports(s, port_buf);
        xSemaphoreGive(s->i2c_mutex);

        if (err != ESP_OK) {
            continue;  // I2C glitch — try next cycle
        }

        s->poll_count++;
        uint32_t now = (uint32_t)(esp_timer_get_time() / 1000);
        uint16_t raw = (uint16_t)port_buf[0] | ((uint16_t)port_buf[1] << 8);

        // Debounce each pin
        for (int i = 0; i < MCPINPUT_NUM_PINS; i++) {
            uint8_t bit = (raw >> i) & 1;
            uint8_t edge = debounce_update(&s->buttons[i], bit, now,
                                            s->debounce_ms);
            if (edge) {
                eventbuf_push(&s->events, edge, (uint8_t)i, now);
                s->events_total++;
            }
        }

        // Update composite port state bitmask
        uint16_t state = 0;
        for (int i = 0; i < MCPINPUT_NUM_PINS; i++) {
            if (s->buttons[i].state) {
                state |= (1 << i);
            }
        }
        s->port_state = state;

        // LED engine: compute animation duties and write PCA9685.
        // Composite modes (beat-sync, whack) update channel states first.
        // In all modes (including PYTHON), the engine tick runs the
        // per-channel animation and writes I2C at 500Hz.
        if (s->pca_dev != NULL) {
            if (s->led_mode == MCPINPUT_LED_MODE_BEAT_SYNC) {
                led_beat_sync_update(s);
            } else if (s->led_mode == MCPINPUT_LED_MODE_WHACK) {
                led_whack_update(s, now);
            }
            led_engine_tick(s, now);
        }

        // Update stack high water mark periodically
        if ((s->poll_count & 0xFF) == 0) {
            s->task_stack_hwm = uxTaskGetStackHighWaterMark(NULL);
        }
    }

    ESP_LOGI(TAG, "scan task exiting");
    vTaskDelete(NULL);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

const char *scanner_init(const scanner_config_t *cfg, mcpinput_state_t **state_out) {
    // Allocate state in internal DRAM (not PSRAM — needs fast access)
    mcpinput_state_t *state = heap_caps_calloc(1, sizeof(mcpinput_state_t),
                                                MALLOC_CAP_INTERNAL);
    if (state == NULL) {
        return "failed to allocate mcpinput state";
    }

    state->debounce_ms = cfg->debounce_ms;
    state->int_pin = cfg->int_pin;

    // Init debounce state
    for (int i = 0; i < MCPINPUT_NUM_PINS; i++) {
        debounce_init(&state->buttons[i]);
    }

    // Create I2C mutex
    state->i2c_mutex = xSemaphoreCreateMutex();
    if (state->i2c_mutex == NULL) {
        heap_caps_free(state);
        return "failed to create I2C mutex";
    }

    // Init I2C master bus
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = (gpio_num_t)cfg->pin_sda,
        .scl_io_num = (gpio_num_t)cfg->pin_scl,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = false,  // external pull-ups on devkit
    };

    esp_err_t err = i2c_new_master_bus(&bus_cfg, &state->bus);
    if (err != ESP_OK) {
        vSemaphoreDelete(state->i2c_mutex);
        heap_caps_free(state);
        return "i2c_new_master_bus failed (I2C_NUM_0 busy?)";
    }

    // Add MCP23017 device
    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = (uint16_t)cfg->mcp_addr,
        .scl_speed_hz = (uint32_t)cfg->freq,
    };

    err = i2c_master_bus_add_device(state->bus, &dev_cfg, &state->mcp_dev);
    if (err != ESP_OK) {
        i2c_del_master_bus(state->bus);
        vSemaphoreDelete(state->i2c_mutex);
        heap_caps_free(state);
        return "failed to add MCP23017 device to I2C bus";
    }

    // Configure MCP23017: all pins as inputs with pull-ups
    mcp_write_reg(state, MCP_IODIRA, 0xFF);
    mcp_write_reg(state, MCP_IODIRB, 0xFF);
    mcp_write_reg(state, MCP_GPPUA, 0xFF);
    mcp_write_reg(state, MCP_GPPUB, 0xFF);

    // Do an initial read to prime debounce state
    uint8_t init_buf[2];
    err = mcp_read_ports(state, init_buf);
    if (err == ESP_OK) {
        uint16_t raw = (uint16_t)init_buf[0] | ((uint16_t)init_buf[1] << 8);
        for (int i = 0; i < MCPINPUT_NUM_PINS; i++) {
            state->buttons[i].raw = (raw >> i) & 1;
        }
    }

    // Start scan task on core 0
    state->running = 1;
    BaseType_t ret = xTaskCreatePinnedToCore(
        scan_task, "mcpinput", SCAN_TASK_STACK,
        state, SCAN_TASK_PRIO, &s_scan_task, 0);
    if (ret != pdPASS) {
        i2c_master_bus_rm_device(state->mcp_dev);
        i2c_del_master_bus(state->bus);
        vSemaphoreDelete(state->i2c_mutex);
        heap_caps_free(state);
        return "xTaskCreatePinnedToCore failed";
    }

    ESP_LOGI(TAG, "init OK — addr 0x%02X, debounce %d ms, int_pin %d",
             cfg->mcp_addr, cfg->debounce_ms, cfg->int_pin);

    *state_out = state;
    return NULL;
}

void scanner_deinit(mcpinput_state_t *state) {
    if (state == NULL) return;

    // Signal task to stop and wait
    state->running = 0;
    if (s_scan_task) {
        vTaskDelay(pdMS_TO_TICKS(50));
        s_scan_task = NULL;
    }

    // Release PCA9685 device handle (if initialized)
    if (state->pca_dev) {
        i2c_master_bus_rm_device(state->pca_dev);
        state->pca_dev = NULL;
    }

    // Release I2C
    if (state->mcp_dev) {
        i2c_master_bus_rm_device(state->mcp_dev);
    }
    if (state->bus) {
        i2c_del_master_bus(state->bus);
    }
    if (state->i2c_mutex) {
        vSemaphoreDelete(state->i2c_mutex);
    }

    heap_caps_free(state);
    ESP_LOGI(TAG, "deinit complete");
}

// ---------------------------------------------------------------------------
// PCA9685 LED initialization
// ---------------------------------------------------------------------------

int scanner_led_init(mcpinput_state_t *state, uint8_t pca_addr,
                     uint8_t start_ch, uint8_t n_ch) {
    if (state == NULL) return -1;
    if (n_ch > MCPINPUT_LED_MAX_CH) n_ch = MCPINPUT_LED_MAX_CH;

    // Remove old device handle if re-initializing
    if (state->pca_dev) {
        i2c_master_bus_rm_device(state->pca_dev);
        state->pca_dev = NULL;
    }

    // Probe the PCA9685
    xSemaphoreTake(state->i2c_mutex, portMAX_DELAY);
    esp_err_t err = i2c_master_probe(state->bus, pca_addr, I2C_TIMEOUT_MS);
    xSemaphoreGive(state->i2c_mutex);

    if (err != ESP_OK) {
        ESP_LOGW(TAG, "PCA9685 (0x%02X) not found", pca_addr);
        return -1;
    }

    // Add persistent device handle
    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = pca_addr,
        .scl_speed_hz = 400000,
    };

    xSemaphoreTake(state->i2c_mutex, portMAX_DELAY);
    err = i2c_master_bus_add_device(state->bus, &dev_cfg, &state->pca_dev);
    if (err != ESP_OK) {
        xSemaphoreGive(state->i2c_mutex);
        ESP_LOGE(TAG, "PCA9685 add_device failed (%d)", err);
        return -1;
    }

    // Init sequence: sleep → set prescaler → wake + auto-increment
    // Prescaler for 1 kHz: round(25_000_000 / (4096 * 1000)) - 1 = 5
    uint8_t cmd[2];

    // 1. Sleep + auto-increment
    cmd[0] = PCA_MODE1; cmd[1] = PCA_MODE1_SLEEP | PCA_MODE1_AI;
    i2c_master_transmit(state->pca_dev, cmd, 2, I2C_TIMEOUT_MS);

    // 2. MODE2: totem-pole outputs
    cmd[0] = PCA_MODE2; cmd[1] = 0x04;
    i2c_master_transmit(state->pca_dev, cmd, 2, I2C_TIMEOUT_MS);

    // 3. Set prescaler (1 kHz)
    cmd[0] = PCA_PRE_SCALE; cmd[1] = 5;
    i2c_master_transmit(state->pca_dev, cmd, 2, I2C_TIMEOUT_MS);

    // 4. Turn off only our channels (not all — CH0 is the display backlight)
    for (uint8_t ch = start_ch; ch < start_ch + n_ch; ch++) {
        uint8_t ch_off[5] = { (uint8_t)(PCA_LED0_ON_L + 4 * ch), 0, 0, 0, 0x10 };
        i2c_master_transmit(state->pca_dev, ch_off, 5, I2C_TIMEOUT_MS);
    }

    // 5. Wake up (clear sleep, enable auto-increment)
    cmd[0] = PCA_MODE1; cmd[1] = PCA_MODE1_AI;
    i2c_master_transmit(state->pca_dev, cmd, 2, I2C_TIMEOUT_MS);

    xSemaphoreGive(state->i2c_mutex);

    // Store config
    state->pca_start_ch = start_ch;
    state->pca_n_ch = n_ch;
    state->led_mode = MCPINPUT_LED_MODE_PYTHON;  // default: Python controls
    state->led_last_step = 0xFF;
    state->led_track_active = 0;
    for (int i = 0; i < MCPINPUT_LED_MAX_CH; i++) state->led_duty[i] = 0;

    ESP_LOGI(TAG, "PCA9685 (0x%02X) LED init OK — ch %d..%d",
             pca_addr, start_ch, start_ch + n_ch - 1);
    return 0;
}

// ---------------------------------------------------------------------------
// Mutex-protected I2C access for Python
// ---------------------------------------------------------------------------

int scanner_i2c_write(mcpinput_state_t *state, uint8_t addr,
                      uint8_t reg, const uint8_t *data, size_t len) {
    // Build buffer: [reg, data...]
    uint8_t buf[1 + len];
    buf[0] = reg;
    if (len > 0) {
        memcpy(buf + 1, data, len);
    }

    // Add a temporary device handle for this address
    i2c_device_config_t cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = addr,
        .scl_speed_hz = 400000,
    };
    i2c_master_dev_handle_t dev;

    xSemaphoreTake(state->i2c_mutex, portMAX_DELAY);
    esp_err_t err = i2c_master_bus_add_device(state->bus, &cfg, &dev);
    if (err == ESP_OK) {
        err = i2c_master_transmit(dev, buf, 1 + len, I2C_TIMEOUT_MS);
        i2c_master_bus_rm_device(dev);
    }
    xSemaphoreGive(state->i2c_mutex);

    return (int)err;
}

int scanner_i2c_read(mcpinput_state_t *state, uint8_t addr,
                     uint8_t reg, uint8_t *buf, size_t len) {
    i2c_device_config_t cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = addr,
        .scl_speed_hz = 400000,
    };
    i2c_master_dev_handle_t dev;

    xSemaphoreTake(state->i2c_mutex, portMAX_DELAY);
    esp_err_t err = i2c_master_bus_add_device(state->bus, &cfg, &dev);
    if (err == ESP_OK) {
        err = i2c_master_transmit_receive(dev, &reg, 1, buf, len,
                                           I2C_TIMEOUT_MS);
        i2c_master_bus_rm_device(dev);
    }
    xSemaphoreGive(state->i2c_mutex);

    return (int)err;
}

int scanner_i2c_raw_write(mcpinput_state_t *state, uint8_t addr,
                           const uint8_t *data, size_t len) {
    i2c_device_config_t cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = addr,
        .scl_speed_hz = 400000,
    };
    i2c_master_dev_handle_t dev;

    xSemaphoreTake(state->i2c_mutex, portMAX_DELAY);
    esp_err_t err = i2c_master_bus_add_device(state->bus, &cfg, &dev);
    if (err == ESP_OK) {
        err = i2c_master_transmit(dev, data, len, I2C_TIMEOUT_MS);
        i2c_master_bus_rm_device(dev);
    }
    xSemaphoreGive(state->i2c_mutex);

    return (int)err;
}

int scanner_i2c_raw_read(mcpinput_state_t *state, uint8_t addr,
                          uint8_t *buf, size_t len) {
    i2c_device_config_t cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = addr,
        .scl_speed_hz = 400000,
    };
    i2c_master_dev_handle_t dev;

    xSemaphoreTake(state->i2c_mutex, portMAX_DELAY);
    esp_err_t err = i2c_master_bus_add_device(state->bus, &cfg, &dev);
    if (err == ESP_OK) {
        err = i2c_master_receive(dev, buf, len, I2C_TIMEOUT_MS);
        i2c_master_bus_rm_device(dev);
    }
    xSemaphoreGive(state->i2c_mutex);

    return (int)err;
}

int scanner_i2c_scan(mcpinput_state_t *state, uint8_t *addrs, size_t addrs_size) {
    int count = 0;

    xSemaphoreTake(state->i2c_mutex, portMAX_DELAY);
    for (uint16_t addr = 0x08; addr < 0x78; addr++) {
        esp_err_t err = i2c_master_probe(state->bus, addr, I2C_TIMEOUT_MS);
        if (err == ESP_OK && count < (int)addrs_size) {
            addrs[count++] = (uint8_t)addr;
        }
    }
    xSemaphoreGive(state->i2c_mutex);

    return count;
}
