// neopixel_mod.h — shared types for the NeoPixel pattern engine
//
// A FreeRTOS task on core 0 computes LED patterns and writes them
// to the WS2812B strip via a persistent RMT channel at ~40 Hz.
// Python sets zone patterns and per-pixel overrides; the C task
// handles all computation and I/O.

#ifndef NEOPIXEL_MOD_H
#define NEOPIXEL_MOD_H

#include <stdint.h>
#include <stdbool.h>

#include "driver/rmt_tx.h"
#include "driver/rmt_encoder.h"

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

#define NP_NUM_LEDS             108
#define NP_PIXEL_BYTES          (NP_NUM_LEDS * 3)  // GRB, 324 bytes
#define NP_NUM_ZONES            3

// Zone indices
#define NP_ZONE_STICK_A         0
#define NP_ZONE_STICK_B         1
#define NP_ZONE_LID_RING        2

// Zone layout (start index, count)
#define NP_STICK_A_START        0
#define NP_STICK_A_COUNT        8
#define NP_STICK_B_START        8
#define NP_STICK_B_COUNT        8
#define NP_LID_RING_START       16
#define NP_LID_RING_COUNT       92

// Pattern IDs
#define NP_PAT_OFF              0
#define NP_PAT_SOLID            1
#define NP_PAT_RAINBOW          2
#define NP_PAT_PULSE            3
#define NP_PAT_CHASE            4
#define NP_PAT_SPARKLE          5
#define NP_PAT_BOUNCE           6
#define NP_PAT_WAVE             7
#define NP_PAT_SPLIT            8
#define NP_PAT_FILL             9
#define NP_PAT_COUNT            10

// Session override modes
#define NP_OVERRIDE_NONE        0
#define NP_OVERRIDE_BLACK       1   // all LEDs off
#define NP_OVERRIDE_SOLID       2   // all LEDs one colour
#define NP_OVERRIDE_PULSE       3   // all LEDs pulsing one colour
#define NP_OVERRIDE_FADE        4   // all LEDs fading one colour

// Override bitmap size
#define NP_OVERRIDE_BITMAP_SIZE ((NP_NUM_LEDS + 7) / 8)

// ---------------------------------------------------------------------------
// Per-zone configuration (written by Python, read by C task)
// ---------------------------------------------------------------------------

typedef struct {
    uint8_t  start;             // first LED index
    uint8_t  count;             // number of LEDs
    volatile uint8_t  pattern;  // NP_PAT_*
    volatile uint8_t  speed;    // 1-10
    volatile uint8_t  brightness; // 0-255
    volatile uint8_t  r, g, b; // base colour (non-rainbow patterns)
    volatile uint8_t  hue_offset; // for rainbow
} np_zone_t;

// ---------------------------------------------------------------------------
// Per-pixel overrides (game-specific individual LEDs)
// ---------------------------------------------------------------------------

typedef struct {
    uint8_t  rgb[NP_NUM_LEDS * 3];                  // GRB pixel data
    volatile uint8_t  mask[NP_OVERRIDE_BITMAP_SIZE]; // which pixels overridden
} np_overrides_t;

// ---------------------------------------------------------------------------
// Global state
// ---------------------------------------------------------------------------

typedef struct {
    // Pixel buffer — DMA-capable internal SRAM, GRB byte order
    uint8_t *pixel_buf;                 // NP_PIXEL_BYTES

    // Zone configuration
    np_zone_t zones[NP_NUM_ZONES];

    // Per-pixel overrides
    np_overrides_t overrides;

    // Session state override (highest priority)
    volatile uint8_t  override_mode;    // NP_OVERRIDE_*
    volatile uint8_t  override_r;
    volatile uint8_t  override_g;
    volatile uint8_t  override_b;

    // Frame counter (incremented by C task)
    volatile uint32_t frame;

    // Task control
    volatile uint8_t  running;          // task loop flag
    volatile uint8_t  paused;           // skip rendering + RMT write

    // GPIO pin
    int gpio_pin;

    // RMT handles (persistent, created once)
    rmt_channel_handle_t rmt_chan;
    rmt_encoder_handle_t rmt_encoder;

    // Diagnostics
    volatile uint32_t write_count;
    volatile uint32_t task_stack_hwm;
    volatile uint32_t last_frame_us;    // microseconds for last frame
} np_state_t;

// Global state (allocated by init, freed by deinit)
extern np_state_t *neopixel_state;

#endif // NEOPIXEL_MOD_H
