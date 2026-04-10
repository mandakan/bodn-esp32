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
