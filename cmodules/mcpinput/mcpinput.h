// mcpinput.h — shared types for the MCP23017 native input module
//
// Deterministic button capture on ESP32-S3 core 0.  A FreeRTOS task
// polls the MCP23017 via I2C, debounces all 16 pins, and pushes
// press/release events to a lock-free ring buffer.  Python drains
// events with get_events().
//
// The module owns the I2C bus and exposes mutex-protected i2c_write/
// i2c_read for Python to use with other I2C devices (PCA9685, MCP2).

#ifndef MCPINPUT_H
#define MCPINPUT_H

#include <stdint.h>
#include <stdbool.h>

#include "driver/i2c_master.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

#define MCPINPUT_NUM_PINS       16
#define MCPINPUT_EVENT_BUF_SIZE 32  // power of 2

// Event types
#define MCPINPUT_PRESS          1
#define MCPINPUT_RELEASE        2

// MCP23017 registers (IOCON.BANK=0 default)
#define MCP_IODIRA      0x00
#define MCP_IODIRB      0x01
#define MCP_GPPUA       0x0C
#define MCP_GPPUB       0x0D
#define MCP_GPIOA       0x12

// ---------------------------------------------------------------------------
// Event ring buffer (fixed-size struct slots, SPSC)
// ---------------------------------------------------------------------------

typedef struct {
    uint8_t  type;      // MCPINPUT_PRESS or MCPINPUT_RELEASE
    uint8_t  pin;       // 0-15 (MCP pin number)
    uint16_t _pad;
    uint32_t time_ms;   // milliseconds from esp_timer
} mcpinput_event_t;

typedef struct {
    mcpinput_event_t events[MCPINPUT_EVENT_BUF_SIZE];
    volatile uint32_t wr;   // write index (scanner task)
    volatile uint32_t rd;   // read index (Python / core 1)
} mcpinput_eventbuf_t;

// ---------------------------------------------------------------------------
// Per-button debounce state
// ---------------------------------------------------------------------------

typedef struct {
    uint8_t  raw;               // last raw reading (0 or 1)
    uint8_t  state;             // debounced state (1 = pressed, active-low inverted)
    uint32_t last_change_ms;    // timestamp of last raw transition
} mcpinput_debounce_t;

// ---------------------------------------------------------------------------
// Global state
// ---------------------------------------------------------------------------

typedef struct {
    // I2C bus (owned by this module)
    i2c_master_bus_handle_t bus;
    i2c_master_dev_handle_t mcp_dev;
    SemaphoreHandle_t       i2c_mutex;

    // Button state
    mcpinput_debounce_t     buttons[MCPINPUT_NUM_PINS];
    mcpinput_eventbuf_t     events;
    volatile uint16_t       port_state;     // current debounced bitmask

    // Config
    uint32_t                debounce_ms;
    int                     int_pin;        // -1 = polling, else GPIO num

    // Task control
    volatile uint8_t        running;

    // Diagnostics
    volatile uint32_t       poll_count;
    volatile uint32_t       events_total;
    volatile uint32_t       task_stack_hwm;
} mcpinput_state_t;

// Global state (allocated by init, freed by deinit)
extern mcpinput_state_t *mcpinput_state;

#endif // MCPINPUT_H
