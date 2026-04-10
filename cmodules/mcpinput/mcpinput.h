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
// LED animation engine
// ---------------------------------------------------------------------------

#define MCPINPUT_LED_MAX_CH         5   // max arcade LED channels

// Per-channel animation modes (set by Python, evaluated by C engine tick)
#define LED_ANIM_OFF    0   // duty = 0
#define LED_ANIM_ON     1   // duty = 4095
#define LED_ANIM_GLOW   2   // duty = 192
#define LED_ANIM_PULSE  3   // triangle wave: glow ↔ on
#define LED_ANIM_BLINK  4   // on/off square wave
#define LED_ANIM_FLASH  5   // linear decay on→off (frame-timed)
#define LED_ANIM_WAVE   6   // staggered pulse per channel

// Per-channel animation state
typedef struct {
    uint8_t  mode;       // LED_ANIM_*
    uint8_t  speed;      // animation speed parameter (1-8)
    uint8_t  flash_ttl;  // frames remaining for FLASH (Python decrements)
    uint8_t  flash_start; // initial flash duration (for computing duty ratio)
} led_channel_t;

// Global LED operating modes (controls which tick function runs)
#define MCPINPUT_LED_MODE_PYTHON    0   // Python drives via led_anim() → C engine tick
#define MCPINPUT_LED_MODE_BEAT_SYNC 1   // C reads audiomix clock → sets ch modes → engine tick
#define MCPINPUT_LED_MODE_WHACK     2   // C pulse + hit/miss detection → engine tick

// PCA9685 duty presets (12-bit)
#define MCPINPUT_LED_DUTY_OFF       0
#define MCPINPUT_LED_DUTY_GLOW      192   // ~5% brightness
#define MCPINPUT_LED_DUTY_ON        4095  // full brightness

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

    // PCA9685 LED control (optional, initialized by led_init)
    i2c_master_dev_handle_t pca_dev;        // NULL if not initialized
    uint8_t                 pca_start_ch;   // first PCA9685 channel
    uint8_t                 pca_n_ch;       // number of channels (max 5)
    volatile uint8_t        led_mode;       // MCPINPUT_LED_MODE_*
    led_channel_t           led_ch[MCPINPUT_LED_MAX_CH]; // per-channel animation state
    uint16_t                led_duty[MCPINPUT_LED_MAX_CH]; // current duty (dirty check)

    // Beat-sync mode state (sequencer)
    uint8_t                 led_last_step;  // cached step for change detection
    volatile uint8_t        led_track_active; // 5-bit mask: tracks with notes

    // Whack / High-Five mode state (hit detection + timing)
    volatile uint8_t        whack_target;    // active button 0-4, 0xFF = none
    volatile uint32_t       whack_deadline_ms; // esp_timer ms deadline for timeout
    volatile uint8_t        whack_hit;       // set by scan task on hit, cleared by Python
    volatile uint8_t        whack_miss;      // set by scan task on timeout, cleared by Python
    uint8_t                 whack_pins[MCPINPUT_LED_MAX_CH]; // MCP pin per arcade button

    // Diagnostics
    volatile uint32_t       poll_count;
    volatile uint32_t       events_total;
    volatile uint32_t       task_stack_hwm;
} mcpinput_state_t;

// Global state (allocated by init, freed by deinit)
extern mcpinput_state_t *mcpinput_state;

#endif // MCPINPUT_H
